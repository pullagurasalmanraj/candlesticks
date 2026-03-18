# routes/auth.py
# ================================================================
#  Authentication blueprint:
#    POST /api/login
#    POST /api/signup
#    GET  /auth/google
#    GET  /auth/google/callback
#    GET  /auth/login         (Upstox OAuth start)
#    GET  /                   (Upstox OAuth callback)
#    GET  /login-success
# ================================================================
import traceback
from urllib.parse import quote

from flask import (
    Blueprint, request, jsonify, session,
    redirect, url_for, send_from_directory,
)
from werkzeug.security import generate_password_hash, check_password_hash

from config                  import (UPSTOX_API_BASE, UPSTOX_CLIENT_ID,
                                     UPSTOX_CLIENT_SECRET, UPSTOX_REDIRECT_URI,
                                     FRONTEND_DIR, safe_requests)
from db                      import get_db_conn
from services.token_service  import save_tokens, token_is_fresh
from extensions              import google   # registered in app.py via init_oauth()

auth_bp = Blueprint("auth", __name__)


# ── Email / password login ───────────────────────────────────────
@auth_bp.route("/api/login", methods=["POST"])
def login_user():
    data     = request.json or {}
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    with get_db_conn() as db:
        with db.cursor() as cur:
            cur.execute("SELECT password_hash FROM users WHERE username=%s", (username,))
            row = cur.fetchone()

    if not row:
        return jsonify({"error": "Invalid username"}), 401
    if not check_password_hash(row[0], password):
        return jsonify({"error": "Invalid password"}), 401

    session["user"] = username
    return jsonify({"success": True})


# ── Email / password signup ──────────────────────────────────────
@auth_bp.route("/api/signup", methods=["POST"])
def signup():
    data     = request.json or {}
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    hashed = generate_password_hash(password)
    try:
        with get_db_conn() as db:
            with db.cursor() as cur:
                cur.execute(
                    "INSERT INTO users(username, password_hash) VALUES(%s, %s)",
                    (username, hashed),
                )
        return jsonify({"success": True})
    except Exception:
        return jsonify({"error": "Username already exists"}), 409


# ── Google OAuth ─────────────────────────────────────────────────
@auth_bp.route("/auth/google")
def google_login():
    redirect_uri = url_for("auth.google_callback", _external=True)
    return google.authorize_redirect(redirect_uri)


@auth_bp.route("/auth/google/callback")
def google_callback():
    try:
        token     = google.authorize_access_token()
        email     = token["userinfo"]["email"]

        with get_db_conn() as db:
            with db.cursor() as cur:
                cur.execute("SELECT username FROM users WHERE username=%s", (email,))
                if not cur.fetchone():
                    cur.execute(
                        "INSERT INTO users(username, password_hash) VALUES(%s, %s)",
                        (email, ""),
                    )

        session["user"] = email
        return redirect(f"/login-success?via=google&user={quote(email)}")

    except Exception:
        traceback.print_exc()
        return redirect("/login?error=google_failed")


# ── Upstox OAuth start ───────────────────────────────────────────
@auth_bp.route("/auth/login")
def auth_login():
    auth_url = (
        f"{UPSTOX_API_BASE}/login/authorization/dialog"
        f"?client_id={UPSTOX_CLIENT_ID}"
        f"&redirect_uri={UPSTOX_REDIRECT_URI}"
        f"&response_type=code"
    )
    return redirect(auth_url)


# ── Upstox OAuth callback (lands on /) ──────────────────────────
@auth_bp.route("/", methods=["GET"])
def root_or_callback():
    code = request.args.get("code")
    if code:
        try:
            r = safe_requests.post(
                f"{UPSTOX_API_BASE}/login/authorization/token",
                data={
                    "code": code,
                    "client_id": UPSTOX_CLIENT_ID,
                    "client_secret": UPSTOX_CLIENT_SECRET,
                    "redirect_uri": UPSTOX_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
                timeout=15,
            )
            data = r.json()
            if r.status_code == 200 and "access_token" in data:
                save_tokens(data)
                return redirect(f"/login-success?token={data['access_token']}")
            return f"<h3>Token exchange failed</h3><pre>{data}</pre>", 400
        except Exception as e:
            traceback.print_exc()
            return f"<h3>Server error</h3><pre>{e}</pre>", 500

    if token_is_fresh():
        return send_from_directory(FRONTEND_DIR, "index.html")
    return redirect("/auth/login")


@auth_bp.route("/login-success")
def login_success():
    response = send_from_directory(FRONTEND_DIR, "index.html")
    response.headers["Cache-Control"] = "no-store"
    return response
