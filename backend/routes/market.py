# routes/market.py
# ================================================================
#  Market data blueprint:
#    GET  /api/index-summary
#    GET  /api/ws-subscribe
#    POST /api/unsubscribe
# ================================================================
import json, time as systime
from datetime import datetime, time as dtime

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
    as_of  = datetime.now(INDIA_TZ).isoformat()

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
        "Nifty 50":      "NSE_INDEX|Nifty 50",
        "Bank Nifty":    "NSE_INDEX|Nifty Bank",
        "Sensex":        "BSE_INDEX|SENSEX",
        "Nifty Next 50": "NSE_INDEX|Nifty Next 50",
    }
    symbols = ",".join(INDEX_KEYS.values())
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}

    quote_url = f"{UPSTOX_API_BASE}/market-quote/quotes?instrument_key={symbols}"
    response = safe_requests.get(quote_url, headers=headers, timeout=10)

    if response.status_code == 401:
        if refresh_upstox_token():
            headers["Authorization"] = f"Bearer {load_saved_tokens().get('access_token')}"
            response = safe_requests.get(quote_url, headers=headers, timeout=10)
        else:
            return jsonify({"error": "Session expired — login again"}), 401

    if response.status_code != 200:
        if _last_market_data:
            stale = dict(_last_market_data)
            stale["status"] = "stale"
            stale["warning"] = "Live index summary unavailable; serving stale cache"
            return jsonify(stale), 200
        return jsonify({
            "status": "degraded",
            "indices": {},
            "marketSummary": {"title": "Market Data Unavailable", "avg_percent": 0},
            "asOf": as_of,
            "warning": "Live index summary unavailable",
            "details": response.text,
        }), 200

    data_raw = (response.json() or {}).get("data", {})
    rows_by_key = {}
    if isinstance(data_raw, dict):
        for map_key, row in data_raw.items():
            if not isinstance(row, dict):
                continue
            row_key = str(row.get("instrument_token") or map_key).replace(":", "|")
            rows_by_key[row_key.upper()] = row
            rows_by_key[str(map_key).replace(":", "|").upper()] = row
    elif isinstance(data_raw, list):
        for row in data_raw:
            if not isinstance(row, dict):
                continue
            row_key = str(
                row.get("instrument_token")
                or row.get("instrument_key")
                or ""
            ).replace(":", "|")
            if row_key:
                rows_by_key[row_key.upper()] = row

    summary = {}
    total_pct, count = 0, 0

    for name, key in INDEX_KEYS.items():
        row = rows_by_key.get(key.upper())
        if not row:
            continue

        def safe(v):
            try:    return round(float(v), 2)
            except: return 0

        ohlc = row.get("ohlc") if isinstance(row.get("ohlc"), dict) else {}
        ltp = safe(row.get("ltp", row.get("last_price")))
        prev_close = safe(row.get("cp", row.get("close", ohlc.get("close"))))
        open_px = safe(row.get("open", ohlc.get("open")))
        high_px = safe(row.get("high", ohlc.get("high")))
        low_px = safe(row.get("low", ohlc.get("low")))
        change = safe(row.get("change", row.get("net_change", ltp - prev_close)))
        percent = safe(
            row.get(
                "percent_change",
                ((change / prev_close) * 100.0) if prev_close else 0.0,
            )
        )

        summary[name] = {
            "symbol": key, "displayName": name, "ltp": ltp,
            "open": open_px, "high": high_px,
            "low": low_px, "prevClose": prev_close,
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
def _resolve_one_instrument_key(raw_symbol: str, exchange: str = ""):
    symbol_raw = (raw_symbol or "").strip()
    if not symbol_raw:
        return None, None, "symbol missing"

    if "|" in symbol_raw:
        return symbol_raw, symbol_raw, None

    symbol = symbol_raw.upper()
    mapped = SYMBOL_TO_KEY.get(symbol)
    if not mapped:
        return None, None, f"Symbol not found: {symbol}"

    if isinstance(mapped, str):
        return mapped, symbol, None

    if isinstance(mapped, dict):
        instrument_key = mapped.get(exchange) or mapped.get("NSE") or list(mapped.values())[0]
        return instrument_key, symbol, None

    return None, None, "Invalid mapping format"


def _collect_subscribe_targets():
    body = request.get_json(silent=True) or {}
    exchange = (
        body.get("exchange")
        or request.args.get("exchange")
        or ""
    ).strip().upper()

    raw_targets = []

    # GET compatibility
    if request.args.get("symbol"):
        raw_targets.append(request.args.get("symbol"))
    raw_targets.extend(request.args.getlist("symbols"))
    raw_targets.extend(request.args.getlist("instrument_key"))
    raw_targets.extend(request.args.getlist("instrument_keys"))

    # POST payload support
    if body.get("symbol"):
        raw_targets.append(body.get("symbol"))
    if isinstance(body.get("symbols"), list):
        raw_targets.extend(body.get("symbols"))
    if body.get("instrument_key"):
        raw_targets.append(body.get("instrument_key"))
    if isinstance(body.get("instrument_keys"), list):
        raw_targets.extend(body.get("instrument_keys"))

    split_targets = []
    for raw in raw_targets:
        if raw is None:
            continue
        txt = str(raw).strip()
        if not txt:
            continue
        if "," in txt:
            split_targets.extend([x.strip() for x in txt.split(",") if x.strip()])
        else:
            split_targets.append(txt)

    unique_raw = list(dict.fromkeys(split_targets))

    resolved_keys = []
    resolved_symbols = []
    errors = []
    for raw in unique_raw:
        key, symbol, err = _resolve_one_instrument_key(raw, exchange=exchange)
        if err:
            errors.append({"input": raw, "error": err})
            continue
        resolved_keys.append(key)
        resolved_symbols.append(symbol)

    resolved_keys = list(dict.fromkeys(resolved_keys))
    resolved_symbols = list(dict.fromkeys(resolved_symbols))

    return resolved_keys, resolved_symbols, errors, bool(body.get("replace"))


@market_bp.route("/api/ws-subscribe", methods=["GET", "POST"])
def api_ws_subscribe():
    import traceback
    try:
        keys, symbols, errors, replace = _collect_subscribe_targets()
        if not keys:
            if errors:
                return jsonify({"error": "No valid symbol/instrument_key", "details": errors}), 400
            return jsonify({"error": "symbol missing"}), 400

        redis_client.publish("subscribe:requests", json.dumps({
            "instrument_keys": keys,
            "symbols": symbols,
            "action": "subscribe",
            "replace": replace,
        }))

        return jsonify({
            "status": "subscribed",
            "instrument_keys": keys,
            "symbols": symbols,
            "replace": replace,
            "invalid": errors,
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@market_bp.route("/api/unsubscribe", methods=["POST"])
def api_unsubscribe():
    payload = request.get_json(silent=True) or {}
    keys = []

    if payload.get("instrument_key"):
        keys.append(payload.get("instrument_key"))
    if isinstance(payload.get("instrument_keys"), list):
        keys.extend(payload.get("instrument_keys"))
    if isinstance(payload.get("unsubscribe"), list):
        keys.extend(payload.get("unsubscribe"))

    keys = [str(k).strip() for k in keys if str(k or "").strip()]
    keys = list(dict.fromkeys(keys))

    if not keys:
        return jsonify({"error": "instrument_key missing"}), 400

    redis_client.publish("unsubscribe:requests", json.dumps({
        "instrument_keys": keys,
        "method": "unsub",
        "action": "unsubscribe",
    }))
    return jsonify({"status": "unsubscribed", "instrument_keys": keys})


@market_bp.route("/api/unsubscribe-all", methods=["POST"])
def api_unsubscribe_all():
    try:
        all_keys = list(redis_client.smembers("active_subscriptions") or [])
        keys = [
            ik for ik in all_keys
            if not str(ik or "").upper().startswith(("NSE_INDEX|", "BSE_INDEX|"))
        ]
        for ik in keys:
            redis_client.publish("unsubscribe:requests", json.dumps({
                "instrument_key": ik, "method": "unsub", "action": "unsubscribe",
            }))
        if keys:
            redis_client.srem("active_subscriptions", *keys)
        return jsonify({
            "status": "ok",
            "unsubscribed_count": len(keys),
            "instrument_keys": keys,
            "preserved_index_keys": [ik for ik in all_keys if ik not in keys],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


