# routes/candles.py
# ================================================================
#  Candle data blueprint:
#    POST /api/candles/store     — intraday candles
#    POST /api/candles/history   — historical (chunked)
#    POST /api/candles/daily     — daily candles
#    GET  /api/history/daily     — download as Excel
#    GET  /api/timeframes
#    GET  /api/date-ranges
# ================================================================
import traceback
from datetime import datetime, date
from urllib.parse import quote
from io import BytesIO

import pandas as pd
import ta
from dateutil.relativedelta import relativedelta
from flask import Blueprint, request, jsonify, send_file, make_response
from psycopg2.extras import execute_batch

from config                 import UPSTOX_V3_BASE, safe_requests
from db                     import get_db_conn
from services.token_service import get_valid_token
from utils.symbol_map       import SYMBOL_TO_KEY

candles_bp = Blueprint("candles", __name__)


def detect_exchange(instrument_key: str) -> str:
    key = instrument_key.upper()
    if "NSE" in key: return "NSE"
    if "BSE" in key: return "BSE"
    return "UNKNOWN"


# ── Timeframes ───────────────────────────────────────────────────
# DB stores value as "1","3","5","15","30" and label as "1 Minute" etc.
# Frontend needs short display like "1m","3m" — mapped here so DB needs no migration.
_TF_DISPLAY = {
    "1":   "1m",
    "3":   "3m",
    "5":   "5m",
    "15":  "15m",
    "30":  "30m",
    "60":  "1h",
    "1m":  "1m",
    "3m":  "3m",
    "5m":  "5m",
    "15m": "15m",
    "30m": "30m",
    "1h":  "1h",
}

@candles_bp.route("/api/timeframes", methods=["GET"])
def api_timeframes():
    try:
        with get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT tf_value, label FROM timeframes ORDER BY id ASC")
                rows = cur.fetchall()
        return jsonify({"timeframes": [
            {
                "value":   v,                        # raw DB value — "1", "5" etc
                "label":   _TF_DISPLAY.get(v, v),   # short display — "1m", "5m" etc
                "display": _TF_DISPLAY.get(v, v),   # alias for frontend convenience
            }
            for v, l in rows
        ]})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e), "timeframes": []}), 500


# ── Date ranges ──────────────────────────────────────────────────
@candles_bp.route("/api/date-ranges", methods=["GET"])
def api_date_ranges():
    try:
        with get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT code, label, days_back_start, days_back_end FROM date_ranges ORDER BY id")
                rows = cur.fetchall()
        return jsonify({"ranges": [
            {"code": c, "label": l, "days_back_start": s, "days_back_end": e}
            for c, l, s, e in rows
        ]})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e), "ranges": []}), 500


