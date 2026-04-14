# ═══════════════════════════════════════════════════════════════════
# GOOGLE DRIVE WRITE-BACK
# ═══════════════════════════════════════════════════════════════════
# Persists incrementally-updated wallet JSONs back to the same Google
# Drive file IDs, so they survive Streamlit Cloud container recycles.
#
# Auth: service account JSON stored in st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"].
# The service account needs Editor access to the Drive folder (or to
# each individual file). It updates files IN PLACE — file IDs never change.
#
# This module is intentionally tiny: one auth helper, one upload function.
# Imported by wallet_dashboard.py only when the user clicks ⚡ Fetch New.
# ═══════════════════════════════════════════════════════════════════

import io
import json


def _get_drive_service(service_account_info):
    """
    Build a Drive v3 client from a service account dict.
    Lazy imports keep cold-start fast for users who don't click Fetch New.
    """
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=["https://www.googleapis.com/auth/drive"],
    )
    # cache_discovery=False silences a noisy warning on Streamlit Cloud
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def upload_wallet_json(file_id, wallet_json, service_account_info):
    """
    Overwrite the Drive file at `file_id` with the given wallet_json dict.
    Returns (success: bool, message: str).

    Uses media upload to update the file in place — the file ID stays
    the same, so DRIVE_WALLETS in the dashboard never needs updating.
    """
    try:
        from googleapiclient.http import MediaIoBaseUpload
    except ImportError:
        return False, "google-api-python-client not installed"

    try:
        service = _get_drive_service(service_account_info)
    except Exception as e:
        return False, f"Drive auth failed: {e}"

    try:
        # Serialize JSON to bytes, wrap in a BytesIO for the upload media
        payload = json.dumps(wallet_json).encode("utf-8")
        media = MediaIoBaseUpload(
            io.BytesIO(payload),
            mimetype="application/json",
            resumable=False,
        )
        # update() on an existing file ID overwrites contents in place
        service.files().update(
            fileId=file_id,
            media_body=media,
        ).execute()
        return True, f"Saved to Drive ({len(payload):,} bytes)"
    except Exception as e:
        # Most common failure mode: service account doesn't have access.
        # Surface the error so the user knows what to fix.
        return False, f"Drive upload failed: {e}"
