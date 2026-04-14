# Solana Wallet Trade Analyzer

A Solana wallet trade analyzer with a bootstrap pipeline (Colab) and an
interactive dashboard (Streamlit Cloud) that fetches new swaps
incrementally and persists them back to Google Drive — so updates
survive Streamlit Cloud container recycles.

## Architecture

```
┌──────────────────────┐     Google Drive      ┌───────────────────────┐
│  process_wallet.py   │ ◀── wallet_*.json ──▶ │  wallet_dashboard.py  │
│  (Google Colab)      │   (read + write)      │  + pipeline.py        │
│  Full history fetch  │                       │  + drive_io.py        │
│  Run once per wallet │                       │  Incremental updates  │
└──────────────────────┘                       └───────────────────────┘
                                                        │
                                                        ▼
                                                 Helius (new swaps)
                                                 DexScreener (prices)
```

- **Colab** does the initial full-history fetch (expensive, once per wallet)
- **Dashboard** fetches only new swaps since the last update (cheap, on-demand)
- **Updated JSON is written back to the same Drive file** after each fetch,
  so cold starts always pick up the latest state
- **Helius API key + Google service account** live in Streamlit Secrets

## How incremental fetch + write-back works

When you click **⚡ Fetch New** in the dashboard:

1. Reads the stored `last_signature` from the wallet JSON
2. Walks Helius newest → oldest, stopping at that signature — only new txns are pulled
3. Parses new trades using the same logic as Colab bootstrap
4. Merges + dedupes with existing trades, rebuilds positions
5. Refreshes DexScreener prices for all tokens
6. Computes MC-at-first-buy **only for newly-seen mints**
7. Saves updated JSON to local disk
8. **Uploads the updated JSON back to the same Google Drive file ID**

Step 8 is what makes container recycles harmless: when Streamlit Cloud
wipes the container and re-downloads from Drive, it gets the latest
state, not a stale bootstrap.

## Setup

### 1. Bootstrap a wallet (Google Colab — once per wallet)

1. Upload `process_wallet.py` to Google Colab
2. Install dependencies: `!pip install requests`
3. Edit the 3 config lines:
   ```python
   API_KEY = "your-helius-api-key"
   WALLET  = "your-solana-wallet-address"
   PERIOD  = "ALL"
   ```
4. Run — outputs `wallet_XXXXXXXX_ALL.json`
5. Upload the JSON to a **dedicated Google Drive folder** (e.g. `wallet_data`)
6. Set the file's sharing to **"Anyone with the link"** (for gdown read access)
7. Copy the file ID from the share URL:
   `https://drive.google.com/file/d/THIS_PART/view`

### 2. Google Cloud service account (one-time setup)

This gives the Streamlit app **write** access to your Drive folder so it
can persist incremental updates back to the same files.

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (or select an existing one)
3. **Enable the Google Drive API**:
   APIs & Services → Library → search "Google Drive API" → Enable
4. **Create a service account**:
   APIs & Services → Credentials → Create Credentials → Service Account
   - Name it something like `wallet-dashboard-writer`
   - Skip the optional roles step
   - Click Done
5. **Create a key**:
   Click the new service account → Keys tab → Add Key → Create New Key → JSON
   - A JSON file downloads. Keep it safe — this is the credential.
6. **Note the service account email** (looks like
   `wallet-dashboard-writer@your-project.iam.gserviceaccount.com`)
7. **Share your Drive folder with the service account**:
   - In Google Drive, right-click your `wallet_data` folder → Share
   - Paste the service account email
   - Set permission to **Editor**
   - Uncheck "Notify people"
   - Click Share

That's it. The service account can now read and write to every file in
that folder.

### 3. Dashboard (Streamlit Cloud)

Repo files:
- `wallet_dashboard.py`
- `pipeline.py`
- `drive_io.py` ← new, required for Drive write-back
- `requirements.txt`
- `README.md`
- `.gitignore`

Make sure `requirements.txt` includes:
```
streamlit
plotly
pandas
gdown
requests
google-api-python-client
google-auth
```

Configure wallets in `wallet_dashboard.py`:
```python
DRIVE_WALLETS = {
    "My Wallet": "paste-google-drive-file-id-here",
}
```

Push to GitHub. On [share.streamlit.io](https://share.streamlit.io):

1. **New app** → select repo → main file `wallet_dashboard.py` → **Deploy**
2. **Settings → Secrets** and add both:

   ```toml
   HELIUS_API_KEY = "your-helius-api-key"

   [GOOGLE_SERVICE_ACCOUNT_JSON]
   type = "service_account"
   project_id = "your-project-id"
   private_key_id = "..."
   private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
   client_email = "wallet-dashboard-writer@your-project.iam.gserviceaccount.com"
   client_id = "..."
   auth_uri = "https://accounts.google.com/o/oauth2/auth"
   token_uri = "https://oauth2.googleapis.com/token"
   auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
   client_x509_cert_url = "..."
   universe_domain = "googleapis.com"
   ```

   Copy each field from the service account JSON file you downloaded.
   The `private_key` field needs to keep its `\n` escapes intact.

3. Save. The app restarts and ⚡ Fetch New now persists to Drive.

### 4. Day-to-day usage

- **⚡ Fetch New** — pulls new swaps from Helius, saves locally, and
  writes back to Drive. The toast shows both counts and the Drive save
  status. Cheap and persistent.
- **🔄 Reload** — re-downloads the wallet JSON from Drive, discarding
  any local-only state. With write-back enabled this is rarely needed —
  Drive is always current.

### 5. What you'll see

After a successful fetch, the toast looks like:
```
✅ Added 12 new trades (2 new tokens, 2 MC-at-buy computed) · 💾 Saved to Drive (847,392 bytes)
```

If the service account secret is missing or misconfigured, you'll see
the trade counts succeed but a warning instead of the save confirmation:
```
✅ Added 12 new trades (...) · ⚠️ Drive upload failed: ...
```

The local update is still applied — only the cross-recycle persistence
is lost until you fix the auth.

## Adding More Wallets

1. Bootstrap in Colab and upload to the **same shared Drive folder**
   (no extra sharing needed — the service account already has folder access)
2. Add one line to `DRIVE_WALLETS`
3. Push to GitHub

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

## Security

- Helius API key and Google service account live in Streamlit Secrets — never in GitHub
- Service account has access **only to the `wallet_data` folder** you shared
  with it — nothing else in your Drive
- Wallet JSONs are still "anyone with the link" for gdown read access;
  if you want to lock them down, you can switch the dashboard to read
  via the service account too (more refactoring, not done by default)
- `pipeline.py` and `drive_io.py` only read secrets when the user clicks
  ⚡ Fetch New, and never log them
