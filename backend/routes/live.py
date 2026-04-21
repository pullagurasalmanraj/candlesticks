# routes/live.py
# ================================================================
#  Live candle engine blueprint:
#    POST /api/start-live-conversion
#    GET  /api/symbol-feedkey
#    GET  /api/ws-subscribe
#    POST /api/unsubscribe
#
# FIXES APPLIED:
#   1. redis_load_candles: raw items from lrange are now str (decode_responses=True
#      in extensions.py), so json.loads(r) works directly — no .decode() needed.
#   2. candle_worker backfill: added defensive str() cast on ts values from i1
#      dict to guard against int vs string inconsistency from protobuf decode.
#   3. /api/start-live-conversion: also publishes a subscribe:requests event so
#      wsserver.py immediately subscribes to the instrument if not already active.
# ================================================================
import json, traceback, threading
from datetime import datetime, time as dtime, date
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import ta
from flask import Blueprint, request, jsonify

from extensions             import redis_client, REDIS_ENABLED
from utils.symbol_map       import SYMBOL_TO_KEY

live_bp = Blueprint("live", __name__)

def _get_ff(feeds: dict, feed_key: str) -> dict:
    """Extract marketFF or indexFF — works for both equity and index instruments."""
    feed = feeds.get(feed_key, {})
    full = feed.get("fullFeed", {})
    return full.get("marketFF") or full.get("indexFF") or {}


IST           = ZoneInfo("Asia/Kolkata")
live_workers  = {}   # symbol → thread


# ── Redis helpers ────────────────────────────────────────────────
def is_index_instrument_key(instrument_key: str) -> bool:
    k = str(instrument_key or "").upper()
    return k.startswith("NSE_INDEX|") or k.startswith("BSE_INDEX|")


def daily_tick_storage_key(instrument_key: str, day_value: date | None = None) -> str:
    day_iso = (day_value or date.today()).isoformat()
    bucket = "index" if is_index_instrument_key(instrument_key) else "instrument"
    return f"ticks:{bucket}:{day_iso}:{instrument_key}"


def redis_store_candle(symbol: str, timeframe: str, candle: dict):
    ts       = int(candle["ts"])
    dt       = datetime.fromtimestamp(ts / 1000, IST)
    if dt.date() != datetime.now(IST).date():
        return
    key = f"candles:{symbol}:{timeframe}:{dt.date().isoformat()}"
    redis_client.zadd(key, {json.dumps(candle): ts})


def redis_load_candles(symbol: str, timeframe: str = "1m", limit: int = 1200) -> pd.DataFrame:
    today = date.today().isoformat()
    key   = f"candles:{symbol}:{timeframe}:{today}"
    raw   = redis_client.zrange(key, 0, -1)
    if not raw:
        return pd.DataFrame()
    candles = []
    for r in raw[-limit:]:
        try:
            # FIX 1: extensions.py uses decode_responses=True so r is already a str.
            # Previously wsserver used decode_responses=False and stored bytes,
            # causing json.loads() to fail silently here.
            candles.append(json.loads(r))
        except Exception:
            continue
    df = pd.DataFrame(candles)
    if df.empty:
        return df
    limit_ts = redis_client.get(f"_bootstrap_limit:{symbol}:{timeframe}")
    if limit_ts:
        try:
            df = df[df["ts"] <= int(limit_ts)]
        except Exception:
            pass
    return df