# ── Store intraday candles ───────────────────────────────────────
@candles_bp.route("/api/candles/store", methods=["POST"])
def api_candles_store():
    try:
        payload        = request.get_json(force=True) or {}
        instrument_key = payload.get("instrument_key", "").strip()
        timeframe      = payload.get("timeframe", "").strip()
        if not instrument_key or not timeframe:
            return jsonify({"error": "instrument_key and timeframe required"}), 400

        symbol   = (payload.get("symbol") or "").strip().upper() or instrument_key.split("|")[-1].upper()
        exchange = detect_exchange(instrument_key)

        token = get_valid_token()
        if not token:
            return jsonify({"error": "No Upstox access token"}), 401

        url = f"{UPSTOX_V3_BASE}/historical-candle/intraday/{instrument_key}/minutes/{timeframe}"
        r   = safe_requests.get(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}, timeout=20)

        if r.status_code != 200:
            return jsonify({"error": "Upstox API error", "details": r.json()}), r.status_code

        candles = (r.json() or {}).get("data", {}).get("candles", [])
        if not candles:
            return jsonify({"status": "success", "inserted": 0, "total": 0})

        start_dt = datetime.fromisoformat(payload["start_date"]).date() if payload.get("start_date") else None
        end_dt   = datetime.fromisoformat(payload["end_date"]).date()   if payload.get("end_date")   else None

        rows = []
        for c in candles:
            try:
                ts = datetime.fromisoformat(c[0])
                if start_dt and ts.date() < start_dt: continue
                if end_dt   and ts.date() > end_dt:   continue
                o, h, l, cl = map(float, c[1:5])
                v = int(c[5]) if c[5] not in (None, "") else 0
                rows.append((symbol, exchange, ts, o, h, l, cl, v, timeframe))
            except Exception:
                continue

        if rows:
            with get_db_conn() as conn:
                with conn.cursor() as cur:
                    execute_batch(cur, """
                        INSERT INTO intraday_candles (symbol,exchange,timestamp,open,high,low,close,volume,timeframe)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (symbol,exchange,timestamp,timeframe)
                        DO UPDATE SET open=EXCLUDED.open,high=EXCLUDED.high,low=EXCLUDED.low,
                                      close=EXCLUDED.close,volume=EXCLUDED.volume
                    """, rows, page_size=500)

        return jsonify({"status": "success", "symbol": symbol, "exchange": exchange,
                        "timeframe": timeframe, "inserted": len(rows), "total": len(candles)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ── Historical candles (chunked) ─────────────────────────────────
@candles_bp.route("/api/candles/history", methods=["POST"])
def api_candles_history():
    try:
        payload        = request.get_json(force=True) or {}
        instrument_key = payload.get("instrument_key", "").strip()
        symbol         = payload.get("symbol", "").strip().upper()
        timeframe      = payload.get("timeframe", "").strip()
        start_date     = payload.get("start_date", "").strip()
        end_date       = payload.get("end_date",   "").strip()

        if not all([instrument_key, symbol, timeframe, start_date, end_date]):
            return jsonify({"error": "instrument_key, symbol, timeframe, start_date, end_date required"}), 400

        exchange = detect_exchange(instrument_key)
        TF_MAP   = {"1m":"1","3m":"3","5m":"5","15m":"15","30m":"30","60m":"60"}
        api_tf   = TF_MAP.get(timeframe.lower(), timeframe)

        token = get_valid_token()
        if not token:
            return jsonify({"error": "No Upstox access token"}), 401

        start_dt = date.fromisoformat(min(start_date, end_date))
        end_dt   = date.fromisoformat(max(start_date, end_date))

        tf = str(timeframe).strip().lower()
        if tf.isdigit():       tf = f"{tf}m"
        if tf.endswith("m"):   category = "minutes"; interval = int(tf[:-1])
        elif tf.endswith("h"): category = "hours";   interval = int(tf[:-1])
        elif tf.endswith("d"): category = "days";    interval = 1
        else: return jsonify({"error": "Unsupported timeframe"}), 400

        delta = relativedelta(months=1 if interval <= 15 else 3) if category == "minutes" \
                else relativedelta(months=3) if category == "hours" \
                else relativedelta(years=10)

        chunks = []
        cur = start_dt
        while cur <= end_dt:
            chunk_to = min(cur + delta - relativedelta(days=1), end_dt)
            chunks.append((cur, chunk_to))
            cur = chunk_to + relativedelta(days=1)

        headers        = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        total_inserted = 0
        total_received = 0

        for cf, ct in chunks:
            url = f"{UPSTOX_V3_BASE}/historical-candle/{instrument_key}/minutes/{api_tf}/{ct}/{cf}"
            r   = safe_requests.get(url, headers=headers, timeout=30)
            if r.status_code != 200:
                return jsonify({"error": "Upstox API error", "details": r.json()}), r.status_code

            candles = (r.json() or {}).get("data", {}).get("candles", [])
            total_received += len(candles)
            rows = []
            for c in candles:
                try:
                    ts = datetime.fromisoformat(c[0])
                    o, h, l, cl = map(float, c[1:5])
                    v = int(c[5]) if c[5] else 0
                    rows.append((symbol, exchange, ts, o, h, l, cl, v, api_tf))
                except Exception:
                    continue

            if rows:
                with get_db_conn() as conn:
                    with conn.cursor() as cur_db:
                        execute_batch(cur_db, """
                            INSERT INTO intraday_candles (symbol,exchange,timestamp,open,high,low,close,volume,timeframe)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            ON CONFLICT (symbol,exchange,timestamp,timeframe)
                            DO UPDATE SET open=EXCLUDED.open,high=EXCLUDED.high,low=EXCLUDED.low,
                                          close=EXCLUDED.close,volume=EXCLUDED.volume
                        """, rows, page_size=500)
                total_inserted += len(rows)

        return jsonify({"status": "success", "symbol": symbol, "exchange": exchange,
                        "timeframe": timeframe, "stored_tf": api_tf, "chunks": len(chunks),
                        "inserted": total_inserted, "total": total_received,
                        "from_date": str(start_dt), "to_date": str(end_dt)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ── Daily candles ────────────────────────────────────────────────
@candles_bp.route("/api/candles/daily", methods=["POST"])
def api_daily_candles():
    try:
        payload        = request.json or {}
        symbol         = payload.get("symbol", "").upper().strip()
        instrument_key = payload.get("instrument_key", "").strip()
        start_date     = payload.get("start_date")
        end_date       = payload.get("end_date")

        if not all([symbol, instrument_key, start_date, end_date]):
            return jsonify({"error": "symbol, instrument_key, start_date, end_date required"}), 400

        exchange = detect_exchange(instrument_key)
        token    = get_valid_token()
        if not token:
            return jsonify({"error": "Missing Upstox access token"}), 401

        encoded_key = quote(instrument_key, safe="")
        url = f"{UPSTOX_V3_BASE}/historical-candle/{encoded_key}/days/1/{end_date}/{start_date}"
        r   = safe_requests.get(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}, timeout=30)

        if r.status_code != 200:
            return jsonify({"error": "Upstox API Error", "details": r.text}), r.status_code

        candles = (r.json() or {}).get("data", {}).get("candles", [])
        if not candles:
            return jsonify({"status": "success", "inserted": 0, "total": 0})

        rows = []
        for c in candles:
            try:
                ts = datetime.fromisoformat(c[0])
                o, h, l, cl, vol = map(float, c[1:6])
                rows.append((symbol, exchange, ts, o, h, l, cl, int(vol), "1D"))
            except Exception as e:
                print("⚠️  Candle skipped:", c, e)

        with get_db_conn() as conn:
            with conn.cursor() as cur:
                execute_batch(cur, """
                    INSERT INTO daily_candles (symbol,exchange,timestamp,open,high,low,close,volume,timeframe)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (symbol,exchange,timestamp)
                    DO UPDATE SET open=EXCLUDED.open,high=EXCLUDED.high,low=EXCLUDED.low,
                                  close=EXCLUDED.close,volume=EXCLUDED.volume,timeframe=EXCLUDED.timeframe
                """, rows, page_size=300)

        return jsonify({"status": "success", "symbol": symbol, "exchange": exchange,
                        "inserted": len(rows), "total": len(candles)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ── Download daily history as Excel ─────────────────────────────
@candles_bp.route("/api/history/daily", methods=["GET"])
def download_daily_upstox():
    try:
        symbol         = request.args.get("symbol", "").upper().strip()
        start_date     = request.args.get("start", "").strip()
        end_date       = request.args.get("end",   "").strip()
        instrument_key = request.args.get("instrument_key", "").strip()

        if not symbol or not start_date or not end_date:
            return jsonify({"error": "symbol, start and end required"}), 400

        if not instrument_key:
            entry = SYMBOL_TO_KEY.get(symbol)
            instrument_key = entry.get("NSE") or entry.get("BSE") \
                if isinstance(entry, dict) else entry
        if not instrument_key:
            return jsonify({"error": f"No instrument key found for {symbol}"}), 404

        token = get_valid_token()
        if not token:
            return jsonify({"error": "No Upstox access token stored"}), 401

        url = f"{UPSTOX_V3_BASE}/historical-candle/{instrument_key}/days/1/{end_date}/{start_date}"
        r   = safe_requests.get(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}, timeout=20)

        if r.status_code != 200:
            return jsonify({"error": "Upstox API error", "details": r.text}), 400

        candles = r.json().get("data", {}).get("candles", [])
        if not candles:
            return jsonify({"error": "No candle data returned"}), 404

        df = pd.DataFrame(candles, columns=["Date","Open","High","Low","Close","Volume","OI"])
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.sort_values("Date")
        df[["Open","High","Low","Close","Volume","OI"]] = df[["Open","High","Low","Close","Volume","OI"]].apply(pd.to_numeric, errors="coerce")
        df["Volume"] = df["Volume"].fillna(0).astype(int)

        close, high, low  = df["Close"], df["High"], df["Low"]
        df["RSI_14"]      = ta.momentum.RSIIndicator(close, 14).rsi()
        df["EMA_20"]      = ta.trend.EMAIndicator(close, 20).ema_indicator()
        df["SMA_20"]      = ta.trend.SMAIndicator(close, 20).sma_indicator()
        macd              = ta.trend.MACD(close)
        df["MACD"]        = macd.macd()
        df["MACD_Signal"] = macd.macd_signal()
        df["MACD_Hist"]   = macd.macd_diff()
        df["ADX_14"]      = ta.trend.ADXIndicator(high, low, close, 14).adx()
        df = df.dropna().reset_index(drop=True)

        if df.empty:
            return jsonify({"error": "Not enough valid rows for indicators"}), 400

        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
        df.insert(0, "Symbol", symbol)
        df.insert(1, "InstrumentKey", instrument_key)

        output = BytesIO()
        df.to_excel(output, index=False, sheet_name="Daily Data")
        output.seek(0)

        resp = make_response(send_file(
            output, as_attachment=True,
            download_name=f"{symbol}_{start_date}_to_{end_date}_DailyTechnical.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ))
        resp.headers["Access-Control-Allow-Origin"]   = "*"
        resp.headers["Access-Control-Expose-Headers"] = "Content-Disposition"
        return resp
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
