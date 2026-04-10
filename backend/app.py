# app.py
# ================================================================
#  Entry point — creates Flask app, wires extensions and blueprints.
#  All route logic lives in routes/*.py
#  All business logic lives in services/*.py
#  Config lives in config.py
# ================================================================
import os
import warnings

from dotenv import load_dotenv


# In containers, compose-provided env vars must win over local .env values.
# Keeping override=False still loads missing vars for local development.
load_dotenv(override=False)
warnings.filterwarnings("ignore")

from flask import Flask, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix

from config import FRONTEND_DIR, SECRET_KEY, BASE_DIR
from extensions import init_oauth

# ── Create app ───────────────────────────────────────────────────
app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
app.secret_key = SECRET_KEY
app.config.update(
    SECRET_KEY=SECRET_KEY,
    GOOGLE_CLIENT_ID=os.getenv("GOOGLE_CLIENT_ID"),
    GOOGLE_CLIENT_SECRET=os.getenv("GOOGLE_CLIENT_SECRET"),
    SESSION_COOKIE_NAME="candlesticks_session",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,  # set True when HTTPS
)

# ── Middleware ───────────────────────────────────────────────────
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# ── OAuth ────────────────────────────────────────────────────────
init_oauth(app)

# ── Symbol map — must load before blueprints, works under both python app.py and gunicorn ──
from utils.symbol_map import load_symbol_map

load_symbol_map()

# ── Register blueprints ──────────────────────────────────────────
from routes.auth import auth_bp
from routes.market import market_bp
from routes.candles import candles_bp
from routes.instruments import instruments_bp
from routes.indicators import indicators_bp
from routes.strategy import strategy_bp
from routes.ml import ml_bp
from routes.live import live_bp
from routes.logos import logos_bp


app.register_blueprint(auth_bp)
app.register_blueprint(market_bp)
app.register_blueprint(candles_bp)
app.register_blueprint(instruments_bp)
app.register_blueprint(indicators_bp)
app.register_blueprint(strategy_bp)
app.register_blueprint(ml_bp)
app.register_blueprint(live_bp)
app.register_blueprint(logos_bp)


# ── Static SPA catch-all ─────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    from flask import request, jsonify

    if request.path.startswith("/api/"):
        return jsonify({"error": "API endpoint not found"}), 404
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# ── Startup ──────────────────────────────────────────────────────
if __name__ == "__main__":
    # Sync instruments at boot.
    # If lock exists but instruments table is empty (fresh DB), force re-sync.
    from routes.instruments import sync_instruments_core
    from db import get_db_conn

    def _instrument_table_has_rows():
        try:
            with get_db_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM instruments WHERE is_active = TRUE LIMIT 1")
                    return cur.fetchone() is not None
        except Exception:
            return False

    lock = os.path.join(BASE_DIR, ".instrument_sync.lock")
    needs_sync = not os.path.exists(lock)
    if not needs_sync and not _instrument_table_has_rows():
        print("INFO: instruments table empty, forcing sync despite lock file")
        needs_sync = True

    if needs_sync:
        try:
            sync_instruments_core()
            with open(lock, "w") as f:
                from datetime import datetime, timezone

                f.write(datetime.now(timezone.utc).isoformat())
        except Exception as e:
            print("⚠️  Instrument sync failed:", e)

    # Update India VIX
    try:
        from services.vix_service import update_vix_if_needed

        update_vix_if_needed()
    except Exception as e:
        print("⚠️  VIX update failed:", e)

    # ── Seed Redis from token.json on startup ────────────────────
    # Problem: token.json is written during OAuth (locally or in a previous run)
    # but Redis is empty on every fresh Docker start. wsserver reads ONLY from
    # Redis, so without this seed it loops forever with "No token in Redis".
    # Fix: load_saved_tokens() falls back to token.json when Redis is empty,
    # then save_tokens() writes it back to Redis so wsserver can find it.
    try:
        from extensions import REDIS_ENABLED, redis_client
        from services.token_service import load_saved_tokens, save_tokens

        if REDIS_ENABLED and redis_client:
            existing = redis_client.get("upstox:tokens")
            if existing:
                print("✅ Redis already has token — no seed needed")
            else:
                tokens = load_saved_tokens()  # reads token.json as fallback
                if tokens.get("access_token"):
                    save_tokens(tokens)       # writes to Redis + token.json
                    print("✅ Token seeded into Redis from token.json")
                else:
                    print("⚠️  No saved token found — complete Upstox OAuth to generate one")
        else:
            print("⚠️  Redis not available at startup — wsserver will not receive token")
    except Exception as e:
        print("⚠️  Token seed failed:", e)
    # ─────────────────────────────────────────────────────────────

    app.run(host="0.0.0.0", port=8000, debug=False)
