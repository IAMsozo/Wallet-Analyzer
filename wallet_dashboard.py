"""
Solana Wallet Trade Analyzer — Dashboard
==========================================
Deploy to Streamlit Community Cloud from a public GitHub repo.
Contains ZERO API keys. Reads wallet_*.json from Google Drive.

To add a wallet: add one line to DRIVE_WALLETS below.
"""

import os
import json
import shutil
from datetime import datetime, timedelta

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import gdown

# ─────────────────────────────────────────────
# WALLET CONFIG — EDIT THIS DICT TO ADD WALLETS
# ─────────────────────────────────────────────
# Format: "Display Name": "Google Drive File ID"
# Get file ID from share link: https://drive.google.com/file/d/FILE_ID_HERE/view
DRIVE_WALLETS = {
    "Example Wallet": "PASTE_GOOGLE_DRIVE_FILE_ID_HERE",
    # "Wallet 2": "ANOTHER_FILE_ID",
}

CACHE_DIR = "wallet_data"

# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────
DUST_USD = 1.0
DUST_SOL = 0.01

MC_BUCKET_ORDER = [
    "Unknown", "<$10K", "$10K-$50K", "$50K-$100K",
    "$100K-$500K", "$500K-$1M", "$1M-$10M", ">$10M",
]

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Solana Wallet Analyzer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# CUSTOM STYLING
# ─────────────────────────────────────────────
st.markdown("""
<style>
    /* Dark theme overrides */
    .stApp { background-color: #0e1117; }
    .metric-card {
        background: linear-gradient(135deg, #1a1f2e 0%, #151922 100%);
        border: 1px solid #2d3548;
        border-radius: 12px;
        padding: 16px 20px;
        text-align: center;
    }
    .metric-label {
        color: #8b95a5;
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 4px;
    }
    .metric-value {
        font-size: 1.5rem;
        font-weight: 700;
        color: #e2e8f0;
    }
    .metric-value.positive { color: #22c55e; }
    .metric-value.negative { color: #ef4444; }
    .first-buy-badge {
        background: #22c55e22;
        color: #22c55e;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    div[data-testid="stDataFrame"] { font-size: 0.85rem; }
    .accuracy-note {
        background: #1e293b;
        border-left: 3px solid #f59e0b;
        padding: 12px 16px;
        border-radius: 0 8px 8px 0;
        font-size: 0.82rem;
        color: #94a3b8;
        margin-top: 16px;
    }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# DATA LOADING
# ─────────────────────────────────────────────
def download_from_drive(file_id, dest_path):
    """Download a file from Google Drive via gdown."""
    url = f"https://drive.google.com/uc?id={file_id}"
    try:
        gdown.download(url, dest_path, quiet=True)
        return os.path.exists(dest_path)
    except Exception as e:
        st.error(f"Failed to download from Drive: {e}")
        return False

@st.cache_data
def load_data(filepath: str):
    """Load and prepare wallet JSON into DataFrames."""
    with open(filepath, "r") as f:
        raw = json.load(f)

    wallet_addr = raw.get("wallet", "unknown")
    generated_at = raw.get("generated_at", "")
    period = raw.get("period", "ALL")

    # --- Trades DataFrame ---
    trades_raw = raw.get("trades", [])
    if trades_raw:
        df_trades = pd.DataFrame(trades_raw)
    else:
        df_trades = pd.DataFrame()

    if not df_trades.empty:
        # Numeric safety
        num_cols = ["sol_amount", "usd_value", "token_amount", "sol_price",
                    "mc_at_trade", "current_price", "current_mc"]
        for c in num_cols:
            if c in df_trades.columns:
                df_trades[c] = pd.to_numeric(df_trades[c], errors="coerce").fillna(0)

        # Datetime safety — normalize to tz-naive UTC
        if "datetime" in df_trades.columns:
            df_trades["datetime"] = pd.to_datetime(
                df_trades["datetime"], utc=True
            ).dt.tz_convert(None)
        elif "timestamp" in df_trades.columns:
            df_trades["datetime"] = pd.to_datetime(
                df_trades["timestamp"], unit="s", utc=True
            ).dt.tz_convert(None)

        # Ensure is_first_buy
        if "is_first_buy" not in df_trades.columns:
            df_trades["is_first_buy"] = False

    # --- Positions DataFrame ---
    positions_raw = raw.get("positions", [])
    if positions_raw:
        df_positions = pd.DataFrame(positions_raw)
    else:
        df_positions = pd.DataFrame()

    if not df_positions.empty:
        num_cols_pos = ["sol_in", "sol_out", "buy_usd", "sell_usd",
                        "pnl_sol", "pnl_usd", "remaining_tokens",
                        "current_price", "current_value", "unrealized_usd",
                        "mc_at_buy", "current_mc", "roi",
                        "tokens_bought", "tokens_sold"]
        for c in num_cols_pos:
            if c in df_positions.columns:
                df_positions[c] = pd.to_numeric(df_positions[c], errors="coerce").fillna(0)

        for dtcol in ["first_buy_dt", "last_sell_dt"]:
            if dtcol in df_positions.columns:
                df_positions[dtcol] = pd.to_datetime(
                    df_positions[dtcol], utc=True, errors="coerce"
                ).dt.tz_convert(None)

        # Compute days_held live
        now_ts = pd.Timestamp.utcnow().tz_localize(None)
        df_positions["days_held"] = df_positions.apply(
            lambda r: max(0, (
                (r["last_sell_dt"] - r["first_buy_dt"]).days
                if pd.notna(r.get("last_sell_dt")) and pd.notna(r.get("first_buy_dt"))
                else (now_ts - r["first_buy_dt"]).days
                if pd.notna(r.get("first_buy_dt"))
                else 0
            )), axis=1
        )

        # MC bucket ordering
        if "mc_bucket" in df_positions.columns:
            df_positions["mc_bucket"] = pd.Categorical(
                df_positions["mc_bucket"],
                categories=MC_BUCKET_ORDER,
                ordered=True,
            )

    summary = raw.get("summary", {})

    return {
        "wallet": wallet_addr,
        "generated_at": generated_at,
        "period": period,
        "trades": df_trades,
        "positions": df_positions,
        "summary": summary,
    }

# ─────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────
def fmt_val(v, use_usd=True, prefix=True):
    """Format a value as USD or SOL with sign."""
    if pd.isna(v) or v == 0:
        return "$0" if use_usd else "0 SOL"
    sign = "+" if v > 0 else ""
    if use_usd:
        if abs(v) >= 1_000_000:
            return f"{sign}${v / 1_000_000:,.2f}M"
        if abs(v) >= 1_000:
            return f"{sign}${v:,.0f}"
        return f"{sign}${v:,.2f}"
    else:
        return f"{sign}{v:,.2f} SOL"

def color_class(v):
    if v > 0:
        return "positive"
    if v < 0:
        return "negative"
    return ""

def metric_card(label, value, is_numeric=True, val_class=""):
    """Render a styled metric card."""
    return f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div class="metric-value {val_class}">{value}</div>
    </div>
    """

def filter_by_period(df, period_key, custom_range=None):
    """Filter DataFrame by time period."""
    if "datetime" not in df.columns or df.empty:
        return df
    now = pd.Timestamp.utcnow().tz_localize(None)
    mapping = {
        "1D": timedelta(days=1),
        "7D": timedelta(days=7),
        "1M": timedelta(days=30),
        "1Y": timedelta(days=365),
    }
    if period_key == "Custom" and custom_range:
        start = pd.Timestamp(custom_range[0])
        end = pd.Timestamp(custom_range[1]) + timedelta(days=1)
        return df[(df["datetime"] >= start) & (df["datetime"] < end)]
    if period_key == "All":
        return df
    delta = mapping.get(period_key)
    if delta:
        cutoff = now - delta
        return df[df["datetime"] >= cutoff]
    return df

def gmgn_link(mint, symbol):
    """Create a GMGN.ai link for a token."""
    url = f"https://gmgn.ai/sol/token/{mint}"
    return f"[{symbol}]({url})"

# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────
with st.sidebar:
    st.title("📊 Wallet Analyzer")
    st.caption("Solana Trade Dashboard")

    # Wallet selector
    wallet_names = list(DRIVE_WALLETS.keys())
    if not wallet_names:
        st.error("No wallets configured. Add entries to DRIVE_WALLETS.")
        st.stop()

    selected_name = st.selectbox("Wallet", wallet_names)
    file_id = DRIVE_WALLETS[selected_name]

    # Refresh button
    if st.button("🔄 Refresh Data from Drive"):
        if os.path.exists(CACHE_DIR):
            shutil.rmtree(CACHE_DIR)
        st.cache_data.clear()
        st.rerun()

    # USD / SOL toggle
    currency = st.radio("Currency", ["USD", "SOL"], horizontal=True)
    USE_USD = currency == "USD"

    st.divider()
    st.markdown("""
    <div class="accuracy-note">
        <strong>⚠️ Accuracy Notes</strong><br>
        • MC at buy uses current supply (understated for tokens that burned supply)<br>
        • USD values use daily SOL close (~1-3% error)<br>
        • Dead tokens show $0 unrealised<br>
        • Token-to-token swaps not via SOL/stablecoins are missing<br>
        • Cross-check high-value positions on GMGN/Solscan
    </div>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────
# LOAD DATA
# ─────────────────────────────────────────────
os.makedirs(CACHE_DIR, exist_ok=True)
cache_path = os.path.join(CACHE_DIR, f"{selected_name.replace(' ', '_')}.json")

if not os.path.exists(cache_path):
    with st.spinner("Downloading wallet data from Google Drive..."):
        success = download_from_drive(file_id, cache_path)
        if not success:
            st.error("Could not download wallet data. Check Drive file ID and sharing settings.")
            st.stop()

data = load_data(cache_path)
df_trades = data["trades"]
df_positions = data["positions"]
wallet_addr = data["wallet"]

st.sidebar.caption(f"Wallet: `{wallet_addr[:8]}...{wallet_addr[-4:]}`")
st.sidebar.caption(f"Data generated: {data['generated_at'][:19]}")

# ─────────────────────────────────────────────
# FILTER NON-DUST TRADES
# ─────────────────────────────────────────────
if not df_trades.empty:
    df_trades_clean = df_trades[
        (df_trades["usd_value"] >= DUST_USD) | (df_trades["sol_amount"] >= DUST_SOL)
    ].copy()
else:
    df_trades_clean = df_trades.copy()

# ─────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────
tab_pnl, tab_history, tab_positions, tab_time, tab_mc, tab_open = st.tabs([
    "📈 P&L Overview", "📋 Trade History", "💼 Positions",
    "🕐 Time Analysis", "🎯 MC Analysis", "🔓 Open Positions",
])

# ═════════════════════════════════════════════
# TAB 1: P&L OVERVIEW
# ═════════════════════════════════════════════
with tab_pnl:
    if df_trades_clean.empty:
        st.info("No trades found.")
    else:
        # Period filter
        period_cols = st.columns([1, 1, 1, 1, 1, 2])
        period_options = ["1D", "7D", "1M", "1Y", "All", "Custom"]
        period_key = "All"
        for i, opt in enumerate(period_options[:5]):
            if period_cols[i].button(opt, key=f"pnl_period_{opt}", use_container_width=True):
                st.session_state["pnl_period"] = opt
        custom_range = None
        with period_cols[5]:
            if st.button("Custom", key="pnl_period_custom", use_container_width=True):
                st.session_state["pnl_period"] = "Custom"
        period_key = st.session_state.get("pnl_period", "All")

        if period_key == "Custom":
            dr = st.date_input("Date range", value=[], key="pnl_custom_range")
            if len(dr) == 2:
                custom_range = dr
            else:
                st.caption("Select start and end dates.")

        filtered = filter_by_period(df_trades_clean, period_key, custom_range)

        if filtered.empty:
            st.info("No trades in selected period.")
        else:
            val_col = "usd_value" if USE_USD else "sol_amount"

            # Compute signed PnL per trade
            filtered = filtered.copy()
            filtered["signed_pnl"] = filtered.apply(
                lambda r: r[val_col] if r["action"] == "SELL" else -r[val_col], axis=1
            )
            filtered["cum_pnl"] = filtered["signed_pnl"].cumsum()

            # KPI metrics
            total_pnl = filtered["signed_pnl"].sum()
            num_trades = len(filtered)
            buys = filtered[filtered["action"] == "BUY"]
            sells = filtered[filtered["action"] == "SELL"]
            total_bought = buys[val_col].sum()
            total_sold = sells[val_col].sum()

            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.markdown(metric_card("Total P&L", fmt_val(total_pnl, USE_USD),
                                      val_class=color_class(total_pnl)), unsafe_allow_html=True)
            mc2.markdown(metric_card("Trades", str(num_trades)), unsafe_allow_html=True)
            mc3.markdown(metric_card("Total Bought", fmt_val(total_bought, USE_USD)),
                         unsafe_allow_html=True)
            mc4.markdown(metric_card("Total Sold", fmt_val(total_sold, USE_USD)),
                         unsafe_allow_html=True)

            # Cumulative P&L chart
            st.subheader("Cumulative P&L")
            fig_cum = go.Figure()
            fig_cum.add_trace(go.Scatter(
                x=filtered["datetime"],
                y=filtered["cum_pnl"],
                mode="lines",
                fill="tozeroy",
                line=dict(color="#22c55e" if total_pnl >= 0 else "#ef4444", width=2),
                fillcolor="rgba(34,197,94,0.1)" if total_pnl >= 0 else "rgba(239,68,68,0.1)",
            ))
            fig_cum.update_layout(
                template="plotly_dark",
                paper_bgcolor="#0e1117",
                plot_bgcolor="#0e1117",
                xaxis_title="",
                yaxis_title="USD" if USE_USD else "SOL",
                height=350,
                margin=dict(l=40, r=20, t=20, b=40),
            )
            st.plotly_chart(fig_cum, use_container_width=True)

            # Monthly P&L bar chart
            st.subheader("Monthly P&L")
            monthly = filtered.copy()
            monthly["month"] = monthly["datetime"].dt.to_period("M").astype(str)
            monthly_pnl = monthly.groupby("month")["signed_pnl"].sum().reset_index()
            monthly_pnl.columns = ["Month", "PnL"]
            monthly_pnl["color"] = monthly_pnl["PnL"].apply(
                lambda x: "#22c55e" if x >= 0 else "#ef4444"
            )
            fig_monthly = go.Figure(go.Bar(
                x=monthly_pnl["Month"],
                y=monthly_pnl["PnL"],
                marker_color=monthly_pnl["color"],
            ))
            fig_monthly.update_layout(
                template="plotly_dark",
                paper_bgcolor="#0e1117",
                plot_bgcolor="#0e1117",
                yaxis_title="USD" if USE_USD else "SOL",
                height=300,
                margin=dict(l=40, r=20, t=20, b=40),
            )
            st.plotly_chart(fig_monthly, use_container_width=True)

            # Yearly breakdown
            yearly = filtered.copy()
            yearly["year"] = yearly["datetime"].dt.year
            year_groups = yearly.groupby("year")
            st.subheader("Yearly Breakdown")
            year_cols = st.columns(min(len(year_groups), 5))
            for i, (year, grp) in enumerate(year_groups):
                if i >= 5:
                    break
                yr_pnl = grp["signed_pnl"].sum()
                yr_trades = len(grp)
                year_cols[i].markdown(
                    metric_card(str(year), fmt_val(yr_pnl, USE_USD),
                                val_class=color_class(yr_pnl)),
                    unsafe_allow_html=True,
                )

# ═════════════════════════════════════════════
# TAB 2: TRADE HISTORY
# ═════════════════════════════════════════════
with tab_history:
    if df_trades_clean.empty:
        st.info("No trades found.")
    else:
        fcol1, fcol2, fcol3 = st.columns([2, 2, 2])

        with fcol1:
            trade_filter = st.selectbox("Filter", [
                "All", "Buys Only", "Sells Only", "Unique Buys Only"
            ], key="hist_filter")

        with fcol2:
            sort_by = st.selectbox("Sort by", [
                "Time", "Amount", "ROI", "P&L"
            ], key="hist_sort")

        with fcol3:
            sort_dir = st.radio("Direction", ["↓ Desc", "↑ Asc"],
                                horizontal=True, key="hist_dir")
        ascending = sort_dir.startswith("↑")

        df_hist = df_trades_clean.copy()
        val_col = "usd_value" if USE_USD else "sol_amount"

        # Filter
        if trade_filter == "Buys Only":
            df_hist = df_hist[df_hist["action"] == "BUY"]
        elif trade_filter == "Sells Only":
            df_hist = df_hist[df_hist["action"] == "SELL"]
        elif trade_filter == "Unique Buys Only":
            df_hist = df_hist[df_hist["is_first_buy"] == True]

        # Compute display columns
        df_hist["Amount"] = df_hist[val_col].apply(lambda x: fmt_val(x, USE_USD, prefix=False))

        # Realised P&L (for sells: the usd_value; for buys: negative)
        df_hist["signed_pnl"] = df_hist.apply(
            lambda r: r[val_col] if r["action"] == "SELL" else -r[val_col], axis=1
        )
        df_hist["Realised P&L"] = df_hist["signed_pnl"].apply(lambda x: fmt_val(x, USE_USD))

        # Sort mapping
        sort_col_map = {
            "Time": "datetime",
            "Amount": val_col,
            "ROI": val_col,  # approximate; real ROI needs position context
            "P&L": "signed_pnl",
        }
        sc = sort_col_map.get(sort_by, "datetime")
        df_hist = df_hist.sort_values(sc, ascending=ascending)

        # Build display table
        display_cols = {
            "datetime": "Time",
            "action": "Action",
            "token_symbol": "Ticker",
            "mc_at_trade": "MC at Trade",
            "Amount": "Amount",
            "Realised P&L": "Realised P&L",
            "is_first_buy": "1st Buy",
            "method": "Method",
        }
        avail = [c for c in display_cols.keys() if c in df_hist.columns]
        df_show = df_hist[avail].copy()
        df_show = df_show.rename(columns=display_cols)

        if "MC at Trade" in df_show.columns:
            df_show["MC at Trade"] = df_show["MC at Trade"].apply(
                lambda x: f"${x:,.0f}" if x > 0 else "—"
            )
        if "Time" in df_show.columns:
            df_show["Time"] = df_show["Time"].dt.strftime("%Y-%m-%d %H:%M")
        if "1st Buy" in df_show.columns:
            df_show["1st Buy"] = df_show["1st Buy"].apply(lambda x: "✅" if x else "")

        st.dataframe(df_show, use_container_width=True, height=600, hide_index=True)
        st.caption(f"Showing {len(df_show)} trades (dust < ${DUST_USD} / {DUST_SOL} SOL hidden)")

# ═════════════════════════════════════════════
# TAB 3: POSITIONS
# ═════════════════════════════════════════════
with tab_positions:
    if df_positions.empty:
        st.info("No positions found.")
    else:
        pcol1, pcol2 = st.columns([3, 2])
        with pcol1:
            pos_sort = st.selectbox("Sort by", [
                "P&L", "ROI", "Buy Amount"
            ], key="pos_sort")
        with pcol2:
            pos_dir = st.radio("Direction", ["↓ Desc", "↑ Asc"],
                               horizontal=True, key="pos_dir")
        pos_asc = pos_dir.startswith("↑")

        df_pos = df_positions.copy()
        pnl_col = "pnl_usd" if USE_USD else "pnl_sol"
        buy_col = "buy_usd" if USE_USD else "sol_in"
        sell_col = "sell_usd" if USE_USD else "sol_out"

        sort_map = {
            "P&L": pnl_col,
            "ROI": "roi",
            "Buy Amount": buy_col,
        }
        df_pos = df_pos.sort_values(sort_map[pos_sort], ascending=pos_asc)

        # Build display
        df_pshow = pd.DataFrame()
        df_pshow["Name"] = df_pos["token_name"]
        df_pshow["Ticker"] = df_pos["token_symbol"]
        df_pshow["Status"] = df_pos["status"]
        df_pshow["MC at Buy"] = df_pos["mc_at_buy"].apply(
            lambda x: f"${x:,.0f}" if x > 0 else "—"
        )
        df_pshow["MC Bucket"] = df_pos["mc_bucket"].astype(str)
        df_pshow["Buys"] = df_pos["num_buys"]
        df_pshow["Sells"] = df_pos["num_sells"]
        df_pshow["Balance"] = df_pos["remaining_tokens"].apply(
            lambda x: f"{x:,.0f}" if x > 0 else "0"
        )
        df_pshow["Buy Amt"] = df_pos[buy_col].apply(lambda x: fmt_val(x, USE_USD))
        df_pshow["Sell Amt"] = df_pos[sell_col].apply(lambda x: fmt_val(x, USE_USD))
        df_pshow["P&L"] = df_pos[pnl_col].apply(lambda x: fmt_val(x, USE_USD))
        df_pshow["ROI"] = df_pos["roi"].apply(lambda x: f"{x:+,.1f}%")
        df_pshow["Days"] = df_pos["days_held"]
        df_pshow["First Buy"] = df_pos["first_buy_dt"].apply(
            lambda x: x.strftime("%Y-%m-%d") if pd.notna(x) else "—"
        )

        st.dataframe(df_pshow, use_container_width=True, height=600, hide_index=True)
        st.caption(f"Showing {len(df_pshow)} positions")

# ═════════════════════════════════════════════
# TAB 4: TIME ANALYSIS
# ═════════════════════════════════════════════
with tab_time:
    if df_trades_clean.empty:
        st.info("No trades found.")
    else:
        df_time = df_trades_clean.copy()
        val_col = "usd_value" if USE_USD else "sol_amount"
        df_time["signed_pnl"] = df_time.apply(
            lambda r: r[val_col] if r["action"] == "SELL" else -r[val_col], axis=1
        )
        df_time["dow"] = df_time["datetime"].dt.day_name()
        df_time["hour"] = df_time["datetime"].dt.hour

        # Day of Week P&L
        st.subheader("P&L by Day of Week")
        dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        dow_pnl = df_time.groupby("dow").agg(
            pnl=("signed_pnl", "sum"),
            trades=("signed_pnl", "count"),
            wins=("signed_pnl", lambda x: (x > 0).sum()),
        ).reindex(dow_order).fillna(0)
        dow_pnl["win_rate"] = (dow_pnl["wins"] / dow_pnl["trades"] * 100).fillna(0)
        dow_pnl = dow_pnl.reset_index()

        fig_dow = go.Figure(go.Bar(
            x=dow_pnl["dow"],
            y=dow_pnl["pnl"],
            marker_color=dow_pnl["pnl"].apply(
                lambda x: "#22c55e" if x >= 0 else "#ef4444"
            ),
            text=dow_pnl["win_rate"].apply(lambda x: f"{x:.0f}% WR"),
            textposition="outside",
        ))
        fig_dow.update_layout(
            template="plotly_dark",
            paper_bgcolor="#0e1117",
            plot_bgcolor="#0e1117",
            yaxis_title="USD" if USE_USD else "SOL",
            height=300,
            margin=dict(l=40, r=20, t=20, b=40),
        )
        st.plotly_chart(fig_dow, use_container_width=True)

        # Hour × Day Heatmap
        st.subheader("Trade Count: Hour × Day")
        heatmap_data = df_time.groupby(["dow", "hour"]).size().reset_index(name="count")
        pivot = heatmap_data.pivot(index="dow", columns="hour", values="count").fillna(0)
        # Reindex to proper day order
        pivot = pivot.reindex(dow_order).fillna(0)

        fig_heat = go.Figure(go.Heatmap(
            z=pivot.values,
            x=[f"{h:02d}" for h in pivot.columns],
            y=pivot.index,
            colorscale="Viridis",
            showscale=True,
        ))
        fig_heat.update_layout(
            template="plotly_dark",
            paper_bgcolor="#0e1117",
            plot_bgcolor="#0e1117",
            height=280,
            margin=dict(l=80, r=20, t=20, b=40),
            xaxis_title="Hour (UTC)",
        )
        st.plotly_chart(fig_heat, use_container_width=True)

        # Hour of Day P&L
        st.subheader("P&L by Hour")
        hour_pnl = df_time.groupby("hour")["signed_pnl"].sum().reset_index()
        hour_pnl.columns = ["Hour", "PnL"]
        fig_hour = go.Figure(go.Bar(
            x=hour_pnl["Hour"],
            y=hour_pnl["PnL"],
            marker_color=hour_pnl["PnL"].apply(
                lambda x: "#22c55e" if x >= 0 else "#ef4444"
            ),
        ))
        fig_hour.update_layout(
            template="plotly_dark",
            paper_bgcolor="#0e1117",
            plot_bgcolor="#0e1117",
            yaxis_title="USD" if USE_USD else "SOL",
            xaxis_title="Hour (UTC)",
            height=280,
            margin=dict(l=40, r=20, t=20, b=40),
        )
        st.plotly_chart(fig_hour, use_container_width=True)

# ═════════════════════════════════════════════
# TAB 5: MC ANALYSIS
# ═════════════════════════════════════════════
with tab_mc:
    if df_positions.empty:
        st.info("No positions found.")
    else:
        pnl_col = "pnl_usd" if USE_USD else "pnl_sol"
        df_mc = df_positions.copy()

        mc_stats = df_mc.groupby("mc_bucket", observed=False).agg(
            total_pnl=(pnl_col, "sum"),
            count=(pnl_col, "count"),
            wins=(pnl_col, lambda x: (x > 0).sum()),
        ).reset_index()
        mc_stats["win_rate"] = (mc_stats["wins"] / mc_stats["count"] * 100).fillna(0)
        # Ensure correct order
        mc_stats["mc_bucket"] = pd.Categorical(
            mc_stats["mc_bucket"], categories=MC_BUCKET_ORDER, ordered=True
        )
        mc_stats = mc_stats.sort_values("mc_bucket")

        # P&L by MC bucket
        st.subheader("P&L by Market Cap at Entry")
        fig_mc_pnl = go.Figure(go.Bar(
            x=mc_stats["mc_bucket"].astype(str),
            y=mc_stats["total_pnl"],
            marker_color=mc_stats["total_pnl"].apply(
                lambda x: "#22c55e" if x >= 0 else "#ef4444"
            ),
        ))
        fig_mc_pnl.update_layout(
            template="plotly_dark",
            paper_bgcolor="#0e1117",
            plot_bgcolor="#0e1117",
            yaxis_title="USD" if USE_USD else "SOL",
            height=300,
            margin=dict(l=40, r=20, t=20, b=40),
        )
        st.plotly_chart(fig_mc_pnl, use_container_width=True)

        # Win rate by MC bucket
        st.subheader("Win Rate by Market Cap")
        fig_mc_wr = go.Figure(go.Bar(
            x=mc_stats["mc_bucket"].astype(str),
            y=mc_stats["win_rate"],
            marker_color="#6366f1",
            text=mc_stats["win_rate"].apply(lambda x: f"{x:.0f}%"),
            textposition="outside",
        ))
        fig_mc_wr.update_layout(
            template="plotly_dark",
            paper_bgcolor="#0e1117",
            plot_bgcolor="#0e1117",
            yaxis_title="Win Rate %",
            yaxis_range=[0, 100],
            height=300,
            margin=dict(l=40, r=20, t=20, b=40),
        )
        st.plotly_chart(fig_mc_wr, use_container_width=True)

        # Summary table
        st.subheader("MC Bucket Summary")
        mc_table = mc_stats[["mc_bucket", "count", "wins", "win_rate", "total_pnl"]].copy()
        mc_table.columns = ["MC Bucket", "Positions", "Wins", "Win Rate %", "Total P&L"]
        mc_table["Win Rate %"] = mc_table["Win Rate %"].apply(lambda x: f"{x:.1f}%")
        mc_table["Total P&L"] = mc_table["Total P&L"].apply(lambda x: fmt_val(x, USE_USD))
        st.dataframe(mc_table, use_container_width=True, hide_index=True)

# ═════════════════════════════════════════════
# TAB 6: OPEN POSITIONS
# ═════════════════════════════════════════════
with tab_open:
    if df_positions.empty:
        st.info("No positions found.")
    else:
        open_pos = df_positions[df_positions["status"] == "OPEN BUY"].copy()
        if open_pos.empty:
            st.info("No open positions.")
        else:
            buy_col = "buy_usd" if USE_USD else "sol_in"
            open_pos["unrealized_display"] = open_pos["unrealized_usd"]
            open_pos["roi_open"] = np.where(
                open_pos[buy_col] > 0,
                (open_pos["unrealized_usd"] / open_pos[buy_col] * 100),
                0,
            )

            in_profit = open_pos[open_pos["unrealized_usd"] > 0].sort_values(
                "unrealized_usd", ascending=False
            )
            in_loss = open_pos[open_pos["unrealized_usd"] <= 0].sort_values(
                "unrealized_usd", ascending=True
            )

            sub_profit, sub_loss = st.tabs(["🟢 In Profit", "🔴 In Loss"])

            for sub_tab, sub_df, label in [
                (sub_profit, in_profit, "profitable"),
                (sub_loss, in_loss, "losing"),
            ]:
                with sub_tab:
                    if sub_df.empty:
                        st.info(f"No {label} open positions.")
                    else:
                        df_open_show = pd.DataFrame()
                        df_open_show["Name"] = sub_df["token_name"]
                        df_open_show["Ticker"] = sub_df["token_symbol"]
                        df_open_show["MC at Buy"] = sub_df["mc_at_buy"].apply(
                            lambda x: f"${x:,.0f}" if x > 0 else "—"
                        )
                        df_open_show["Balance"] = sub_df["remaining_tokens"].apply(
                            lambda x: f"{x:,.0f}"
                        )
                        df_open_show["Buy Amt"] = sub_df[buy_col].apply(
                            lambda x: fmt_val(x, USE_USD)
                        )
                        df_open_show["Current Value"] = sub_df["current_value"].apply(
                            lambda x: fmt_val(x, USE_USD)
                        )
                        df_open_show["Price"] = sub_df["current_price"].apply(
                            lambda x: f"${x:.8f}" if x < 0.01 else f"${x:.4f}"
                        )
                        df_open_show["Unrealised P&L"] = sub_df["unrealized_usd"].apply(
                            lambda x: fmt_val(x, True)
                        )
                        df_open_show["ROI"] = sub_df["roi_open"].apply(
                            lambda x: f"{x:+,.1f}%"
                        )
                        df_open_show["First Buy"] = sub_df["first_buy_dt"].apply(
                            lambda x: x.strftime("%Y-%m-%d") if pd.notna(x) else "—"
                        )
                        st.dataframe(df_open_show, use_container_width=True,
                                     height=500, hide_index=True)
                        st.caption(f"{len(sub_df)} {label} open positions")
