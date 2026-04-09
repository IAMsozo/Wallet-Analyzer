# Solana Wallet Trade Analyzer

A Solana wallet trade analyzer with a bootstrap pipeline (Colab) and an
interactive dashboard (Streamlit Cloud) that can fetch new swaps
incrementally — no re-running Colab for every refresh.

## Architecture

```
┌──────────────────────┐     Google Drive      ┌───────────────────────┐
│  process_wallet.py   │ ─── wallet_*.json ──▶ │  wallet_dashboard.py  │
│  (Google Colab)      │      (bootstrap)      │  (Streamlit Cloud)    │
│  Full history fetch  │                       │  + pipeline.py        │
│  Run once per wallet │                       │  Incremental updates  │
└──────────────────────┘                       └───────────────────────┘
                                                        │
                                                        ▼
                                                 Helius (new swaps)
                                                 DexScreener (prices)
```

- **Colab** does the initial full-history fetch (expensive, once per wallet)
- **Dashboard** fetches only new swaps since the last update (cheap, on-demand)
- **Helius API key** lives in Streamlit Secrets (never in GitHub)
- **Wallet data** lives in Google Drive for bootstrap, Streamlit local disk for runtime

## How incremental fetch works

When you click **⚡ Fetch New** in the dashboard:

1. Reads the stored `last_signature` from the wallet JSON
2. Walks Helius transaction history newest → oldest, stopping when it
   hits that signature — so only genuinely new txns are fetched
3. Parses new trades using the same logic as Colab bootstrap
4. Merges + dedupes with existing trades, rebuilds positions
5. Refreshes DexScreener prices for all tokens (prices move constantly)
6. Computes MC-at-first-buy **only for newly-seen mints** — the
   expensive Helius RPC step is skipped for tokens already processed
7. Saves updated JSON to local disk

Typical refresh cost: a handful of Helius calls, a few DexScreener
batches, and zero RPC calls if no new mints appeared. Seconds, not minutes.

## Setup

### 1. Bootstrap a wallet (Google Colab — run once per wallet)

1. Upload `process_wallet.py` to Google Colab
2. Install dependencies: `!pip install requests`
3. Edit the 3 config lines at the top:
   ```python
   API_KEY = "your-helius-api-key"
   WALLET  = "your-solana-wallet-address"
   PERIOD  = "ALL"  # 1M / 3M / 6M / 1Y / 2Y / ALL
   ```
4. Run the script — it outputs `wallet_XXXXXXXX_ALL.json`
5. Upload the JSON to Google Drive
6. Set sharing to **"Anyone with the link"**
7. Copy the file ID from the share URL:
   `https://drive.google.com/file/d/THIS_PART/view`

### 2. Dashboard (Streamlit Cloud)

Repo files:
- `wallet_dashboard.py`
- `pipeline.py` ← new, required for incremental fetch
- `requirements.txt`
- `README.md`
- `.gitignore`

Configure wallets in `wallet_dashboard.py`:
```python
DRIVE_WALLETS = {
    "My Wallet": "paste-google-drive-file-id-here",
}
```

Push to GitHub, then on [share.streamlit.io](https://share.streamlit.io):

1. **New app** → select repo → main file `wallet_dashboard.py` → **Deploy**
2. Once deployed, go to **Settings → Secrets** and add:
   ```toml
   HELIUS_API_KEY = "your-helius-api-key"
   ```
3. Save. The app will restart and the ⚡ Fetch New button will work.

Your dashboard is live at `https://yourapp.streamlit.app`.

### 3. Day-to-day usage

- **⚡ Fetch New** — pulls new swaps from Helius since last update.
  Use this for normal refreshes. Fast and cheap.
- **🔄 Reload** — re-downloads the wallet JSON from Google Drive,
  discarding any incremental updates. Use this only if you've
  re-bootstrapped in Colab and pushed a fresh JSON to Drive.

### Container recycles

Streamlit Cloud containers can be recycled, which wipes local files.
When this happens the dashboard automatically re-downloads from Drive
on next load. You'll lose any incremental updates made since the last
Drive upload, but one click of **⚡ Fetch New** will catch back up.

## Adding More Wallets

Bootstrap the new wallet in Colab, upload to Drive, then add one line:

```python
DRIVE_WALLETS = {
    "Main Wallet": "abc123fileID",
    "Alt Wallet":  "xyz789fileID",  # ← new wallet
}
```

Push to GitHub — Streamlit Cloud auto-redeploys.

## Wallet Types Supported

- ✅ Native SOL wallets
- ✅ WSOL wallets (Pump.fun AMM, Jupiter)
- ✅ USDC-funded wallets
- ✅ DFlow aggregator wallets (solver-pays-USDC)
- ✅ Mixed wallets
- ❌ Token-to-token swaps not via SOL/WSOL/stablecoins

## Accuracy Notes

- MC at buy uses **current** token supply (understated for tokens that burned supply)
- USD values use daily SOL close price (~1-3% error per trade)
- Dead tokens with no DexScreener price show $0 unrealised
- Helius Enhanced API occasionally omits transactions — cross-check on GMGN/Solscan

## Dashboard Tabs

| Tab | Contents |
|-----|----------|
| P&L Overview | Cumulative P&L chart, monthly bars, yearly metrics, period filters |
| Trade History | Filterable/sortable trade list with first-buy flags, MC at trade |
| Positions | All positions with P&L, ROI, MC bucket, days held |
| Time Analysis | Day-of-week P&L, hour×day heatmap, hourly P&L |
| MC Analysis | P&L and win rate by market cap bucket at entry |
| Open Positions | In Profit / In Loss subtabs with unrealised P&L |

## Tech Stack

- **Bootstrap pipeline**: Python, Helius API, Kraken API, CryptoCompare, DexScreener
- **Incremental pipeline**: `pipeline.py` (same sources, delta-fetch)
- **Dashboard**: Streamlit, Plotly, pandas
- **Storage**: Google Drive (bootstrap), Streamlit local disk (runtime)
- **Hosting**: Streamlit Community Cloud (free)

## Security

- Helius API key is stored in Streamlit Secrets — never committed to GitHub
- Wallet JSON files live in Google Drive (anyone-with-link) and locally in
  the Streamlit container. Nothing sensitive is exposed in the repo.
- `pipeline.py` reads the key only when the user clicks **⚡ Fetch New**,
  and never logs or echoes it.
