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


load_dotenv(override=True)
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
    # Sync instruments once at boot (skip if lock file exists)
    from routes.instruments import sync_instruments_core

    lock = os.path.join(BASE_DIR, ".instrument_sync.lock")
    if not os.path.exists(lock):
        try:
            sync_instruments_core()
            with open(lock, "w") as f:
                from datetime import datetime

                f.write(datetime.utcnow().isoformat())
        except Exception as e:
            print("⚠️  Instrument sync failed:", e)

    # Update India VIX
    try:
        from services.vix_service import update_vix_if_needed

        update_vix_if_needed()
    except Exception as e:
        print("⚠️  VIX update failed:", e)

    app.run(host="0.0.0.0", port=8000, debug=False)