def compute_and_store_last_n_indicators(symbol: str, timeframe: str = "1m", n: int = 1):
    ML_SEQ_LEN = 200
    df = redis_load_candles(symbol, timeframe, limit=1200)
    if df.empty or len(df) < ML_SEQ_LEN:
        return False

    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True).dt.tz_convert(IST)
    df.sort_values("ts", inplace=True)
    df["date"] = df["ts"].dt.date

    close = df["close"].astype(float)
    high  = df["high"].astype(float)
    low   = df["low"].astype(float)
    vol   = df["volume"].astype(float)

    df["rsi_14"]  = ta.momentum.RSIIndicator(close, 14).rsi()
    df["ema_9"]   = ta.trend.EMAIndicator(close,  9).ema_indicator()
    df["ema_21"]  = ta.trend.EMAIndicator(close, 21).ema_indicator()
    df["ema_50"]  = ta.trend.EMAIndicator(close, 50).ema_indicator()
    df["ema_200"] = ta.trend.EMAIndicator(close,200).ema_indicator()
    macd = ta.trend.MACD(close)
    df["macd"], df["macd_signal"], df["macd_hist"] = macd.macd(), macd.macd_signal(), macd.macd_diff()
    df["atr_14"]     = ta.volatility.AverageTrueRange(high, low, close, 14).average_true_range()
    df["atr_percent"]= df["atr_14"] / close * 100
    bb = ta.volatility.BollingerBands(close, 20, 2)
    df["bollinger_mid"]   = bb.bollinger_mavg()
    df["bollinger_upper"] = bb.bollinger_hband()
    df["bollinger_lower"] = bb.bollinger_lband()
    typical = (high + low + close) / 3
    df["vwap"] = (typical * vol).groupby(df["date"]).cumsum() / vol.groupby(df["date"]).cumsum()

    df["orb_high"] = np.nan
    df["orb_low"]  = np.nan
    for d, day_df in df.groupby("date"):
        orb = day_df[(day_df["ts"].dt.time >= dtime(9,15)) & (day_df["ts"].dt.time <= dtime(9,20))]
        if orb.empty: continue
        df.loc[day_df.index, "orb_high"] = orb["high"].max()
        df.loc[day_df.index, "orb_low"]  = orb["low"].min()

    df["orb_breakout"] = (df["close"] > df["orb_high"]).astype(int)
    df["orb_breakdown"]= (df["close"] < df["orb_low"]).astype(int)
    df["is_open_candle"]= ((df["ts"].dt.hour==9)&(df["ts"].dt.minute==15)).astype(int)
    df["prev_close"]   = df["close"].shift(1)
    df["gap_percent"]  = ((df["open"]-df["prev_close"])/df["prev_close"]*100).fillna(0)
    df["volatility"]   = df["close"].pct_change().rolling(20).std()

    try:
        st = ta.trend.STCIndicator(df["close"])
        supertrend_signal = int(np.sign(st.stc().iloc[-1] - st.stc().iloc[-2]))
    except Exception:
        supertrend_signal = 0

    last       = df.iloc[-1]
    candle_ts  = int(last["ts"].timestamp() * 1000)
    ind_row    = {
        "candle_ts": candle_ts, "candle_time_ist": last["ts"].strftime("%Y-%m-%d %H:%M:%S"),
        "close": float(last["close"]), "rsi_14": float(last["rsi_14"]),
        "ema_9": float(last["ema_9"]), "ema_21": float(last["ema_21"]),
        "ema_50": float(last["ema_50"]), "ema_200": float(last["ema_200"]),
        "macd": float(last["macd"]), "macd_signal": float(last["macd_signal"]),
        "macd_hist": float(last["macd_hist"]), "atr_14": float(last["atr_14"]),
        "atr_percent": float(last["atr_percent"]),
        "bollinger_mid": float(last["bollinger_mid"]),
        "bollinger_upper": float(last["bollinger_upper"]),
        "bollinger_lower": float(last["bollinger_lower"]),
        "volatility": float(last["volatility"]), "gap_percent": float(last["gap_percent"]),
        "vwap": float(last["vwap"]), "orb_high": float(last["orb_high"]),
        "orb_low": float(last["orb_low"]), "orb_breakout": int(last["orb_breakout"]),
        "orb_breakdown": int(last["orb_breakdown"]), "supertrend_signal": supertrend_signal,
        "is_open_candle": int(last["is_open_candle"]), "ml_ready": True, "sequence_len": len(df),
    }
    ind_key = f"live:{symbol}:{timeframe}:indicators"
    redis_client.rpush(ind_key, json.dumps(ind_row))
    redis_client.ltrim(ind_key, -500, -1)
    return True


def bootstrap_indicators(symbol: str, timeframe: str = "1m"):
    df = redis_load_candles(symbol, timeframe)
    if df.empty:
        return False
    df = df.sort_values("ts").reset_index(drop=True)
    ind_key = f"live:{symbol}:{timeframe}:indicators"
    redis_client.delete(ind_key)
    for i in range(len(df)):
        redis_client.set(f"_bootstrap_limit:{symbol}:{timeframe}", int(df.iloc[i]["ts"]))
        compute_and_store_last_n_indicators(symbol, timeframe, n=1)
    redis_client.delete(f"_bootstrap_limit:{symbol}:{timeframe}")
    return True


