# config.py
# ================================================================
#  Centralised configuration — all env vars in one place.
#  Import from here everywhere instead of calling os.getenv()
#  scattered across files.
# ================================================================
import os
import pytz
from requests.sessions import Session as RequestsSession

# ── Timezone ─────────────────────────────────────────────────────
INDIA_TZ = pytz.timezone("Asia/Kolkata")

# ── Paths ────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "../frontend/dist")
TOKENS_FILE = os.path.join(BASE_DIR, "tokens.json")
ENV_FILE = os.path.join(BASE_DIR, ".env")

# ── Upstox ───────────────────────────────────────────────────────
UPSTOX_CLIENT_ID = os.getenv("UPSTOX_CLIENT_ID", "").strip()
UPSTOX_CLIENT_SECRET = os.getenv("UPSTOX_CLIENT_SECRET", "").strip()
UPSTOX_REDIRECT_URI = os.getenv("UPSTOX_REDIRECT_URI", "http://localhost/").strip()
UPSTOX_API_BASE = os.getenv("UPSTOX_API_BASE", "https://api.upstox.com/v2")
UPSTOX_V3_BASE = os.getenv("UPSTOX_V3_BASE", "https://api.upstox.com/v3")

# ── PostgreSQL ───────────────────────────────────────────────────
PG_HOST = os.getenv("PGHOST", "127.0.0.1")
PG_PORT = int(os.getenv("PGPORT", "5432"))
PG_DB = os.getenv("PGDATABASE", "trading_db")
PG_USER = os.getenv("PGUSER", "postgres")
PG_PASSWORD = os.getenv("PGPASSWORD", "postgres")

# ── Redis ────────────────────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "redis://:linux123@127.0.0.1:6379/10")

# ── Flask ────────────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", "candlesticks_super_secret_key")

# ── HTTP session (no proxy) ──────────────────────────────────────
safe_requests = RequestsSession()
safe_requests.trust_env = False
