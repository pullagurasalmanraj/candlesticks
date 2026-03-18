# extensions.py
# ================================================================
#  Flask extensions and shared singletons (Redis, OAuth).
#  Import `redis_client`, `REDIS_ENABLED` from here.
#  Import `oauth`, `google` from here.
# ================================================================
import json

try:
    import redis as redis_lib
except Exception:
    redis_lib = None

from config import REDIS_URL, SECRET_KEY

# ── Redis ────────────────────────────────────────────────────────
REDIS_ENABLED = False
redis_client  = None

if redis_lib is not None:
    try:
        redis_client = redis_lib.Redis.from_url(REDIS_URL, decode_responses=True)
        redis_client.ping()
        REDIS_ENABLED = True
        print("✅ Connected to Redis:", REDIS_URL)
    except Exception as e:
        print("⚠️  Redis connection failed:", e)
else:
    print("⚠️  redis library not available; Redis features disabled")

# ── OAuth (Authlib) ──────────────────────────────────────────────
# Call init_oauth(app) once in app.py after Flask app is created.
from authlib.integrations.flask_client import OAuth

oauth  = OAuth()
google = None   # assigned after init_oauth()

def init_oauth(app):
    global google
    oauth.init_app(app)
    google = oauth.register(
        name="google",
        client_id=app.config.get("GOOGLE_CLIENT_ID"),
        client_secret=app.config.get("GOOGLE_CLIENT_SECRET"),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    return google
