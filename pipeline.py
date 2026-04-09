# ═══════════════════════════════════════════════════════════════════
# INCREMENTAL WALLET PIPELINE
# ═══════════════════════════════════════════════════════════════════
# Shared logic for fetching + processing Solana wallet swaps.
# Used by wallet_dashboard.py for incremental updates.
#
# Design:
#   - fetch_new_transactions() walks Helius newest→oldest and stops at
#     the last known signature, so only NEW txns are pulled.
#   - parse_trade() / build_positions() are ports of the same logic
#     from process_wallet.py — single source of truth now lives here.
#   - update_wallet_data() is the top-level function the dashboard calls.
#     It takes the existing wallet JSON dict, returns an updated dict.
#
# The wallet JSON is extended with two new fields (backward compatible):
#   - "sol_prices": {date_str: float}   cached price map
#   - "last_signature": str             newest signature processed
# Old JSON files without these fields still work — they'll be
# bootstrapped on the first incremental update.
# ═══════════════════════════════════════════════════════════════════

import requests
import time
from datetime import datetime, timezone, timedelta
from collections import defaultdict

# ── Constants ────────────────────────────────────────────────────────
WSOL = "So11111111111111111111111111111111111111112"

STABLECOIN_MINTS = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
}

EXCLUDE_MINTS = STABLECOIN_MINTS | {
    WSOL,
    "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",   # mSOL
    "7dHbWXmci3dT8UFYWYZweBLXgycu7Y3iL6trKn1Y7ARj",  # stSOL
}

DUST_USD = 1.0
DUST_SOL = 0.01


# ════════════════════════════════════════════════════════════════════
# TRANSACTION DETECTION
# ════════════════════════════════════════════════════════════════════
def is_swap(txn, wallet):
    """Ported verbatim from process_wallet.py — detects swap txns."""
    if txn.get("events", {}).get("swap"):
        return True

    tt = txn.get("tokenTransfers", [])
    wallet_tt = [x for x in tt
                 if x.get("fromUserAccount") == wallet
                 or x.get("toUserAccount") == wallet]
    if wallet_tt:
        for a in txn.get("accountData", []):
            if a.get("account") == wallet:
                if abs(a.get("nativeBalanceChange", 0)) > 100_000:
                    return True
        wsol_moves = [x for x in tt
                      if x.get("mint") == WSOL
                      and (x.get("fromUserAccount") == wallet
                           or x.get("toUserAccount") == wallet)
                      and x.get("tokenAmount", 0) > 0.001]
        if wsol_moves:
            return True

    wallet_token_rcv = [x for x in tt
                        if x.get("toUserAccount") == wallet
                        and x.get("mint") not in EXCLUDE_MINTS
                        and x.get("tokenAmount", 0) > 0]
    wallet_token_snt = [x for x in tt
                        if x.get("fromUserAccount") == wallet
                        and x.get("mint") not in EXCLUDE_MINTS
                        and x.get("tokenAmount", 0) > 0]
    any_stable = [x for x in tt
                  if x.get("mint") in STABLECOIN_MINTS
                  and x.get("tokenAmount", 0) > 1.0]

    if any_stable and (wallet_token_rcv or wallet_token_snt):
        return True

    return False


