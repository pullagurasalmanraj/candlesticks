# services/token_service.py
import os, json
from datetime import datetime, timedelta, timezone
from dotenv import set_key

from config     import TOKENS_FILE, ENV_FILE, UPSTOX_API_BASE
from config     import UPSTOX_CLIENT_ID, UPSTOX_CLIENT_SECRET, UPSTOX_REDIRECT_URI, safe_requests
from extensions import redis_client, REDIS_ENABLED


def load_saved_tokens() -> dict:
    if REDIS_ENABLED and redis_client:
        try:
            t = redis_client.get("upstox:tokens")
            return json.loads(t) if t else {}
        except Exception:
            pass
    if os.path.exists(TOKENS_FILE):
        try:
            with open(TOKENS_FILE) as f:
                return json.load(f) or {}
        except Exception:
            pass
    return {}


def save_tokens(data: dict):
    data_copy = dict(data)
    data_copy["saved_at"] = datetime.now(timezone.utc).isoformat()
    if REDIS_ENABLED and redis_client:
        try:
            redis_client.set("upstox:tokens", json.dumps(data_copy))
        except Exception as e:
            print("⚠️  Redis token write failed:", e)
    try:
        with open(TOKENS_FILE, "w") as f:
            json.dump(data_copy, f, indent=2)
    except Exception:
        pass
    if data_copy.get("access_token"):
        os.environ["UPSTOX_ACCESS_TOKEN"] = data_copy["access_token"]
        try:
            set_key(ENV_FILE, "UPSTOX_ACCESS_TOKEN", data_copy["access_token"])
        except Exception:
            pass
    print("💾 Token saved.")


def token_is_fresh(max_age_hours: int = 24) -> bool:
    data = load_saved_tokens()
    if not data.get("access_token") or not data.get("saved_at"):
        return False
    try:
        t = datetime.fromisoformat(data["saved_at"])
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - t) < timedelta(hours=max_age_hours)
    except Exception:
        return False


def refresh_upstox_token() -> bool:
    data          = load_saved_tokens()
    refresh_token = data.get("refresh_token") or os.getenv("UPSTOX_REFRESH_TOKEN", "").strip()
    if not refresh_token:
        return False
    try:
        r = safe_requests.post(
            f"{UPSTOX_API_BASE}/login/authorization/token",
            data={"grant_type": "refresh_token", "refresh_token": refresh_token,
                  "client_id": UPSTOX_CLIENT_ID, "client_secret": UPSTOX_CLIENT_SECRET,
                  "redirect_uri": UPSTOX_REDIRECT_URI},
            timeout=12,
        )
        j = r.json() if r.content else {}
        if r.status_code == 200 and "access_token" in j:
            save_tokens(j)
            return True
        return False
    except Exception:
        return False


def get_valid_token() -> str | None:
    """Returns a valid access token, refreshing if needed."""
    token = load_saved_tokens().get("access_token")
    if not token:
        return None
    if not token_is_fresh():
        if not refresh_upstox_token():
            return None
        token = load_saved_tokens().get("access_token")
    return token
