import os
import json
import base64
import hashlib
from datetime import datetime, timedelta, timezone
from dotenv import set_key
from cryptography.fernet import Fernet

from config     import TOKENS_FILE, ENV_FILE, UPSTOX_API_BASE, SECRET_KEY, INDIA_TZ
from config     import UPSTOX_CLIENT_ID, UPSTOX_CLIENT_SECRET, UPSTOX_REDIRECT_URI, safe_requests
from extensions import redis_client, REDIS_ENABLED


def _get_cipher():
    key = base64.urlsafe_b64encode(hashlib.sha256((SECRET_KEY or "candlesticks_super_secret_key").encode()).digest())
    return Fernet(key)


def encrypt_token(plain_token: str) -> str:
    if not plain_token or not isinstance(plain_token, str):
        return ""
    if plain_token.startswith("gAAAAA"):
        return plain_token  # Already encrypted
    try:
        cipher = _get_cipher()
        return cipher.encrypt(plain_token.encode("utf-8")).decode("utf-8")
    except Exception as e:
        print("⚠️ Token encryption failed:", e)
        return plain_token


def decrypt_token(cipher_token: str) -> str:
    if not cipher_token or not isinstance(cipher_token, str):
        return ""
    token_str = cipher_token.strip("'\"")
    if not token_str.startswith("gAAAAA"):
        return token_str  # Legacy plaintext JWT token
    try:
        cipher = _get_cipher()
        return cipher.decrypt(token_str.encode("utf-8")).decode("utf-8")
    except Exception as e:
        print("⚠️ Token decryption failed:", e)
        return token_str


def load_saved_tokens() -> dict:
    data = {}
    if REDIS_ENABLED and redis_client:
        try:
            t = redis_client.get("upstox:tokens")
            if t:
                try:
                    data = json.loads(t)
                except json.JSONDecodeError:
                    if t.strip():
                        data = {"access_token": t.strip("'\"")}
        except Exception:
            pass

    if not data and os.path.exists(TOKENS_FILE):
        try:
            with open(TOKENS_FILE) as f:
                data = json.load(f) or {}
        except Exception:
            pass

    if not data:
        env_token = os.getenv("UPSTOX_ACCESS_TOKEN", "").strip().strip("'\"")
        if env_token:
            data = {"access_token": env_token}

    if isinstance(data, dict):
        decrypted = dict(data)
        if decrypted.get("access_token"):
            decrypted["access_token"] = decrypt_token(decrypted["access_token"])
        if decrypted.get("refresh_token"):
            decrypted["refresh_token"] = decrypt_token(decrypted["refresh_token"])
        return decrypted

    return {}


def save_tokens(data: dict):
    data_copy = dict(data)
    data_copy["saved_at"] = datetime.now(timezone.utc).isoformat()

    # Apply Fernet (AES) encryption at rest for access_token and refresh_token
    encrypted_dict = dict(data_copy)
    if encrypted_dict.get("access_token"):
        encrypted_dict["access_token"] = encrypt_token(encrypted_dict["access_token"])
    if encrypted_dict.get("refresh_token"):
        encrypted_dict["refresh_token"] = encrypt_token(encrypted_dict["refresh_token"])

    if REDIS_ENABLED and redis_client:
        try:
            redis_client.set("upstox:tokens", json.dumps(encrypted_dict))
        except Exception as e:
            print("⚠️  Redis token write failed:", e)
    try:
        with open(TOKENS_FILE, "w") as f:
            json.dump(encrypted_dict, f, indent=2)
    except Exception:
        pass
        try:
            set_key(ENV_FILE, "UPSTOX_ACCESS_TOKEN", encrypted_dict["access_token"])
        except Exception:
            pass
    print("🔒 Encrypted token saved to Redis, tokens.json, and .env.")


def clear_saved_tokens():
    if REDIS_ENABLED and redis_client:
        try:
            redis_client.delete("upstox:tokens")
        except Exception as e:
            print("⚠️ Redis token delete failed:", e)
    if os.path.exists(TOKENS_FILE):
        try:
            os.remove(TOKENS_FILE)
        except Exception:
            pass
    if "UPSTOX_ACCESS_TOKEN" in os.environ:
        del os.environ["UPSTOX_ACCESS_TOKEN"]
    try:
        set_key(ENV_FILE, "UPSTOX_ACCESS_TOKEN", "")
    except Exception:
        pass
    print("🧹 Cleared saved Upstox tokens from Redis and disk.")


def token_is_fresh(max_age_hours: int = 24) -> bool:
    data = load_saved_tokens()
    if not data.get("access_token") or not data.get("saved_at"):
        return False
    try:
        saved_time = datetime.fromisoformat(data["saved_at"])
        if saved_time.tzinfo is None:
            saved_time = saved_time.replace(tzinfo=timezone.utc)
        
        now = datetime.now(timezone.utc)
        
        # 1. Check max age limit (24h)
        if (now - saved_time) >= timedelta(hours=max_age_hours):
            return False
        
        # 2. Check 3:30 AM IST daily cutoff (Upstox official token expiry rule)
        saved_ist = saved_time.astimezone(INDIA_TZ)
        now_ist = now.astimezone(INDIA_TZ)
        
        # Cutoff is 3:30 AM IST of the following calendar day relative to saved_ist
        cutoff_date = (saved_ist + timedelta(days=1)).date()
        cutoff_time = INDIA_TZ.localize(datetime(cutoff_date.year, cutoff_date.month, cutoff_date.day, 3, 30, 0))
        
        return now_ist < cutoff_time
    except Exception as e:
        print("⚠️ token_is_fresh check error:", e)
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