# ════════════════════════════════════════════════════════════════════
# STEP 1 — INCREMENTAL FETCH
# ════════════════════════════════════════════════════════════════════
def fetch_new_transactions(wallet, api_key, last_signature=None,
                           max_pages=50, progress_cb=None):
    """
    Walk Helius newest→oldest, stopping when we hit `last_signature`.

    Returns: list of swap transactions newer than last_signature,
             ordered newest-first (Helius default).

    If last_signature is None (first run), this falls back to fetching
    everything — but the dashboard's incremental path should always
    pass a signature, because the bootstrap JSON from Colab gives us one.

    max_pages is a safety cap: 50 pages × 100 txns = 5000 txns max per
    refresh. If a wallet accumulates more than that between refreshes,
    the user just clicks refresh again.
    """
    new_txns = []
    before_sig = None
    page = 0
    reached_known = False

    while page < max_pages:
        params = {"api-key": api_key, "limit": 100}
        if before_sig:
            params["before"] = before_sig

        try:
            r = requests.get(
                f"https://api.helius.xyz/v0/addresses/{wallet}/transactions",
                params=params, timeout=30
            )
            batch = r.json()
        except Exception as e:
            if progress_cb:
                progress_cb(f"Helius fetch error on page {page + 1}: {e}")
            break

        if not batch or not isinstance(batch, list):
            break

        # Walk the batch; stop at last_signature if we hit it
        for txn in batch:
            if last_signature and txn.get("signature") == last_signature:
                reached_known = True
                break
            if is_swap(txn, wallet):
                new_txns.append(txn)

        page += 1
        if progress_cb:
            progress_cb(f"Page {page}: fetched {len(batch)} txns, "
                        f"{len(new_txns)} new swaps so far")

        if reached_known:
            break
        if len(batch) < 100:
            # Ran out of history without finding last_signature — this
            # only happens on first-ever incremental run or if Helius
            # returned fewer than expected. Not an error.
            break

        before_sig = batch[-1]["signature"]
        time.sleep(0.3)

    return new_txns


