# routes/logos.py
# ================================================================
#  Logo blueprint:
#    GET  /api/logo/<symbol>     — resolve single symbol → 302 redirect
#    POST /api/logo/batch        — resolve many symbols in one call
#    POST /api/logo/seed         — batch seed all equity symbols from DB
#
#  Key optimisations vs old version:
#  - Non-equity symbols (options, futures) rejected instantly with 204
#    before any DB/Redis/API call — eliminates the flood of 404s from
#    options chain requests like "TCS 2120 CE 28 APR 26"
#  - /api/logo/batch lets the frontend send all visible symbols in one
#    HTTP request instead of one request per symbol — eliminates the
#    N×API-call thundering herd that caused dashboard lag
#  - Null results are cached (Redis 1d, DB) so repeated requests for
#    the same unknown symbol cost nothing after the first call
# ================================================================
import traceback
from flask import Blueprint, redirect, jsonify, request, Response

from services.logo_service import (
    resolve_logo_domain,
    resolve_logos_batch,
    _is_equity_symbol,
    LOGO_DEV_KEY,
    LOGO_DEV_SECRET,
)
from db import get_db_conn

logos_bp = Blueprint("logos", __name__)


@logos_bp.route("/api/logo/<symbol>")
def get_stock_logo(symbol):
    """
    Resolves domain for a single symbol and redirects to logo.dev CDN.
    Returns 204 (no content) for non-equity symbols so the browser
    doesn't log a 404 and the frontend can show initials immediately.
    Returns 404 only for equity symbols where no domain was found.
    """
    try:
        sym = symbol.upper().strip()

        # Fast reject without touching Redis/DB/API
        if not _is_equity_symbol(sym):
            return Response(status=204)

        domain = resolve_logo_domain(sym)

        if not domain:
            return Response(status=404)

        logo_url = (
            f"https://img.logo.dev/{domain}?token={LOGO_DEV_KEY}"
            f"&size=256&format=png"
        )
        resp = redirect(logo_url, code=302)
        resp.headers["X-Logo-Domain"] = domain
        resp.headers["Cache-Control"] = "public, max-age=604800"  # 7 days
        return resp

    except Exception:
        traceback.print_exc()
        return Response(status=500)


@logos_bp.route("/api/logo/batch", methods=["POST"])
def get_logos_batch():
    """
    Resolve logos for multiple symbols in a single request.
    Eliminates the N-per-symbol request flood that caused dashboard lag.

    Request:  POST /api/logo/batch
              { "symbols": ["TCS", "RELIANCE", "TCS 2120 CE 28 APR 26", ...] }

    Response: { "logos": { "TCS": "https://img.logo.dev/tcs.com?token=...",
                            "RELIANCE": "https://img.logo.dev/relianceindustries.com?token=...",
                            "TCS 2120 CE 28 APR 26": null } }

    Non-equity symbols return null immediately with no API calls.
    Already-cached symbols return instantly from Redis.
    Only genuinely new equity symbols hit logo.dev.
    """
    try:
        data    = request.get_json(force=True) or {}
        symbols = data.get("symbols") or []

        if not symbols or not isinstance(symbols, list):
            return jsonify({"error": "symbols array required"}), 400

        # Cap at 200 per batch to prevent abuse
        symbols = symbols[:200]

        domain_map = resolve_logos_batch(symbols)

        # Build logo URL map — None stays None (frontend shows initials)
        logos = {}
        for sym, domain in domain_map.items():
            if domain:
                logos[sym] = (
                    f"https://img.logo.dev/{domain}?token={LOGO_DEV_KEY}"
                    f"&size=256&format=png"
                )
            else:
                logos[sym] = None

        return jsonify({"logos": logos})

    except Exception:
        traceback.print_exc()
        return jsonify({"error": "internal error"}), 500


@logos_bp.route("/api/logo/seed", methods=["POST"])
def seed_logos():
    """
    Batch resolve logos for all equity symbols in DB.
    Skips options/futures automatically.
    Call once after instrument sync.
    """
    try:
        with get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT trading_symbol
                    FROM instruments
                    WHERE is_active = TRUE
                      AND segment IN ('NSE_EQ', 'BSE_EQ')
                      AND trading_symbol IS NOT NULL
                    ORDER BY trading_symbol
                    """
                )
                symbols = [row[0] for row in cur.fetchall()]

        # Filter to equity only before any API work
        equity_symbols = [s for s in symbols if _is_equity_symbol(s)]

        resolved = 0
        failed   = 0

        for sym in equity_symbols:
            try:
                domain = resolve_logo_domain(sym)
                if domain:
                    resolved += 1
                else:
                    failed += 1
            except Exception:
                failed += 1

        return jsonify({
            "status":   "SUCCESS",
            "total":    len(equity_symbols),
            "resolved": resolved,
            "failed":   failed,
            "skipped":  len(symbols) - len(equity_symbols),
        })

    except Exception:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
