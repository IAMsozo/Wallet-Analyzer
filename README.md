# Solana Wallet Trade Analyzer

A two-component system for analyzing Solana wallet trades: a private data pipeline (Colab) and a public dashboard (Streamlit Cloud).

## Architecture

```
┌──────────────────────┐       Google Drive       ┌───────────────────────┐
│  process_wallet.py   │  ──── wallet_*.json ───▶  │  wallet_dashboard.py  │
│  (Google Colab)      │                           │  (Streamlit Cloud)    │
│  Has API key         │                           │  No API keys          │
│  Never in GitHub     │                           │  Public GitHub repo   │
└──────────────────────┘                           └───────────────────────┘
```

- **API key** stays in Colab — never exposed
- **Wallet data** stays in Google Drive — never in GitHub
- **Dashboard** is a public web app anyone can view

## Setup

### 1. Pipeline (Private — Google Colab)

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

### 2. Dashboard (Public — Streamlit Cloud)

1. Fork or create a GitHub repo with these files:
   - `wallet_dashboard.py`
   - `requirements.txt`
   - `README.md`
   - `.gitignore`
2. Edit `DRIVE_WALLETS` at the top of `wallet_dashboard.py`:
   ```python
   DRIVE_WALLETS = {
       "My Wallet": "paste-google-drive-file-id-here",
   }
   ```
3. Push to GitHub
4. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**
5. Select your repo → set main file to `wallet_dashboard.py` → **Deploy**
6. Your dashboard is live at `https://yourapp.streamlit.app`

### 3. Updating Data

1. Re-run `process_wallet.py` in Colab
2. Upload new JSON to Google Drive (replace same file to keep the same ID)
3. Click **🔄 Refresh** in the dashboard
4. No redeployment or GitHub changes needed

## Adding More Wallets

Add one line to `DRIVE_WALLETS`:

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

- **Pipeline**: Python, Helius API, Kraken API, CryptoCompare, DexScreener
- **Dashboard**: Streamlit, Plotly, pandas
- **Storage**: Google Drive (wallet JSON), gdown (download)
- **Hosting**: Streamlit Community Cloud (free)