def minute_bucket(ts_ms: int) -> int:
    return (ts_ms // 60000) * 60000


def candle_worker(symbol: str, feed_key: str):
    today        = date.today()
    MARKET_START = dtime(9, 15)
    MARKET_LAST  = dtime(15, 29)
    MARKET_CLOSE = dtime(15, 30)

    print(f"[CANDLE] Engine started for {symbol} ({today})")

    # Backfill from stored daily ticks
    tick_key = daily_tick_storage_key(feed_key, today)
    raw_items = redis_client.lrange(tick_key, 0, -1)
    if not raw_items:
        # Backward-compatibility: support old mixed namespace key.
        legacy_tick_key = f"ticks:{today.isoformat()}:{feed_key}"
        raw_items = redis_client.lrange(legacy_tick_key, 0, -1)
    backfill   = []
    for raw in raw_items:
        try:
            # FIX 1 (same as above): raw is str because decode_responses=True
            msg  = json.loads(raw)
            feeds= msg.get("data",{}).get("feeds",{})
            if feed_key not in feeds: continue
            ff   = _get_ff(feeds, feed_key)
            ohlc = ff.get("marketOHLC",{}).get("ohlc",[])
            i1   = next((x for x in ohlc if x.get("interval")=="I1"), None)
            if not i1 or "ts" not in i1: continue
            # FIX 2: defensive str() cast before int() — protobuf MessageToDict
            # sometimes returns ts as int, sometimes as string
            backfill.append((int(str(i1["ts"])), i1))
        except Exception:
            continue

    backfill.sort(key=lambda x: x[0])
    last_closed_ts = None
    for ts, i1 in backfill:
        dt = datetime.fromtimestamp(ts/1000, IST)
        if dt.date()!=today or dt.time()<MARKET_START or dt.time()>MARKET_LAST: continue
        if last_closed_ts and ts <= last_closed_ts: continue
        last_closed_ts = ts
        redis_store_candle(symbol, "1m", {
            "ts": ts, "ts_ist": dt.strftime("%Y-%m-%d %H:%M:%S"),
            "open": float(i1["open"]), "high": float(i1["high"]),
            "low": float(i1["low"]), "close": float(i1["close"]),
            "volume": float(i1.get("vol",0)),
        })

    bootstrap_indicators(symbol, "1m")
    print("[CANDLE] Backfill completed → LIVE mode")

    pubsub = redis_client.pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe("ticks:live")
    last_minute_bucket  = None
    last_ohlc_snapshot  = None

    while True:
        if datetime.now(IST).time() >= MARKET_CLOSE:
            print(f"[CANDLE] Market closed — stopping {symbol}")
            break
        message = pubsub.get_message(timeout=1.0)
        if not message or message["type"]!="message": continue
        try:
            # FIX 1: message["data"] is str (decode_responses=True), not bytes
            msg   = json.loads(message["data"])
            feeds = msg.get("data",{}).get("feeds",{})
            if feed_key not in feeds: continue
            ff    = _get_ff(feeds, feed_key)
            ltpc  = ff.get("ltpc")
            if not ltpc or "ltt" not in ltpc: continue
            ltt     = int(str(ltpc["ltt"]))
            tick_dt = datetime.fromtimestamp(ltt/1000, IST)
            if tick_dt.date()!=today or tick_dt.time()<MARKET_START or tick_dt.time()>MARKET_LAST: continue
            current_bucket = minute_bucket(ltt)
            ohlc = ff.get("marketOHLC",{}).get("ohlc",[])
            i1   = next((x for x in ohlc if x.get("interval")=="I1"), None)
            if not i1: continue
            last_ohlc_snapshot = i1
            if last_minute_bucket is None: last_minute_bucket = current_bucket; continue
            if current_bucket == last_minute_bucket: continue
            # close previous minute
            candle_dt = datetime.fromtimestamp(last_minute_bucket/1000, IST)
            redis_store_candle(symbol, "1m", {
                "ts": last_minute_bucket, "ts_ist": candle_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "open": float(last_ohlc_snapshot["open"]), "high": float(last_ohlc_snapshot["high"]),
                "low": float(last_ohlc_snapshot["low"]),   "close": float(last_ohlc_snapshot["close"]),
                "volume": float(last_ohlc_snapshot.get("vol",0)),
            })
            compute_and_store_last_n_indicators(symbol, "1m", n=1)
            last_closed_ts = last_minute_bucket
            last_minute_bucket = current_bucket
        except Exception:
            traceback.print_exc()


# ── Routes ───────────────────────────────────────────────────────
@live_bp.route("/api/start-live-conversion", methods=["POST"])
def start_live_conversion():
    payload   = request.get_json(force=True) or {}
    symbol    = (payload.get("symbol")   or "").upper().strip()
    feed_key  = payload.get("feed_key")
    if not symbol or not feed_key:
        return jsonify({"error": "symbol and feed_key required"}), 400

    worker_key = f"{symbol}:1m"
    if worker_key in live_workers:
        w = live_workers[worker_key]
        if w and w.is_alive():
            return jsonify({"status":"ALREADY_RUNNING","symbol":symbol}), 200
        live_workers.pop(worker_key, None)

    # FIX 3: Publish a subscribe request so wsserver.py immediately subscribes
    # this instrument if it isn't already. Without this the candle worker starts
    # but Upstox sends no ticks because no subscription was ever sent.
    redis_client.publish(
        "subscribe:requests",
        json.dumps({
            "instrument_key": feed_key,
            "action":         "subscribe",
            "symbol":         symbol,
        }),
    )

    worker = threading.Thread(target=candle_worker, args=(symbol, feed_key), daemon=True)
    worker.start()
    live_workers[worker_key] = worker
    return jsonify({"status":"STARTED","symbol":symbol,"engine":"I1_SINGLE_ENGINE"}), 200


@live_bp.route("/api/symbol-feedkey", methods=["GET"])
def api_symbol_feedkey():
    try:
        symbol = (request.args.get("symbol") or "").upper().strip()
        if not symbol:
            return jsonify({"error": "symbol required"}), 400
        entry = SYMBOL_TO_KEY.get(symbol)
        if not entry:
            return jsonify({"symbol": symbol, "feed_key": None})
        if isinstance(entry, dict):
            feed_key = entry.get("NSE") or entry.get("BSE") or list(entry.values())[0]
            return jsonify({"symbol": symbol, "feed_key": feed_key})
        return jsonify({"symbol": symbol, "feed_key": entry if isinstance(entry, str) else None})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Subscribe  –  GET /api/ws-subscribe?symbol=RELIANCE&exchange=NSE
# ---------------------------------------------------------------------------
@live_bp.route("/api/ws-subscribe", methods=["GET"])
def api_ws_subscribe():
    try:
        symbol   = (request.args.get("symbol")   or "").strip().upper()
        exchange = (request.args.get("exchange") or "").strip().upper()

        if not symbol:
            return jsonify({"error": "symbol missing"}), 400

        # Frontend may send a full instrument key directly (e.g. "NSE_EQ|INE002A01018")
        if "|" in symbol:
            instrument_key = symbol
        else:
            mapped = SYMBOL_TO_KEY.get(symbol)
            if not mapped:
                return jsonify({"error": f"Symbol not found: {symbol}"}), 404

            if isinstance(mapped, str):
                instrument_key = mapped
            elif isinstance(mapped, dict):
                if exchange and exchange in mapped:
                    instrument_key = mapped[exchange]
                elif "NSE" in mapped:
                    instrument_key = mapped["NSE"]
                else:
                    instrument_key = list(mapped.values())[0]
            else:
                return jsonify({"error": "Invalid mapping format"}), 500

        redis_client.publish(
            "subscribe:requests",
            json.dumps({
                "instrument_key": instrument_key,
                "action":         "subscribe",
                "symbol":         symbol,
            }),
        )

        print(f"📡 SUBSCRIBE → {symbol} → {instrument_key}")
        return jsonify({
            "status":         "subscribed",
            "instrument_key": instrument_key,
            "symbol":         symbol,
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Unsubscribe  –  POST /api/unsubscribe   body: { "instrument_key": "..." }
# ---------------------------------------------------------------------------
@live_bp.route("/api/unsubscribe", methods=["POST"])
def api_unsubscribe():
    data = request.get_json(silent=True) or {}
    ik   = data.get("instrument_key")

    if not ik:
        return jsonify({"error": "instrument_key missing"}), 400

    redis_client.publish(
        "unsubscribe:requests",
        json.dumps({
            "instrument_key": ik,
            "method":         "unsub",
            "action":         "unsubscribe",
        }),
    )

    print(f"❌ Unsubscribe → {ik}")
    return jsonify({"status": "unsubscribed", "instrument_key": ik})
