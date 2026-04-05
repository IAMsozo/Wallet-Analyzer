import streamlit as st
import json
import os
import pandas as pd
import plotly.graph_objects as go
from datetime import timedelta

st.set_page_config(
    page_title="Wallet Analyzer", page_icon="📊",
    layout="wide", initial_sidebar_state="expanded"
)

# ── CSS ───────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap');
html,body,[class*="css"]{font-family:'DM Sans',sans-serif;background:#0a0a0f;color:#e2e8f0}
.stApp{background:#0a0a0f}
section[data-testid="stSidebar"]{background:#0f0f1a;border-right:1px solid #1e1e30}
[data-testid="metric-container"]{background:linear-gradient(135deg,#0f0f1a,#13131f);border:1px solid #1e1e30;border-radius:10px;padding:16px;transition:border-color .2s}
[data-testid="metric-container"]:hover{border-color:#00ff88}
[data-testid="stMetricLabel"]{color:#64748b!important;font-size:11px!important;text-transform:uppercase;letter-spacing:1px;font-family:'Space Mono',monospace!important}
[data-testid="stMetricValue"]{color:#e2e8f0!important;font-family:'Space Mono',monospace!important;font-size:22px!important}
[data-testid="stMetricDelta"]{font-family:'Space Mono',monospace!important}
h1{font-family:'Space Mono',monospace!important;color:#00ff88!important;font-size:24px!important;letter-spacing:-1px}
h2{font-family:'Space Mono',monospace!important;color:#e2e8f0!important;font-size:16px!important;border-bottom:1px solid #1e1e30;padding-bottom:8px}
button[data-baseweb="tab"]{font-family:'Space Mono',monospace!important;font-size:12px!important;color:#64748b!important}
button[data-baseweb="tab"][aria-selected="true"]{color:#00ff88!important;border-bottom-color:#00ff88!important}
.stSelectbox>div>div,.stMultiSelect>div>div{background:#0f0f1a!important;border:1px solid #1e1e30!important;border-radius:6px!important}
.stRadio>div{flex-direction:row;gap:8px}
.stRadio>div>label{background:#0f0f1a;border:1px solid #1e1e30;border-radius:6px;padding:4px 14px;font-family:'Space Mono',monospace;font-size:12px;cursor:pointer}
.wallet-badge{font-family:'Space Mono',monospace;font-size:11px;color:#64748b;background:#0f0f1a;border:1px solid #1e1e30;border-radius:20px;padding:4px 12px;display:inline-block}
.section-header{font-family:'Space Mono',monospace;font-size:11px;color:#00ff88;text-transform:uppercase;letter-spacing:2px;padding:8px 0;border-bottom:1px solid #00ff8830;margin-bottom:16px}
.stPlotlyChart{border:1px solid #1e1e30;border-radius:10px}
.ht-wrap{overflow-y:auto;border:1px solid #e2e8f0;border-radius:8px;background:#ffffff}
.ht{width:100%;border-collapse:collapse;font-family:'Space Mono',monospace;font-size:12px;background:#ffffff}
.ht thead tr th{padding:10px 12px;text-align:left;color:#475569;font-size:10px;text-transform:uppercase;letter-spacing:1px;background:#f8fafc;border-bottom:2px solid #e2e8f0;position:sticky;top:0;white-space:nowrap}
.ht tbody tr{border-bottom:1px solid #f1f5f9;transition:background .1s}
.ht tbody tr:hover{background:#f8fafc}
.ht tbody tr td{padding:8px 12px;color:#1e293b;white-space:nowrap}
.ht a{color:#2563eb;text-decoration:none;font-weight:700}
.ht a:hover{color:#00aa55;text-decoration:underline}
.profit{color:#16a34a!important}
.loss{color:#dc2626!important}
.neutral{color:#64748b!important}
.badge-closed{background:#00ff8820;color:#00ff88;border-radius:4px;padding:2px 6px;font-size:10px}
.badge-open{background:#ffd70020;color:#ffd700;border-radius:4px;padding:2px 6px;font-size:10px}
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
# WALLET FILES — Google Drive configuration
# ──────────────────────────────────────────────────────────────────
# Add your wallets here. For each wallet:
#   1. Upload the wallet_*.json to Google Drive
#   2. Right-click → Share → "Anyone with the link" → Copy link
#   3. Extract the file ID from the link:
#      https://drive.google.com/file/d/FILE_ID_HERE/view
#   4. Add an entry below: "Display Name": "FILE_ID_HERE"
#
# Example:
#   "9d44pdMg (All time)": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms",
# ══════════════════════════════════════════════════════════════════
DRIVE_WALLETS = {
    # "Wallet Display Name": "Google Drive File ID",
    "Investor":"1VKHSrudNYAv1Gg8XfRujtoiB1y8l29ic",
    "1hrHighWr":"1Drvg7CXRGCYqwgkGSXQaaWlSGiIHby8y",
    "SMhigh_man":"1wLpAkNU6xhA3TJO2WB-BU5mAGfk7yGFN",
    "Nigga":"1R2Md04G-PVFqzNba1uI7lmyWq40-5RVJ",
    "Trial":"1BSJxHA7ouZ6e4F7jFl7y1bEi1KjFRG-z",
    "Trial2":"1bfitN8oL7fUwTIPWAUdEtk72BF4k4oPg",
    "VempNew":"1XsBBPZGl4ZrhdbdnFIbPJlRH0hp8i5dT",
    "38HWr":"1OeFyBLAhGViQJb05Va1FyOPH3TidMBss",
    "TEST500":"1n12ax3n8cpW-x4S0dhDES53SgVGAHAny",
    "HighWR53": "1dkN_NDEY89SkwA_e5Yn6sOqiRSGitI-M",
}

# ── Download wallet files from Drive on startup ────────────────────
import os
try:
    import gdown
except ImportError:
    os.system("pip install gdown -q")
    import gdown

os.makedirs("wallet_data", exist_ok=True)

wallet_labels = {}
for display_name, file_id in DRIVE_WALLETS.items():
    if file_id == "YOUR_DRIVE_FILE_ID_HERE":
        continue
    local_path = f"wallet_data/{display_name.replace(' ','_').replace('/','_')}.json"
    if not os.path.exists(local_path):
        with st.spinner(f"Downloading {display_name}..."):
            try:
                gdown.download(
                    f"https://drive.google.com/uc?id={file_id}",
                    local_path, quiet=True
                )
            except Exception as e:
                st.warning(f"Could not download {display_name}: {e}")
                continue
    if os.path.exists(local_path):
        try:
            with open(local_path) as fh:
                meta = json.load(fh)
            addr = meta.get("wallet", "?")
            gen  = meta.get("generated_at", "")[:10]
            label = f"{display_name}  |  {addr[:8]}...{addr[-6:]}  |  {gen}"
            wallet_labels[label] = local_path
        except:
            wallet_labels[display_name] = local_path

if not wallet_labels:
    st.error(
        "**No wallet files loaded.**\n\n"
        "Add your Google Drive file IDs to the `DRIVE_WALLETS` dictionary "
        "at the top of `wallet_dashboard.py`, then redeploy."
    )
    st.stop()

# ── Wallet refresh button ──────────────────────────────────────────
col_sel, col_ref = st.columns([5, 1])
with col_sel:
    selected_label = st.selectbox("🔑 Wallet", list(wallet_labels.keys()),
                                  key="wallet_selector")
with col_ref:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 Refresh", help="Re-download latest data from Drive"):
        # Delete cached files so they re-download
        for path in wallet_labels.values():
            if os.path.exists(path):
                os.remove(path)
        st.cache_data.clear()
        st.rerun()

selected_file = wallet_labels[selected_label]

# ══════════════════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════════════════
@st.cache_data
def load_data(filepath: str):
    with open(filepath) as f:
        raw = json.load(f)

    # ── Positions ────────────────────────────────────────────────
    pos_df = pd.DataFrame(raw["positions"])

    NUM_POS = [
        "pnl_usd","pnl_sol","buy_usd","sell_usd","sol_in","sol_out",
        "num_buys","num_sells","remaining_tokens","unrealized_pnl_usd",
        "current_price_usd","mc_at_first_buy","total_supply",
    ]
    for c in NUM_POS:
        if c in pos_df.columns:
            pos_df[c] = pd.to_numeric(pos_df[c], errors="coerce")

    def to_naive(series):
        parsed = pd.to_datetime(series, errors="coerce", utc=True)
        return parsed.dt.tz_convert(None)

    pos_df["first_buy_dt"] = to_naive(pos_df["first_buy"])
    pos_df["last_sell_dt"] = to_naive(pos_df["last_sell"])

    def clean_name(r):
        n = str(r.get("token_name") or "").strip()
        return n if n and n.lower() not in ["unknown","none","nan",""] else r["mint"][:14] + "..."
    def clean_sym(r):
        s = str(r.get("token_symbol") or "").strip()
        return s if s and s.lower() not in ["unknown","none","nan","???",""] else r["mint"][:8]

    pos_df["display_name"]   = pos_df.apply(clean_name, axis=1)
    pos_df["display_symbol"] = pos_df.apply(clean_sym,  axis=1)
    pos_df["roi_pct"]        = (pos_df["pnl_usd"] / pos_df["buy_usd"].where(pos_df["buy_usd"] > 0) * 100).round(1)
    pos_df["roi_sol_pct"]    = (pos_df["pnl_sol"] / pos_df["sol_in"].where(pos_df["sol_in"]   > 0) * 100).round(1)

    def best_bucket(r):
        b = r.get("mc_bucket_at_buy")
        if b and b not in ("Unknown", None, ""): return b
        return r.get("mc_bucket") or "Unknown"
    pos_df["mc_bucket_display"] = pos_df.apply(best_bucket, axis=1)

    def fmt_mc_val(val):
        try:
            v = float(val)
            if v <= 0: return "Unknown"
            if v >= 1_000_000: return f"${v/1_000_000:.1f}M"
            if v >= 1_000:     return f"${v/1_000:.0f}K"
            return f"${v:.0f}"
        except:
            return "Unknown"
    pos_df["mc_value_display"] = pos_df["mc_at_first_buy"].apply(fmt_mc_val)

    # ── Trades ───────────────────────────────────────────────────
    trd_df = pd.DataFrame(raw["trades"])
    NUM_TRD = ["sol_amount","usd_value","token_amount","sol_price","hour_utc"]
    for c in NUM_TRD:
        if c in trd_df.columns:
            trd_df[c] = pd.to_numeric(trd_df[c], errors="coerce")

    trd_df["datetime_utc"] = to_naive(trd_df["datetime_utc"])
    trd_df["date"]         = to_naive(trd_df["date"])
    trd_df["hour_utc"]     = trd_df["hour_utc"].fillna(0).astype(int)

    # ── Lookups ───────────────────────────────────────────────────
    supply_lookup = {}
    for p in raw["positions"]:
        ts = p.get("total_supply")
        if ts:
            try:
                v = float(ts)
                if v > 0: supply_lookup[p["mint"]] = v
            except: pass

    mint_lookup = pos_df.set_index("mint")[[
        "display_name","display_symbol","mc_bucket_display",
        "pnl_usd","pnl_sol","roi_pct","roi_sol_pct","buy_usd","sol_in",
        "status","remaining_tokens","current_price_usd","unrealized_pnl_usd",
    ]].to_dict("index")

    wallet_addr = raw.get("wallet", "Unknown")
    return pos_df, trd_df, mint_lookup, supply_lookup, wallet_addr

pos_df, trd_df, mint_lookup, supply_lookup, WALLET = load_data(selected_file)

# ══════════════════════════════════════════════════════════════════
# RENDER HELPERS
# ══════════════════════════════════════════════════════════════════
def html_table(df, height=520):
    hdrs = "".join(f"<th>{c}</th>" for c in df.columns)
    rows = "".join(
        "<tr>" + "".join(f"<td>{v}</td>" for v in r) + "</tr>"
        for _, r in df.iterrows()
    )
    return (f'<div class="ht-wrap" style="max-height:{height}px">'
            f'<table class="ht"><thead><tr>{hdrs}</tr></thead>'
            f'<tbody>{rows}</tbody></table></div>')

def _is_null(v):
    if v is None: return True
    try: return pd.isna(v)
    except: return False

def fmt_pnl_usd(v):
    if _is_null(v): return '<span class="neutral">N/A</span>'
    cls = "profit" if float(v) >= 0 else "loss"
    return f'<span class="{cls}">${float(v):+,.2f}</span>'

def fmt_pnl_sol(v):
    if _is_null(v): return '<span class="neutral">N/A</span>'
    cls = "profit" if float(v) >= 0 else "loss"
    return f'<span class="{cls}">{float(v):+.4f} SOL</span>'

def fmt_roi(v):
    if _is_null(v): return '<span class="neutral">N/A</span>'
    cls = "profit" if float(v) >= 0 else "loss"
    return f'<span class="{cls}">{float(v):+.1f}%</span>'

def fmt_mc_trade(mint, sol_amount, token_amount, sol_price):
    try:
        if not (sol_amount and token_amount and sol_price): return "Unknown"
        s = float(sol_amount); t = float(token_amount); p = float(sol_price)
        if t <= 0: return "Unknown"
        supply = supply_lookup.get(mint)
        if not supply: return "Unknown"
        mc = (s / t) * p * supply
        if mc >= 1_000_000: return f"${mc/1_000_000:.1f}M"
        if mc >= 1_000:     return f"${mc/1_000:.0f}K"
        return f"${mc:.0f}"
    except: return "Unknown"

def ticker_link(mint, sym):
    return f'<a href="https://gmgn.ai/sol/token/{mint}" target="_blank">{sym}</a>'

CHART = dict(
    paper_bgcolor="#0a0a0f", plot_bgcolor="#0a0a0f",
    font=dict(family="Space Mono", color="#64748b", size=11),
    margin=dict(l=0, r=0, t=30, b=0),
)

# ══════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("# 📊 Wallet Analyzer")
    st.markdown(f'<div class="wallet-badge">{WALLET[:8]}...{WALLET[-6:]}</div>', unsafe_allow_html=True)
    st.markdown("---")
    st.markdown('<div class="section-header">Global Filters</div>', unsafe_allow_html=True)

    min_d = trd_df["datetime_utc"].min().date()
    max_d = trd_df["datetime_utc"].max().date()
    date_from = st.date_input("From", value=min_d, min_value=min_d, max_value=max_d)
    date_to   = st.date_input("To",   value=max_d, min_value=min_d, max_value=max_d)
    st.markdown("---")

    mc_order  = ["<4K","4K-9K","10K-19K","20K-29K","30K-99K","100K-999K","1M+","Unknown"]
    mc_avail  = [m for m in mc_order if m in pos_df["mc_bucket_display"].values]
    mc_filter = st.multiselect("MC at Trade", mc_avail, default=mc_avail)
    status_filter = st.multiselect("Position Status",
        ["CLOSED","OPEN BUY","OPEN SELL"], default=["CLOSED","OPEN BUY","OPEN SELL"])
    dex_opts   = sorted(trd_df["dex"].dropna().unique())
    dex_filter = st.multiselect("DEX", dex_opts, default=list(dex_opts))
    day_filter = st.multiselect("Day of Week",
        ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"],
        default=["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"])
    hour_range = st.slider("Hour UTC", 0, 23, (0, 23))

# ══════════════════════════════════════════════════════════════════
# HEADER + USD/SOL TOGGLE
# ══════════════════════════════════════════════════════════════════
h1c, h2c = st.columns([3, 1])
with h1c:
    st.markdown("# Wallet Performance Analyzer")
    st.markdown(f'<span class="wallet-badge">{WALLET}</span>', unsafe_allow_html=True)
with h2c:
    st.markdown("<br>", unsafe_allow_html=True)
    currency = st.radio("", ["USD 💵", "SOL ◎"], horizontal=True, label_visibility="collapsed")
    st.markdown(f'<p style="font-family:Space Mono,monospace;font-size:10px;color:#64748b;text-align:right">{date_from} → {date_to}</p>', unsafe_allow_html=True)

USE_USD = (currency == "USD 💵")
st.markdown("<br>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
# FILTERS
# ══════════════════════════════════════════════════════════════════
def filt_pos(df):
    m = pd.Series(True, index=df.index)
    if status_filter: m &= df["status"].isin(status_filter)
    if mc_filter:     m &= df["mc_bucket_display"].isin(mc_filter)
    m &= df["first_buy_dt"].isna() | (df["first_buy_dt"].dt.date >= date_from)
    m &= df["first_buy_dt"].isna() | (df["first_buy_dt"].dt.date <= date_to)
    return df[m]

def filt_trd(df):
    m = (df["datetime_utc"].dt.date >= date_from) & (df["datetime_utc"].dt.date <= date_to)
    if dex_filter:  m &= df["dex"].isin(dex_filter)
    if day_filter:  m &= df["day_of_week"].isin(day_filter)
    m &= (df["hour_utc"] >= hour_range[0]) & (df["hour_utc"] <= hour_range[1])
    return df[m]

fpos = filt_pos(pos_df)
ftrd = filt_trd(trd_df)

closed_pos = fpos[fpos["status"] == "CLOSED"]
open_pos   = fpos[fpos["status"] == "OPEN BUY"]
wins       = closed_pos[closed_pos["pnl_sol"] > 0]
losses_c   = closed_pos[closed_pos["pnl_sol"] <= 0]
win_rate   = len(wins) / len(closed_pos) * 100 if len(closed_pos) else 0

# ── KPIs ──────────────────────────────────────────────────────────
if USE_USD:
    kpi_total  = f"${fpos['pnl_usd'].sum():,.0f}"
    kpi_real   = f"${closed_pos['pnl_usd'].sum():,.0f}"
    kpi_unreal = f"${open_pos['unrealized_pnl_usd'].sum():,.0f}"
    kpi_invest = f"${fpos['buy_usd'].sum():,.0f}"
else:
    kpi_total  = f"{fpos['pnl_sol'].sum():,.2f} SOL"
    kpi_real   = f"{closed_pos['pnl_sol'].sum():,.2f} SOL"
    kpi_unreal = f"{open_pos['unrealized_pnl_usd'].sum():,.2f} SOL"
    kpi_invest = f"{fpos['sol_in'].sum():,.2f} SOL"

k1,k2,k3,k4,k5,k6 = st.columns(6)
k1.metric("Total P&L",        kpi_total)
k2.metric("Realised P&L",     kpi_real)
k3.metric("Unrealised P&L",   kpi_unreal)
k4.metric("Win Rate",         f"{win_rate:.1f}%")
k5.metric("Closed Positions", f"{len(closed_pos):,}", delta=f"W:{len(wins)} L:{len(losses_c)}")
k6.metric("Total Invested",   kpi_invest)
st.markdown("<br>", unsafe_allow_html=True)

tab1,tab2,tab3,tab4,tab5,tab6 = st.tabs([
    "📈 P&L Overview","📋 Trade History","🪙 Positions",
    "📅 Time Analysis","📊 MC Analysis","💼 Open Positions",
])

# ════════════════════════════════════════════════════════════════
# TAB 1 — P&L Overview
# ════════════════════════════════════════════════════════════════
with tab1:
    pnl_col = "pnl_usd" if USE_USD else "pnl_sol"
    pfx     = "$"       if USE_USD else ""
    sfx     = ""        if USE_USD else " SOL"

    if "pnl_period" not in st.session_state:
        st.session_state["pnl_period"] = "All"

    bp1,bp2,bp3,bp4,bp5,bp6,_ = st.columns([1,1,1,1,1,1,5])
    if bp1.button("1D",     use_container_width=True): st.session_state["pnl_period"] = "1D"
    if bp2.button("7D",     use_container_width=True): st.session_state["pnl_period"] = "7D"
    if bp3.button("1M",     use_container_width=True): st.session_state["pnl_period"] = "1M"
    if bp4.button("1Y",     use_container_width=True): st.session_state["pnl_period"] = "1Y"
    if bp5.button("All",    use_container_width=True): st.session_state["pnl_period"] = "All"
    if bp6.button("Custom", use_container_width=True): st.session_state["pnl_period"] = "Custom"

    period   = st.session_state["pnl_period"]
    today_ts = pd.Timestamp.utcnow().normalize().tz_localize(None)

    if   period == "1D":     p_from = today_ts - timedelta(days=1)
    elif period == "7D":     p_from = today_ts - timedelta(days=7)
    elif period == "1M":     p_from = today_ts - timedelta(days=30)
    elif period == "1Y":     p_from = today_ts - timedelta(days=365)
    elif period == "Custom":
        cc1,cc2 = st.columns(2)
        with cc1: p_from = pd.Timestamp(st.date_input("From", value=(today_ts-timedelta(days=90)).date(), key="cf"))
        with cc2: p_to   = pd.Timestamp(st.date_input("To",   value=today_ts.date(), key="ct"))
    else:
        p_from = pd.Timestamp("2000-01-01")

    p_to = today_ts + timedelta(days=1) if period != "Custom" else p_to

    st.markdown(f'<p style="font-family:Space Mono,monospace;font-size:10px;color:#00ff88;margin:4px 0 14px">Period: <b>{period}</b> &nbsp;|&nbsp; {p_from.date()} → {p_to.date()}</p>', unsafe_allow_html=True)

    cl, cr = st.columns([2, 1])

    with cl:
        st.markdown("## Cumulative P&L Over Time")
        cp_all = closed_pos.dropna(subset=["last_sell_dt", pnl_col]).sort_values("last_sell_dt").copy()
        cp_all["cum"] = cp_all[pnl_col].cumsum()
        cp = cp_all[(cp_all["last_sell_dt"] >= p_from) & (cp_all["last_sell_dt"] <= p_to)]

        if not cp.empty:
            fig = go.Figure(go.Scatter(
                x=cp["last_sell_dt"], y=cp["cum"], mode="lines",
                line=dict(color="#00ff88", width=2),
                fill="tozeroy", fillcolor="rgba(0,255,136,0.07)",
                hovertemplate=f"<b>%{{x|%Y-%m-%d}}</b><br>{pfx}%{{y:,.2f}}{sfx}<extra></extra>",
            ))
            fig.update_layout(**CHART, height=320, showlegend=False, hovermode="x unified",
                xaxis=dict(gridcolor="#1e1e30", zeroline=False),
                yaxis=dict(gridcolor="#1e1e30", zeroline=True, zerolinecolor="#334155",
                           tickprefix=pfx, ticksuffix=sfx))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No closed trades in this period.")

        period_pnl  = cp[pnl_col].sum() if not cp.empty else 0
        period_n    = len(cp)
        period_wins = int((cp["pnl_sol"] > 0).sum()) if not cp.empty else 0
        pk1,pk2,pk3 = st.columns(3)
        pk1.metric(f"{period} P&L",     f"{pfx}{period_pnl:,.2f}{sfx}")
        pk2.metric(f"{period} Closed",  f"{period_n:,}")
        pk3.metric(f"{period} Win Rate",f"{round(period_wins/period_n*100,1) if period_n else 0}%")

    with cr:
        st.markdown("## Monthly P&L")
        mon = closed_pos.dropna(subset=["first_buy_dt", pnl_col]).copy()
        mon = mon[(mon["first_buy_dt"] >= p_from) & (mon["first_buy_dt"] <= p_to)].copy()
        if not mon.empty:
            mon["month"] = mon["first_buy_dt"].dt.to_period("M").astype(str)
            mg2 = mon.groupby("month")[pnl_col].sum().reset_index().sort_values("month").tail(24)
            fig2 = go.Figure(go.Bar(
                x=mg2["month"], y=mg2[pnl_col],
                marker_color=["#00ff88" if v > 0 else "#ff4466" for v in mg2[pnl_col]],
                hovertemplate=f"<b>%{{x}}</b><br>{pfx}%{{y:,.2f}}{sfx}<extra></extra>",
            ))
            fig2.update_layout(**CHART, height=380, bargap=0.15,
                xaxis=dict(gridcolor="#1e1e30", tickangle=-45),
                yaxis=dict(gridcolor="#1e1e30", tickprefix=pfx, ticksuffix=sfx))
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("No data for this period.")

    st.markdown("## Yearly Breakdown")
    yr = closed_pos.dropna(subset=["first_buy_dt"]).copy()
    yr["year"] = yr["first_buy_dt"].dt.year
    yg = yr.groupby("year").agg(
        pnl_usd=("pnl_usd","sum"), pnl_sol=("pnl_sol","sum"),
        wins=("pnl_sol", lambda x:(x>0).sum()),
        losses=("pnl_sol", lambda x:(x<=0).sum()),
        trades=("pnl_sol","count"),
    ).reset_index()
    yg["wr"] = (yg["wins"]/(yg["wins"]+yg["losses"])*100).round(1)
    for _, row in yg.iterrows():
        c1,c2,c3,c4,c5 = st.columns(5)
        c1.metric(f"{int(row['year'])} P&L",
                  f"${row['pnl_usd']:,.0f}" if USE_USD else f"{row['pnl_sol']:,.1f} SOL")
        c2.metric("Alt P&L",
                  f"{row['pnl_sol']:,.1f} SOL" if USE_USD else f"${row['pnl_usd']:,.0f}")
        c3.metric("Trades",   f"{int(row['trades']):,}")
        c4.metric("Win Rate", f"{row['wr']}%")
        c5.metric("W / L",    f"{int(row['wins'])} / {int(row['losses'])}")

# ════════════════════════════════════════════════════════════════
# TAB 2 — Trade History
# ════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("## Trade History")
    st.caption("MC is per-trade (implied price × supply). P&L and ROI reflect the full position for that token.")

    ca, cb, cc = st.columns([2, 2, 1])
    with ca:
        trd_filter = st.selectbox("Filter",
            ["All Trades","Buys Only","Sells Only","Unique Buys Only"],
            key="trd_filter", help="Unique Buys = first-ever buy per token only")
    with cb:
        sort_t = st.selectbox("Sort by", ["Time","Amount","ROI","P&L"], key="tsrt")
    with cc:
        sort_dir_t = st.radio("", ["↓","↑"], key="tsrt_dir", horizontal=True)
    trd_asc = (sort_dir_t == "↑")

    dt = ftrd.copy()
    # Always filter out dust trades (< $1 / < 0.01 SOL) — these are account rent
    # deposits or test transactions, not real trades
    dust_mask = (dt["usd_value"].fillna(0) >= 1.0) | (dt["sol_amount"].fillna(0) >= 0.01)
    dt = dt[dust_mask]
    if trd_filter == "Buys Only":         dt = dt[dt["action"] == "BUY"]
    elif trd_filter == "Sells Only":      dt = dt[dt["action"] == "SELL"]
    elif trd_filter == "Unique Buys Only":dt = dt[(dt["action"]=="BUY") & (dt["is_first_buy"]==True)]

    def enrich_trade(row):
        mint   = row["token_mint"]
        info   = mint_lookup.get(mint, {})
        sym    = info.get("display_symbol") or mint[:8]
        pnl    = info.get("pnl_usd")  if USE_USD else info.get("pnl_sol")
        roi    = info.get("roi_pct")  if USE_USD else info.get("roi_sol_pct")
        mc     = fmt_mc_trade(mint, row.get("sol_amount"), row.get("token_amount"), row.get("sol_price"))
        status = info.get("status", "")
        upnl   = info.get("unrealized_pnl_usd")
        rem    = info.get("remaining_tokens") or 0
        cpx    = info.get("current_price_usd") or 0
        if status == "CLOSED":
            unreal = '<span class="neutral">—</span>'
        elif not _is_null(upnl) and rem and cpx:
            unreal = fmt_pnl_usd(upnl)
        else:
            unreal = '<span class="neutral">No price</span>'
        return sym, mc, pnl, roi, unreal

    if len(dt):
        cols = [enrich_trade(r) for _, r in dt.iterrows()]
        dt = dt.copy()
        dt["_sym"], dt["_mc"], dt["_pnl"], dt["_roi"], dt["_upnl"] = zip(*cols)
    else:
        dt = dt.copy()
        dt["_sym"] = dt["_mc"] = dt["_pnl"] = dt["_roi"] = dt["_upnl"] = None

    sort_map = {
        "Time":   "datetime_utc",
        "Amount": "usd_value" if USE_USD else "sol_amount",
        "ROI":    "_roi",
        "P&L":    "_pnl",
    }
    dt = dt.sort_values(sort_map[sort_t], ascending=trd_asc, na_position="last")

    amt_hdr = "Amount (USD)" if USE_USD else "Amount (SOL)"
    rows = []
    for _, r in dt.iterrows():
        mint = r["token_mint"]
        act  = ('<span class="profit" style="font-weight:700">BUY</span>'
                if r["action"] == "BUY"
                else '<span class="loss" style="font-weight:700">SELL</span>')
        amt  = (f"${r['usd_value']:,.2f}" if pd.notna(r.get("usd_value")) else "N/A") if USE_USD else \
               (f"{r['sol_amount']:.4f}"  if pd.notna(r.get("sol_amount")) else "N/A")
        pnl  = fmt_pnl_usd(r["_pnl"]) if USE_USD else fmt_pnl_sol(r["_pnl"])
        rows.append({
            "Time (UTC)":   str(r["datetime_utc"])[:19],
            "Action":       act,
            "Ticker":       ticker_link(mint, r["_sym"]),
            "MC at Trade":  r["_mc"] or "Unknown",
            amt_hdr:        amt,
            "Realised P&L": pnl,
            "Unreal P&L":   r["_upnl"] if r.get("_upnl") else '<span class="neutral">—</span>',
            "ROI":          fmt_roi(r["_roi"]),
            "1st Buy":      "✅" if r.get("is_first_buy") else "",
        })
    st.markdown(html_table(pd.DataFrame(rows), height=560), unsafe_allow_html=True)
    st.caption(f"{len(rows):,} trades shown")

# ════════════════════════════════════════════════════════════════
# TAB 3 — Positions
# ════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("## Position Analysis")

    sc1, _, sc3 = st.columns([2, 2, 1])
    with sc1:
        sort_by = st.selectbox("Sort by", ["P&L","ROI","Buy Amount"], key="psrt")
    with sc3:
        sort_dir_p = st.radio("", ["↓","↑"], key="psrt_dir", horizontal=True)
    pos_asc = (sort_dir_p == "↑")

    sort_col_map = {
        "P&L":        "pnl_usd"  if USE_USD else "pnl_sol",
        "ROI":        "roi_pct"  if USE_USD else "roi_sol_pct",
        "Buy Amount": "buy_usd"  if USE_USD else "sol_in",
    }
    dp = fpos.copy().sort_values(sort_col_map[sort_by], ascending=pos_asc, na_position="last")

    rows = []
    for _, r in dp.iterrows():
        mint  = r["mint"]
        stat  = ('<span class="badge-closed">CLOSED</span>' if r["status"]=="CLOSED"
                 else '<span class="badge-open">OPEN</span>')
        if USE_USD:
            buy_amt  = f"${r['buy_usd']:,.2f}"  if pd.notna(r.get("buy_usd"))  else "N/A"
            sell_amt = f"${r['sell_usd']:,.2f}" if pd.notna(r.get("sell_usd")) else "N/A"
            pnl_v    = fmt_pnl_usd(r.get("pnl_usd"))
            roi_v    = fmt_roi(r.get("roi_pct"))
        else:
            buy_amt  = f"{r['sol_in']:.4f} SOL"  if pd.notna(r.get("sol_in"))  else "N/A"
            sell_amt = f"{r['sol_out']:.4f} SOL" if pd.notna(r.get("sol_out")) else "N/A"
            pnl_v    = fmt_pnl_sol(r.get("pnl_sol"))
            roi_v    = fmt_roi(r.get("roi_sol_pct"))
        bal = r.get("remaining_tokens")
        bal_s = f"{float(bal):,.0f}" if not _is_null(bal) and float(bal) > 0 else "—"
        rows.append({
            "Name":      (r["display_name"] or "")[:22],
            "Ticker":    ticker_link(mint, r["display_symbol"]),
            "Status":    stat,
            "MC at Buy": r.get("mc_value_display") or "Unknown",
            "MC Bucket": r.get("mc_bucket_display") or "Unknown",
            "Buys":      int(r["num_buys"])  if not _is_null(r.get("num_buys"))  else 0,
            "Sells":     int(r["num_sells"]) if not _is_null(r.get("num_sells")) else 0,
            "Balance":   bal_s,
            "Buy Amt":   buy_amt,
            "Sell Amt":  sell_amt,
            "P&L":       pnl_v,
            "ROI":       roi_v,
            "First Buy": str(r["first_buy"])[:16] if r.get("first_buy") else "—",
        })
    st.markdown(html_table(pd.DataFrame(rows), height=560), unsafe_allow_html=True)
    st.caption(f"{len(rows):,} positions  |  Balance = unsold tokens remaining")

# ════════════════════════════════════════════════════════════════
# TAB 4 — Time Analysis
# ════════════════════════════════════════════════════════════════
with tab4:
    st.markdown("## Time-Based Performance")
    days_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    pnl_col    = "pnl_usd" if USE_USD else "pnl_sol"
    tick_pfx   = "$"       if USE_USD else ""
    tick_sfx   = ""        if USE_USD else " SOL"

    col_dow, col_hod = st.columns(2)

    with col_dow:
        st.markdown("#### Day of Week — P&L")
        cp2 = closed_pos.dropna(subset=["first_buy_dt", pnl_col]).copy()
        cp2["dow"] = cp2["first_buy_dt"].dt.day_name()
        dg = cp2.groupby("dow").agg(
            pnl=(pnl_col,"sum"),
            wins=("pnl_sol", lambda x:(x>0).sum()),
            losses=("pnl_sol", lambda x:(x<=0).sum()),
            count=("pnl_sol","count"),
        ).reindex(days_order).reset_index()
        dg["Win%"] = (dg["wins"]/(dg["wins"]+dg["losses"])*100).round(1)
        fig_d = go.Figure(go.Bar(
            x=dg["dow"], y=dg["pnl"],
            marker_color=["#00ff88" if v>0 else "#ff4466" for v in dg["pnl"]],
            text=dg["Win%"].apply(lambda x: f"{x:.0f}%"),
            textposition="outside",
            textfont=dict(family="Space Mono", size=10, color="#94a3b8"),
            hovertemplate=f"<b>%{{x}}</b><br>{tick_pfx}%{{y:,.2f}}{tick_sfx}<extra></extra>",
        ))
        fig_d.update_layout(**CHART, height=300,
            xaxis=dict(gridcolor="#1e1e30"),
            yaxis=dict(gridcolor="#1e1e30", tickprefix=tick_pfx, ticksuffix=tick_sfx))
        st.plotly_chart(fig_d, use_container_width=True)
        tbl_d = dg[["dow","count","wins","losses","Win%","pnl"]].copy()
        tbl_d.columns = ["Day","Trades","W","L","Win%","P&L"]
        tbl_d["P&L"]  = tbl_d["P&L"].apply(lambda x: f"${x:,.0f}" if USE_USD else f"{x:,.2f} SOL")
        tbl_d["Win%"] = tbl_d["Win%"].apply(lambda x: f"{x:.1f}%")
        st.dataframe(tbl_d, hide_index=True, use_container_width=True, height=280)

    with col_hod:
        st.markdown("#### Hour × Day Heatmap")
        hm = ftrd.copy()
        hm["dow"] = hm["datetime_utc"].dt.day_name()
        hp   = hm.groupby(["dow","hour_utc"]).size().reset_index(name="n")
        hpiv = hp.pivot(index="dow", columns="hour_utc", values="n").fillna(0)
        hpiv = hpiv.reindex([d for d in days_order if d in hpiv.index])
        fig_h = go.Figure(go.Heatmap(
            z=hpiv.values,
            x=[f"{h:02d}:00" for h in hpiv.columns],
            y=hpiv.index.tolist(),
            colorscale=[[0,"rgb(10,10,15)"],[0.4,"rgb(0,60,40)"],[1,"rgb(0,255,136)"]],
            showscale=False,
            hovertemplate="<b>%{y} %{x}</b><br>Trades: %{z}<extra></extra>",
        ))
        fig_h.update_layout(**CHART, height=290, xaxis=dict(tickangle=-45))
        st.plotly_chart(fig_h, use_container_width=True)

        st.markdown("#### Hour of Day — P&L")
        cp3 = closed_pos.dropna(subset=["first_buy", pnl_col]).copy()
        cp3["hour"] = pd.to_datetime(cp3["first_buy"]).dt.hour
        hg = cp3.groupby("hour")[pnl_col].sum().reindex(range(24), fill_value=0)
        fig_hd = go.Figure(go.Bar(
            x=[f"{h:02d}:00" for h in hg.index], y=hg.values,
            marker_color=["#00ff88" if v>0 else "#ff4466" for v in hg.values],
            hovertemplate=f"<b>%{{x}}</b><br>{tick_pfx}%{{y:,.2f}}{tick_sfx}<extra></extra>",
        ))
        fig_hd.update_layout(**CHART, height=260,
            xaxis=dict(gridcolor="#1e1e30", tickangle=-45),
            yaxis=dict(gridcolor="#1e1e30", tickprefix=tick_pfx, ticksuffix=tick_sfx))
        st.plotly_chart(fig_hd, use_container_width=True)

# ════════════════════════════════════════════════════════════════
# TAB 5 — MC Analysis
# ════════════════════════════════════════════════════════════════
with tab5:
    st.markdown("## Market Cap at Trade Analysis")
    st.caption("MC at buy calculated using implied token price × total supply.")
    mc_order = ["<4K","4K-9K","10K-19K","20K-29K","30K-99K","100K-999K","1M+","Unknown"]
    pnl_col  = "pnl_usd" if USE_USD else "pnl_sol"

    mg = closed_pos.groupby("mc_bucket_display").agg(
        pnl=(pnl_col,"sum"),
        wins=("pnl_sol", lambda x:(x>0).sum()),
        losses=("pnl_sol", lambda x:(x<=0).sum()),
        count=("pnl_sol","count"),
    ).reset_index()
    mg.columns = ["mc_bucket","pnl","wins","losses","count"]
    mg = mg.set_index("mc_bucket").reindex(
        [m for m in mc_order if m in mg.index]
    ).reset_index()
    mg["win_rate"] = (mg["wins"]/(mg["wins"]+mg["losses"])*100).round(1)
    mg["avg_pnl"]  = (mg["pnl"]/mg["count"]).round(2)

    cm1, cm2 = st.columns(2)
    with cm1:
        st.markdown("#### P&L by MC Bucket")
        fig_mc = go.Figure(go.Bar(
            x=mg["mc_bucket"], y=mg["pnl"],
            marker_color=["#00ff88" if v>0 else "#ff4466" for v in mg["pnl"]],
            text=mg["win_rate"].apply(lambda x: f"{x:.0f}%"),
            textposition="outside",
            textfont=dict(family="Space Mono", size=10, color="#94a3b8"),
            hovertemplate="<b>%{x}</b><br>%{y:,.2f}<extra></extra>",
        ))
        fig_mc.update_layout(**CHART, height=320,
            xaxis=dict(gridcolor="#1e1e30"),
            yaxis=dict(gridcolor="#1e1e30",
                       tickprefix="$" if USE_USD else "",
                       ticksuffix=""  if USE_USD else " SOL"))
        st.plotly_chart(fig_mc, use_container_width=True)
    with cm2:
        st.markdown("#### Win Rate by MC Bucket")
        fig_wr = go.Figure(go.Bar(
            x=mg["mc_bucket"], y=mg["win_rate"], marker_color="#00aaff",
            text=mg["win_rate"].apply(lambda x: f"{x:.0f}%"),
            textposition="outside",
            textfont=dict(family="Space Mono", size=10, color="#94a3b8"),
        ))
        fig_wr.add_hline(y=50, line_dash="dash", line_color="#334155",
                         annotation_text="50%", annotation_font_color="#64748b")
        fig_wr.update_layout(**CHART, height=320,
            xaxis=dict(gridcolor="#1e1e30"),
            yaxis=dict(gridcolor="#1e1e30", range=[0,115], ticksuffix="%"))
        st.plotly_chart(fig_wr, use_container_width=True)

    st.markdown("#### Summary Table")
    mt = mg[["mc_bucket","count","wins","losses","win_rate","pnl","avg_pnl"]].copy()
    mt.columns = ["MC Range","Closed","Wins","Losses","Win %","P&L","Avg P&L/Trade"]
    fmt_fn = (lambda x: f"${x:,.0f}") if USE_USD else (lambda x: f"{x:,.2f} SOL")
    mt["P&L"]           = mt["P&L"].apply(fmt_fn)
    mt["Avg P&L/Trade"] = mt["Avg P&L/Trade"].apply(fmt_fn)
    mt["Win %"]         = mt["Win %"].apply(lambda x: f"{x:.1f}%")
    st.dataframe(mt, hide_index=True, use_container_width=True)

# ════════════════════════════════════════════════════════════════
# TAB 6 — Open Positions
# ════════════════════════════════════════════════════════════════
with tab6:
    st.markdown("## Open Positions")
    oa = fpos[fpos["status"] == "OPEN BUY"].copy()
    oa["unrealized_roi"] = (
        oa["unrealized_pnl_usd"] / oa["buy_usd"].where(oa["buy_usd"] > 0) * 100
    ).round(1)

    ip = oa[oa["unrealized_pnl_usd"]  > 0].sort_values("unrealized_pnl_usd", ascending=False)
    il = oa[oa["unrealized_pnl_usd"]  < 0].sort_values("unrealized_pnl_usd", ascending=True)
    nd = oa[oa["unrealized_pnl_usd"].isna()]

    s1,s2,s3,s4 = st.columns(4)
    s1.metric("Total Open",        f"{len(oa):,}")
    s2.metric("✅ In Profit",       f"{len(ip):,}", delta=f"${ip['unrealized_pnl_usd'].sum():,.0f}")
    s3.metric("❌ In Loss",         f"{len(il):,}", delta=f"${il['unrealized_pnl_usd'].sum():,.0f}")
    s4.metric("💀 No Price/Rugged", f"{len(nd):,}", delta=f"-${nd['buy_usd'].sum():,.0f}")
    st.markdown("<br>", unsafe_allow_html=True)

    def open_rows(df):
        rows = []
        for _, r in df.iterrows():
            mint   = r["mint"]
            cost_u = (float(r.get("buy_usd") or 0)) - (float(r.get("sell_usd") or 0))
            cost_s = (float(r.get("sol_in")  or 0)) - (float(r.get("sol_out")  or 0))
            curr_p = float(r.get("current_price_usd") or 0)
            rem    = float(r.get("remaining_tokens") or 0)
            curr_v = rem * curr_p
            upnl   = r.get("unrealized_pnl_usd")
            uroi   = r.get("unrealized_roi")
            bal_s  = f"{rem:,.0f}" if rem > 0 else "—"
            buy_a  = f"${cost_u:,.2f}" if USE_USD else f"{cost_s:.4f} SOL"
            pnl_v  = fmt_pnl_usd(upnl)
            rows.append({
                "Name":       (r["display_name"] or "")[:22],
                "Ticker":     ticker_link(mint, r["display_symbol"]),
                "MC at Buy":  r.get("mc_value_display") or "Unknown",
                "Balance":    bal_s,
                "Buy Amt":    buy_a,
                "Curr Val":   f"${curr_v:,.2f}" if curr_v > 0 else "N/A",
                "Price":      f"${curr_p:.8f}"  if curr_p > 0 else "N/A",
                "Unreal P&L": pnl_v,
                "ROI":        fmt_roi(uroi),
                "First Buy":  str(r["first_buy"])[:16] if r.get("first_buy") else "—",
            })
        return pd.DataFrame(rows)

    sub1, sub2 = st.tabs(["✅ In Profit", "❌ In Loss"])
    with sub1: st.markdown(html_table(open_rows(ip), height=430), unsafe_allow_html=True)
    with sub2: st.markdown(html_table(open_rows(il), height=430), unsafe_allow_html=True)