# ════════════════════════════════════════════════════════════════════
# STEP 2 — SOL PRICE HISTORY (incremental)
# ════════════════════════════════════════════════════════════════════
def fetch_missing_sol_prices(existing_prices, new_dates):
    """
    Fetch SOL prices only for dates we don't already have.
    `existing_prices` is the cached dict; `new_dates` is an iterable
    of YYYY-MM-DD strings from the new trades.

    Returns an updated copy of the price map.
    """
    prices = dict(existing_prices) if existing_prices else {}
    missing = sorted(set(new_dates) - set(prices.keys()))
    if not missing:
        return prices

    # For a handful of missing days (the common case), one Kraken call
    # covering the earliest missing day is enough.
    earliest_dt = datetime.strptime(missing[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    since = int((earliest_dt - timedelta(days=2)).timestamp())

    try:
        r = requests.get(
            "https://api.kraken.com/0/public/OHLC",
            params={"pair": "SOLUSD", "interval": 1440, "since": since},
            timeout=15
        ).json()
        candles = r.get("result", {}).get("SOLUSD", [])
        for c in candles:
            ds = datetime.fromtimestamp(c[0], tz=timezone.utc).strftime("%Y-%m-%d")
            prices[ds] = float(c[4])
    except Exception:
        pass

    return prices


def get_sol_price(prices, date_str):
    """Lookup with ±2 day fallback (ported from process_wallet.py)."""
    if date_str in prices:
        return prices[date_str]
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    for d in [1, -1, 2, -2]:
        ds = (dt + timedelta(days=d)).strftime("%Y-%m-%d")
        if ds in prices:
            return prices[ds]
    return None


# ════════════════════════════════════════════════════════════════════
# STEP 3 — PARSE TRADES (ported from process_wallet.py)
# ════════════════════════════════════════════════════════════════════
def parse_trade(txn, wallet, sol_prices):
    """
    Ported from process_wallet.py parse_trade(). The only change:
    price lookups go through the passed-in sol_prices dict rather than
    a module-level global.
    """
    ts = txn["timestamp"]
    dt_obj = datetime.fromtimestamp(ts, tz=timezone.utc)
    date_str = dt_obj.strftime("%Y-%m-%d")
    tt = txn.get("tokenTransfers", [])

    native_sol = 0
    for a in txn.get("accountData", []):
        if a.get("account") == wallet:
            native_sol = a.get("nativeBalanceChange", 0) / 1e9
            break

    wsol_out = sum(
        x["tokenAmount"] for x in tt
        if x.get("mint") == WSOL
        and x.get("fromUserAccount") == wallet
        and x.get("tokenAmount", 0) > 0
    )
    wsol_in = sum(
        x["tokenAmount"] for x in tt
        if x.get("mint") == WSOL
        and x.get("toUserAccount") == wallet
        and x.get("tokenAmount", 0) > 0
    )

    eff_sol_out = wsol_out if wsol_out > abs(native_sol) * 2 else abs(native_sol)
    eff_sol_in = wsol_in if wsol_in > abs(native_sol) * 2 else 0

    result = {
        "signature": txn["signature"],
        "timestamp": ts,
        "datetime_utc": dt_obj.strftime("%Y-%m-%d %H:%M:%S"),
        "date": date_str,
        "month": dt_obj.strftime("%Y-%m"),
        "day_of_week": dt_obj.strftime("%A"),
        "hour_utc": dt_obj.hour,
        "dex": txn.get("source", "UNKNOWN"),
        "action": None,
        "token_mint": None,
        "token_amount": None,
        "sol_amount": abs(native_sol),
        "sol_price": None,
        "usd_value": None,
        "payment_currency": "SOL",
        "is_first_buy": False,
    }

    # Method 1: events.swap
    swap = txn.get("events", {}).get("swap", {})
    if swap:
        for t in swap.get("tokenInputs", []):
            if t.get("userAccount") == wallet and t["mint"] not in EXCLUDE_MINTS:
                dec = t["rawTokenAmount"]["decimals"]
                result.update({
                    "action": "SELL",
                    "token_mint": t["mint"],
                    "token_amount": abs(int(t["rawTokenAmount"]["tokenAmount"])) / (10 ** dec),
                    "sol_amount": eff_sol_in if eff_sol_in > abs(native_sol) else abs(native_sol),
                })
                break
        if not result["action"]:
            for t in swap.get("tokenOutputs", []):
                if t.get("userAccount") == wallet and t["mint"] not in EXCLUDE_MINTS:
                    dec = t["rawTokenAmount"]["decimals"]
                    result.update({
                        "action": "BUY",
                        "token_mint": t["mint"],
                        "token_amount": abs(int(t["rawTokenAmount"]["tokenAmount"])) / (10 ** dec),
                        "sol_amount": eff_sol_out if eff_sol_out > abs(native_sol) else abs(native_sol),
                    })
                    break

    # Method 2: tokenTransfers + SOL/WSOL
    if not result["action"]:
        rcv = [x for x in tt
               if x.get("toUserAccount") == wallet
               and x.get("mint") not in EXCLUDE_MINTS
               and x.get("tokenAmount", 0) > 0]
        snt = [x for x in tt
               if x.get("fromUserAccount") == wallet
               and x.get("mint") not in EXCLUDE_MINTS
               and x.get("tokenAmount", 0) > 0]

        if rcv and (native_sol < -0.0001 or wsol_out > 0.0001):
            result.update({
                "action": "BUY",
                "token_mint": rcv[0]["mint"],
                "token_amount": rcv[0]["tokenAmount"],
                "sol_amount": eff_sol_out,
            })
        elif snt and (native_sol > 0.0001 or wsol_in > 0.0001):
            result.update({
                "action": "SELL",
                "token_mint": snt[0]["mint"],
                "token_amount": snt[0]["tokenAmount"],
                "sol_amount": eff_sol_in if eff_sol_in > 0 else abs(native_sol),
            })

    # DFlow override
    if result["action"] and result["sol_amount"] < 1.0:
        all_stable = [x for x in tt
                      if x.get("mint") in STABLECOIN_MINTS
                      and x.get("tokenAmount", 0) > 1.0]
        if all_stable:
            usdc_amt = max(x["tokenAmount"] for x in all_stable)
            sol_price = get_sol_price(sol_prices, date_str) or 88
            result.update({
                "sol_amount": usdc_amt / sol_price,
                "usd_value": round(usdc_amt, 2),
                "payment_currency": "USDC",
            })

    # Method 3: pure stablecoin swap
    if not result["action"]:
        rcv = [x for x in tt
               if x.get("toUserAccount") == wallet
               and x.get("mint") not in EXCLUDE_MINTS
               and x.get("tokenAmount", 0) > 0]
        snt = [x for x in tt
               if x.get("fromUserAccount") == wallet
               and x.get("mint") not in EXCLUDE_MINTS
               and x.get("tokenAmount", 0) > 0]

        stable_out = [x for x in tt
                      if x.get("fromUserAccount") == wallet
                      and x.get("mint") in STABLECOIN_MINTS
                      and x.get("tokenAmount", 0) > 0]
        stable_in = [x for x in tt
                     if x.get("toUserAccount") == wallet
                     and x.get("mint") in STABLECOIN_MINTS
                     and x.get("tokenAmount", 0) > 0]

        if not stable_out and not stable_in:
            all_stable = [x for x in tt
                          if x.get("mint") in STABLECOIN_MINTS
                          and x.get("tokenAmount", 0) > 1.0]
            if all_stable:
                biggest = max(all_stable, key=lambda x: x["tokenAmount"])
                if rcv:
                    stable_out = [biggest]
                elif snt:
                    stable_in = [biggest]

        if rcv and stable_out:
            usdc_spent = sum(x["tokenAmount"] for x in stable_out)
            sol_price = get_sol_price(sol_prices, date_str) or 88
            result.update({
                "action": "BUY",
                "token_mint": rcv[0]["mint"],
                "token_amount": rcv[0]["tokenAmount"],
                "sol_amount": usdc_spent / sol_price,
                "usd_value": round(usdc_spent, 2),
                "payment_currency": "USDC",
            })
        elif snt and stable_in:
            usdc_rcv = sum(x["tokenAmount"] for x in stable_in)
            sol_price = get_sol_price(sol_prices, date_str) or 88
            result.update({
                "action": "SELL",
                "token_mint": snt[0]["mint"],
                "token_amount": snt[0]["tokenAmount"],
                "sol_amount": usdc_rcv / sol_price,
                "usd_value": round(usdc_rcv, 2),
                "payment_currency": "USDC",
            })

    if not result["action"] or not result["token_mint"]:
        return None
    if result["payment_currency"] == "SOL" and result["sol_amount"] < 0.0001:
        return None

    if result["usd_value"] is None:
        sol_price = get_sol_price(sol_prices, date_str)
        result["sol_price"] = sol_price
        result["usd_value"] = round(result["sol_amount"] * sol_price, 2) if sol_price else None
    else:
        result["sol_price"] = get_sol_price(sol_prices, date_str)

    return result


# ════════════════════════════════════════════════════════════════════
# STEP 4 — FLAG FIRST BUYS + DUST FILTER + BUILD POSITIONS
# ════════════════════════════════════════════════════════════════════
def finalise_trades(trades):
    """
    Full re-sort + re-flag of is_first_buy + dust removal.
    Runs on the merged (old + new) trades list because a new early buy
    could theoretically change which trade is the 'first real buy' for
    a given mint — safer to rebuild than to patch.
    """
    trades = sorted(trades, key=lambda x: x["timestamp"])

    buys_by_mint = defaultdict(list)
    for t in trades:
        if t["action"] == "BUY":
            buys_by_mint[t["token_mint"]].append(t)

    first_real_sigs = {}
    for mint, mint_buys in buys_by_mint.items():
        sorted_buys = sorted(mint_buys, key=lambda x: x["timestamp"])
        non_dust = [b for b in sorted_buys
                    if (b.get("usd_value") or 0) >= DUST_USD
                    or b.get("sol_amount", 0) >= DUST_SOL]
        chosen = non_dust[0] if non_dust else sorted_buys[0]
        first_real_sigs[mint] = chosen["signature"]

    for t in trades:
        t["is_first_buy"] = (
            t["action"] == "BUY"
            and first_real_sigs.get(t["token_mint"]) == t["signature"]
        )

    trades = [
        t for t in trades
        if t["is_first_buy"]
        or (t.get("usd_value") or 0) >= DUST_USD
        or t.get("sol_amount", 0) >= DUST_SOL
    ]
    return trades


def build_positions(trades, prev_positions=None):
    """
    Rebuild positions from scratch. Preserves mc_at_first_buy,
    mc_bucket_at_buy, and total_supply from prev_positions when the
    mint already exists — those never change and we don't want to
    re-query Helius RPC for them.
    """
    prev_by_mint = {p["mint"]: p for p in (prev_positions or [])}

    buys_map = defaultdict(list)
    sells_map = defaultdict(list)
    for t in trades:
        if t["action"] == "BUY":
            buys_map[t["token_mint"]].append(t)
        else:
            sells_map[t["token_mint"]].append(t)

    positions = []
    for mint in set(buys_map) | set(sells_map):
        b = sorted(buys_map[mint], key=lambda x: x["timestamp"])
        s = sorted(sells_map[mint], key=lambda x: x["timestamp"])

        sol_in = sum(x["sol_amount"] for x in b)
        sol_out = sum(x["sol_amount"] for x in s)
        buy_usd = sum(x["usd_value"] for x in b if x.get("usd_value")) or None
        sell_usd = sum(x["usd_value"] for x in s if x.get("usd_value")) or None
        pnl_sol = sol_out - sol_in
        pnl_usd = None
        if buy_usd and sell_usd:
            pnl_usd = sell_usd - buy_usd
        elif sell_usd and not b:
            pnl_usd = sell_usd

        remaining = max(0,
            sum(x["token_amount"] for x in b if x.get("token_amount")) -
            sum(x["token_amount"] for x in s if x.get("token_amount"))
        )

        if b and s:
            status = "CLOSED"
        elif b:
            status = "OPEN BUY"
        else:
            status = "OPEN SELL"

        prev = prev_by_mint.get(mint, {})

        positions.append({
            "mint": mint,
            # Preserve these — they're stable or will be refreshed by enrichment
            "token_name": prev.get("token_name"),
            "token_symbol": prev.get("token_symbol"),
            "status": status,
            "num_buys": len(b),
            "num_sells": len(s),
            "sol_in": round(sol_in, 4),
            "sol_out": round(sol_out, 4),
            "pnl_sol": round(pnl_sol, 4),
            "buy_usd": round(buy_usd, 2) if buy_usd else None,
            "sell_usd": round(sell_usd, 2) if sell_usd else None,
            "pnl_usd": round(pnl_usd, 2) if pnl_usd else None,
            "first_buy": b[0]["datetime_utc"] if b else None,
            "last_sell": s[-1]["datetime_utc"] if s else None,
            "remaining_tokens": round(remaining, 2),
            # These are immutable per mint — preserve from previous run
            "mc_at_first_buy": prev.get("mc_at_first_buy"),
            "mc_bucket_at_buy": prev.get("mc_bucket_at_buy"),
            "total_supply": prev.get("total_supply"),
            # These get refreshed in enrichment step
            "mc_bucket": prev.get("mc_bucket"),
            "market_cap_usd": prev.get("market_cap_usd"),
            "current_price_usd": prev.get("current_price_usd"),
            "unrealized_pnl_usd": prev.get("unrealized_pnl_usd"),
        })

    return positions


# ════════════════════════════════════════════════════════════════════
# STEP 5 — DEXSCREENER ENRICHMENT
# ════════════════════════════════════════════════════════════════════
def mc_bucket(mc):
    if not mc:         return "Unknown"
    if mc < 4_000:     return "<4K"
    if mc < 10_000:    return "4K-9K"
    if mc < 20_000:    return "10K-19K"
    if mc < 30_000:    return "20K-29K"
    if mc < 100_000:   return "30K-99K"
    if mc < 1_000_000: return "100K-999K"
    return "1M+"


def _fetch_dexscreener_batch(mints):
    try:
        r = requests.get(
            f"https://api.dexscreener.com/tokens/v1/solana/{','.join(mints)}",
            timeout=15
        ).json()
        out = {}
        for pair in (r if isinstance(r, list) else []):
            mint = pair.get("baseToken", {}).get("address")
            if not mint:
                continue
            existing_liq = out[mint].get("liquidity", {}).get("usd", 0) if mint in out else 0
            new_liq = pair.get("liquidity", {}).get("usd", 0)
            if new_liq >= existing_liq:
                out[mint] = pair
        return out
    except Exception:
        return {}


def enrich_positions(positions, progress_cb=None):
    """Refresh current price, MC, and unrealised P&L for all positions."""
    pos_by_mint = {p["mint"]: p for p in positions}
    mints_list = list(pos_by_mint.keys())
    enriched = 0

    for i in range(0, len(mints_list), 30):
        batch = mints_list[i:i + 30]
        result = _fetch_dexscreener_batch(batch)

        for mint in batch:
            pair = result.get(mint)
            pos = pos_by_mint[mint]
            if not pair:
                continue

            base = pair.get("baseToken", {})
            px = float(pair.get("priceUsd") or 0)
            mc = pair.get("marketCap") or pair.get("fdv")

            pos["token_name"] = base.get("name")
            pos["token_symbol"] = base.get("symbol")
            pos["current_price_usd"] = px if px > 0 else None
            pos["market_cap_usd"] = mc
            pos["mc_bucket"] = mc_bucket(mc)

            if pos["remaining_tokens"] and px:
                net_cost = (pos["buy_usd"] or 0) - (pos["sell_usd"] or 0)
                pos["unrealized_pnl_usd"] = round(
                    pos["remaining_tokens"] * px - net_cost, 2
                )
            enriched += 1

        if progress_cb and (i // 30 + 1) % 10 == 0:
            progress_cb(f"DexScreener: {min(i + 30, len(mints_list))}/{len(mints_list)}")
        time.sleep(0.5)

    return enriched


# ════════════════════════════════════════════════════════════════════
# STEP 6 — MC AT FIRST BUY (only for new mints)
# ════════════════════════════════════════════════════════════════════
def enrich_mc_at_first_buy(positions, trades, api_key, sol_prices,
                           progress_cb=None):
    """
    Compute MC at first buy ONLY for positions that don't already have it.
    This is the main cost-saver of incremental mode — existing mints
    keep their cached value and never re-query Helius RPC.
    """
    rpc_url = f"https://mainnet.helius-rpc.com/?api-key={api_key}"
    pos_by_mint = {p["mint"]: p for p in positions}

    # Only process mints missing mc_at_first_buy
    first_buys = {t["token_mint"]: t for t in trades if t.get("is_first_buy")}
    to_process = [
        (mint, fb) for mint, fb in first_buys.items()
        if pos_by_mint.get(mint) and pos_by_mint[mint].get("mc_at_first_buy") is None
    ]

    if not to_process:
        return 0

    updated = 0
    for i, (mint, fb) in enumerate(to_process):
        pos = pos_by_mint.get(mint)
        if not pos:
            continue
        if not fb.get("token_amount") or fb["token_amount"] <= 0:
            continue

        if fb.get("payment_currency") == "USDC" and fb.get("usd_value"):
            usd_paid = fb["usd_value"]
        else:
            sp = get_sol_price(sol_prices, fb["date"])
            if not sp:
                continue
            usd_paid = fb["sol_amount"] * sp

        try:
            r = requests.post(
                rpc_url,
                json={"jsonrpc": "2.0", "id": 1,
                      "method": "getTokenSupply",
                      "params": [mint]},
                timeout=10
            )
            supply = float(r.json()["result"]["value"].get("uiAmount") or 0)
            if supply > 0 and fb["token_amount"] > 0:
                token_price = usd_paid / fb["token_amount"]
                mc = token_price * supply
                pos["total_supply"] = supply
                pos["mc_at_first_buy"] = round(mc, 2)
                pos["mc_bucket_at_buy"] = mc_bucket(mc)
                updated += 1
        except Exception:
            pass

        time.sleep(0.04)
        if progress_cb and (i + 1) % 50 == 0:
            progress_cb(f"MC at buy: {i + 1}/{len(to_process)}")

    return updated


# ════════════════════════════════════════════════════════════════════
# TOP-LEVEL: update_wallet_data
# ════════════════════════════════════════════════════════════════════
def update_wallet_data(wallet_json, api_key, progress_cb=None):
    """
    Take an existing wallet JSON dict and incrementally update it with
    any new swaps. Returns (updated_dict, stats) where stats has counts
    for the user-facing success message.

    This is the one function the dashboard calls.
    """
    stats = {
        "new_txns": 0,
        "new_trades": 0,
        "new_mints": 0,
        "mc_updated": 0,
        "error": None,
    }

    wallet = wallet_json.get("wallet")
    if not wallet:
        stats["error"] = "Wallet address missing from JSON"
        return wallet_json, stats

    existing_trades = wallet_json.get("trades", [])
    existing_positions = wallet_json.get("positions", [])
    existing_prices = wallet_json.get("sol_prices", {})

    # Determine last_signature. If the JSON doesn't have one yet (old
    # bootstrap), derive it from the newest trade.
    last_sig = wallet_json.get("last_signature")
    if not last_sig and existing_trades:
        newest = max(existing_trades, key=lambda t: t["timestamp"])
        last_sig = newest.get("signature")

    # STEP 1: fetch new txns
    if progress_cb:
        progress_cb("Fetching new transactions from Helius...")
    new_txns = fetch_new_transactions(wallet, api_key, last_signature=last_sig,
                                      progress_cb=progress_cb)
    stats["new_txns"] = len(new_txns)

    # If no new txns, we still refresh DexScreener prices (MC/unrealised
    # P&L are time-sensitive even without new trades).
    if not new_txns:
        if progress_cb:
            progress_cb("No new trades — refreshing token prices only...")
        enrich_positions(existing_positions, progress_cb=progress_cb)
        wallet_json["positions"] = existing_positions
        wallet_json["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        return wallet_json, stats

    # STEP 2: fetch missing SOL prices for the new trade dates
    new_dates = {
        datetime.fromtimestamp(t["timestamp"], tz=timezone.utc).strftime("%Y-%m-%d")
        for t in new_txns
    }
    sol_prices = fetch_missing_sol_prices(existing_prices, new_dates)

    # STEP 3: parse new trades
    new_trades = []
    for txn in new_txns:
        parsed = parse_trade(txn, wallet, sol_prices)
        if parsed:
            new_trades.append(parsed)
    stats["new_trades"] = len(new_trades)

    # STEP 4: merge, dedupe by signature, re-sort, re-flag first_buy, dust filter
    seen_sigs = {t["signature"] for t in existing_trades}
    merged = existing_trades + [t for t in new_trades if t["signature"] not in seen_sigs]
    merged = finalise_trades(merged)

    # STEP 5: rebuild positions (preserves mc_at_first_buy where present)
    prev_mints = {p["mint"] for p in existing_positions}
    positions = build_positions(merged, prev_positions=existing_positions)
    stats["new_mints"] = len([p for p in positions if p["mint"] not in prev_mints])

    # STEP 6: enrich with DexScreener (all positions, prices move)
    if progress_cb:
        progress_cb("Refreshing token prices (DexScreener)...")
    enrich_positions(positions, progress_cb=progress_cb)

    # STEP 7: MC at first buy ONLY for new mints
    if progress_cb:
        progress_cb("Computing MC at first buy for new mints...")
    stats["mc_updated"] = enrich_mc_at_first_buy(
        positions, merged, api_key, sol_prices, progress_cb=progress_cb
    )

    # STEP 8: compose updated JSON
    newest_ts = max(t["timestamp"] for t in merged)
    oldest_ts = min(t["timestamp"] for t in merged)
    newest_sig = max(merged, key=lambda t: t["timestamp"])["signature"]

    wallet_json.update({
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "date_from": datetime.fromtimestamp(oldest_ts, tz=timezone.utc).strftime("%Y-%m-%d"),
        "date_to": datetime.fromtimestamp(newest_ts, tz=timezone.utc).strftime("%Y-%m-%d"),
        "total_trades": len(merged),
        "positions": positions,
        "trades": merged,
        "sol_prices": sol_prices,
        "last_signature": newest_sig,
    })

    return wallet_json, stats
