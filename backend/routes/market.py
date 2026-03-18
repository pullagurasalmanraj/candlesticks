# routes/market.py
# ================================================================
#  Market data blueprint:
#    GET  /api/index-summary
#    GET  /api/ws-subscribe
#    POST /api/unsubscribe
# ================================================================
import json, time as systime
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from flask import Blueprint, request, jsonify

from config                 import UPSTOX_API_BASE, safe_requests, INDIA_TZ
from extensions             import redis_client, REDIS_ENABLED
from services.token_service import load_saved_tokens, refresh_upstox_token
from utils.symbol_map       import SYMBOL_TO_KEY

market_bp = Blueprint("market", __name__)

_last_market_data = None
_last_market_time = 0


def is_market_open() -> bool:
    now = datetime.now(INDIA_TZ).time()
    return dtime(9, 0) <= now <= dtime(15, 30)


# ── Index summary ────────────────────────────────────────────────
@market_bp.route("/api/index-summary", methods=["GET"])
def index_summary():
    global _last_market_data, _last_market_time

    ttl    = 15 if is_market_open() else 300
    now_ts = systime.time()
    as_of  = datetime.now(ZoneInfo("Asia/Kolkata")).isoformat()

    if REDIS_ENABLED and redis_client:
        try:
            cached = redis_client.get("cache:index_summary")
            if cached:
                return jsonify(json.loads(cached))
        except Exception:
            pass

    if _last_market_data and (now_ts - _last_market_time) < ttl:
        return jsonify(_last_market_data)

    tokens       = load_saved_tokens()
    access_token = tokens.get("access_token")
    if not access_token:
        return jsonify({"error": "Not logged in — connect Upstox"}), 401

    INDEX_KEYS = {
        "Nifty 50":     "NSE_INDEX|NIFTY_50",
        "Bank Nifty":   "NSE_INDEX|BANKNIFTY",
        "Sensex":       "BSE_INDEX|SENSEX",
        "Nifty Next 50":"NSE_INDEX|NIFTY_NEXT_50",
    }
    symbols = ",".join(INDEX_KEYS.values())
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}

    response = safe_requests.get(
        f"{UPSTOX_API_BASE}/v2/market-quote/indices?symbols={symbols}",
        headers=headers, timeout=10,
    )

    if response.status_code == 401:
        if refresh_upstox_token():
            headers["Authorization"] = f"Bearer {load_saved_tokens().get('access_token')}"
            response = safe_requests.get(
                f"{UPSTOX_API_BASE}/v2/market-quote/indices?symbols={symbols}",
                headers=headers, timeout=10,
            )
        else:
            return jsonify({"error": "Session expired — login again"}), 401

    if response.status_code != 200:
        return jsonify({"error": "Upstox API failed", "details": response.text}), 500

    data    = response.json().get("data", [])
    summary = {}
    total_pct, count = 0, 0

    for name, key in INDEX_KEYS.items():
        row = next((x for x in data
                    if x.get("instrument_key") == key
                    or x.get("tradingsymbol") in key), None)
        if not row:
            continue

        def safe(v):
            try:    return round(float(v), 2)
            except: return 0

        ltp     = safe(row.get("ltp"))
        change  = safe(row.get("change"))
        percent = safe(row.get("percent_change"))

        summary[name] = {
            "symbol": key, "displayName": name, "ltp": ltp,
            "open": safe(row.get("open")), "high": safe(row.get("high")),
            "low": safe(row.get("low")), "prevClose": safe(row.get("close")),
            "change": change, "percent": percent,
            "direction": "up" if change >= 0 else "down",
            "source": "Upstox Live",
        }
        total_pct += percent
        count     += 1

    avg_pct = round(total_pct / count, 2) if count else 0
    icon    = "▲" if avg_pct >= 0 else "▼"
    payload = {
        "status": "success", "indices": summary,
        "marketSummary": {
            "title": f"{icon} Market {'UP' if avg_pct >= 0 else 'DOWN'}",
            "avg_percent": avg_pct,
        },
        "asOf": as_of,
    }

    _last_market_data = payload
    _last_market_time = now_ts
    if REDIS_ENABLED and redis_client:
        redis_client.setex("cache:index_summary", ttl, json.dumps(payload))

    return jsonify(payload)


# ── WebSocket subscribe ──────────────────────────────────────────
@market_bp.route("/api/ws-subscribe", methods=["GET"])
def api_ws_subscribe():
    import traceback
    try:
        symbol   = (request.args.get("symbol") or "").strip().upper()
        exchange = (request.args.get("exchange") or "").strip().upper()
        if not symbol:
            return jsonify({"error": "symbol missing"}), 400

        if "|" in symbol:
            instrument_key = symbol
        else:
            mapped = SYMBOL_TO_KEY.get(symbol)
            if not mapped:
                return jsonify({"error": f"Symbol not found: {symbol}"}), 404
            if isinstance(mapped, str):
                instrument_key = mapped
            elif isinstance(mapped, dict):
                instrument_key = mapped.get(exchange) or mapped.get("NSE") or list(mapped.values())[0]
            else:
                return jsonify({"error": "Invalid mapping format"}), 500

        redis_client.publish("subscribe:requests", json.dumps({
            "instrument_key": instrument_key,
            "action": "subscribe", "symbol": symbol,
        }))
        return jsonify({"status": "subscribed", "instrument_key": instrument_key, "symbol": symbol})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ── WebSocket unsubscribe ────────────────────────────────────────
@market_bp.route("/api/unsubscribe", methods=["POST"])
def api_unsubscribe():
    ik = (request.json or {}).get("instrument_key")
    if not ik:
        return jsonify({"error": "instrument_key missing"}), 400
    redis_client.publish("unsubscribe:requests", json.dumps({
        "instrument_key": ik, "method": "unsub", "action": "unsubscribe",
    }))
    return jsonify({"status": "unsubscribed", "instrument_key": ik})
