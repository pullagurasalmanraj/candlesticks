# routes/indicators.py
# ================================================================
#  Indicators blueprint:
#    GET /api/indicators/daily
#    GET /api/indicators/intraday
# ================================================================
import traceback
from datetime import datetime, time as dtime

import numpy as np
import pandas as pd
import ta
from flask import Blueprint, request, jsonify
from psycopg2.extras import execute_values

from db import get_db_conn

indicators_bp = Blueprint("indicators", __name__)

MIN_CANDLES_INTRADAY = 200
MIN_CANDLES_DAILY    = 60


# ── Shared: Supertrend ───────────────────────────────────────────
def compute_supertrend(df, period=10, multiplier=3):
    high  = df["high"].astype(float)
    low   = df["low"].astype(float)
    close = df["close"].astype(float)

    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)

    atr        = tr.rolling(period).mean()
    hl2        = (high + low) / 2
    upper_band = hl2 + multiplier * atr
    lower_band = hl2 - multiplier * atr

    supertrend = [np.nan] * len(df)
    trend = 1

    for i in range(period, len(df)):
        if i == period:
            supertrend[i] = lower_band[i]
            continue
        if close[i] > upper_band[i - 1]:
            trend = 1
        elif close[i] < lower_band[i - 1]:
            trend = -1
        supertrend[i] = (
            max(lower_band[i], supertrend[i - 1]) if trend == 1
            else min(upper_band[i], supertrend[i - 1])
        )

    df["supertrend"]        = supertrend
    df["supertrend_signal"] = np.where(close > df["supertrend"], "BUY", "SELL")
    return df


# ── Shared: upsert SQL ───────────────────────────────────────────
_UPSERT_SQL = """
    INSERT INTO indicators (
        symbol,exchange,timeframe,ts,open,high,low,close,volume,
        ema_9,ema_21,ema_50,ema_200,supertrend,vwap,
        rsi_14,macd,macd_signal,macd_hist,atr_14,
        bollinger_mid,bollinger_upper,bollinger_lower,true_range,
        volume_sma_20,volume_sma_200,volume_ratio,obv,
        orb_high,orb_low,orb_breakout,orb_breakdown,
        signal,signal_strength,supertrend_signal,
        created_at,updated_at
    ) VALUES %s
    ON CONFLICT(symbol,exchange,timeframe,ts)
    DO UPDATE SET
        ema_9=EXCLUDED.ema_9, ema_21=EXCLUDED.ema_21,
        ema_50=EXCLUDED.ema_50, ema_200=EXCLUDED.ema_200,
        rsi_14=EXCLUDED.rsi_14, macd=EXCLUDED.macd,
        macd_signal=EXCLUDED.macd_signal, macd_hist=EXCLUDED.macd_hist,
        atr_14=EXCLUDED.atr_14,
        bollinger_mid=EXCLUDED.bollinger_mid,
        bollinger_upper=EXCLUDED.bollinger_upper,
        bollinger_lower=EXCLUDED.bollinger_lower,
        supertrend=EXCLUDED.supertrend,
        supertrend_signal=EXCLUDED.supertrend_signal,
        vwap=EXCLUDED.vwap, volume_ratio=EXCLUDED.volume_ratio,
        signal=EXCLUDED.signal, signal_strength=EXCLUDED.signal_strength,
        updated_at=NOW()
"""


# ── Daily indicators ─────────────────────────────────────────────
@indicators_bp.route("/api/indicators/daily", methods=["GET"])
def api_indicators_daily():
    try:
        symbol   = request.args.get("symbol",  "").upper().strip()
        exchange = request.args.get("exchange", "NSE").upper().strip()
        if not symbol:
            return jsonify({"error": "symbol is required"}), 400

        with get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT timestamp, open, high, low, close, volume "
                    "FROM daily_candles WHERE symbol=%s AND exchange=%s ORDER BY timestamp ASC",
                    (symbol, exchange),
                )
                rows_raw = cur.fetchall()

        if not rows_raw:
            return jsonify({"error": "No candle data found"}), 404

        # RealDictCursor returns dict rows — convert directly
        import decimal
        df = pd.DataFrame([dict(r) for r in rows_raw])
        df.rename(columns={"timestamp": "ts"}, inplace=True)
        for col in ["open","high","low","close","volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
        df = df.dropna(subset=["ts"]).sort_values("ts").reset_index(drop=True)
        df[["open","high","low","close","volume"]] = \
            df[["open","high","low","close","volume"]].apply(pd.to_numeric, errors="coerce")

        if len(df) < MIN_CANDLES_DAILY:
            return jsonify({
                "error": f"Not enough candles — need at least {MIN_CANDLES_DAILY}, got {len(df)}."
            }), 400

        close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]

        df["ema_9"]   = ta.trend.EMAIndicator(close,  9).ema_indicator()
        df["ema_21"]  = ta.trend.EMAIndicator(close, 21).ema_indicator()
        df["ema_50"]  = ta.trend.EMAIndicator(close, 50).ema_indicator()
        df["ema_200"] = ta.trend.EMAIndicator(close,200).ema_indicator()
        df["rsi_14"]  = ta.momentum.RSIIndicator(close, 14).rsi()

        macd = ta.trend.MACD(close)
        df["macd"], df["macd_signal"], df["macd_hist"] = \
            macd.macd(), macd.macd_signal(), macd.macd_diff()

        df["atr_14"] = ta.volatility.AverageTrueRange(high, low, close).average_true_range()

        bb = ta.volatility.BollingerBands(close)
        df["bollinger_mid"]   = bb.bollinger_mavg()
        df["bollinger_upper"] = bb.bollinger_hband()
        df["bollinger_lower"] = bb.bollinger_lband()

        df["true_range"] = pd.concat([
            (high - low).abs(),
            (high - close.shift()).abs(),
            (low  - close.shift()).abs(),
        ], axis=1).max(axis=1)

        df = compute_supertrend(df)

        df["vwap"]           = (close * volume).cumsum() / volume.cumsum()
        df["volume_sma_20"]  = volume.rolling(20).mean()
        df["volume_sma_200"] = volume.rolling(200).mean()
        df["volume_ratio"]   = (volume / df["volume_sma_20"]).replace([np.inf, -np.inf], None)
        df["obv"]            = ta.volume.OnBalanceVolumeIndicator(close, volume).on_balance_volume()

        df["signal"] = np.where(
            (close > df["supertrend"]) & (df["ema_21"] > df["ema_50"]) & (df["rsi_14"] > 55), "BUY",
            np.where(
                (close < df["supertrend"]) & (df["ema_21"] < df["ema_50"]) & (df["rsi_14"] < 45),
                "SELL", "NEUTRAL",
            ),
        )
        df["signal_strength"]   = df["rsi_14"].fillna(0).round(2)
        df["supertrend_signal"] = df["signal"].map({"BUY": 1, "SELL": -1}).fillna(0)

        df.ffill(inplace=True)
        df.bfill(inplace=True)
        df = df.replace({np.nan: None})

        now  = datetime.utcnow()
        rows = [
            (symbol, exchange, "1D", row.ts,
             row.open, row.high, row.low, row.close, row.volume,
             row.ema_9, row.ema_21, row.ema_50, row.ema_200,
             row.supertrend, row.vwap, row.rsi_14,
             row.macd, row.macd_signal, row.macd_hist, row.atr_14,
             row.bollinger_mid, row.bollinger_upper, row.bollinger_lower,
             row.true_range, row.volume_sma_20, row.volume_sma_200,
             row.volume_ratio, row.obv,
             None, None, None, None,
             row.signal, row.signal_strength, row.supertrend_signal,
             now, now)
            for row in df.itertuples()
        ]

        with get_db_conn() as conn:
            with conn.cursor() as cur:
                execute_values(cur, _UPSERT_SQL, rows)

        return jsonify({"status": "SUCCESS", "rows": len(rows)})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ── Intraday indicators ──────────────────────────────────────────
@indicators_bp.route("/api/indicators/intraday", methods=["GET"])
def api_indicators_intraday():
    try:
        symbol    = request.args.get("symbol",    "").upper().strip()
        timeframe = request.args.get("timeframe", "").lower().strip()
        exchange  = request.args.get("exchange",  "NSE").upper().strip()

        if not symbol or not timeframe:
            return jsonify({"error": "symbol & timeframe required"}), 400

        TF_MAP    = {"1":"1m","3":"3m","5":"5m","15":"15m","30":"30m","60":"60m"}
        timeframe = TF_MAP.get(timeframe, timeframe)

        with get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT timestamp, open, high, low, close, volume "
                    "FROM intraday_candles "
                    "WHERE symbol=%s AND timeframe=%s AND exchange=%s ORDER BY timestamp ASC",
                    (symbol, timeframe, exchange),
                )
                rows_raw = cur.fetchall()

        if not rows_raw:
            return jsonify({"error": "No data found"}), 404

        # RealDictCursor returns dict rows — convert directly
        df = pd.DataFrame([dict(r) for r in rows_raw])
        df.rename(columns={"timestamp": "ts"}, inplace=True)
        for col in ["open","high","low","close","volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.sort_values("ts").reset_index(drop=True)

        # Minimum candle guard BEFORE any processing
        if len(df) < MIN_CANDLES_INTRADAY:
            return jsonify({
                "error": f"Not enough candles — need at least {MIN_CANDLES_INTRADAY}, "
                         f"got {len(df)}. Fetch more history for {symbol} ({timeframe}) first."
            }), 400

        # Extract series — psycopg2 gives numeric types, astype is safe
        close  = df["close"].astype(float)
        high   = df["high"].astype(float)
        low    = df["low"].astype(float)
        volume = df["volume"].astype(float)

        # Compute all indicators BEFORE any timestamp conversion
        df["rsi_14"]  = ta.momentum.RSIIndicator(close, 14).rsi()
        df["ema_9"]   = ta.trend.EMAIndicator(close,  9).ema_indicator()
        df["ema_21"]  = ta.trend.EMAIndicator(close, 21).ema_indicator()
        df["ema_50"]  = ta.trend.EMAIndicator(close, 50).ema_indicator()
        df["ema_200"] = ta.trend.EMAIndicator(close,200).ema_indicator()

        macd = ta.trend.MACD(close)
        df["macd"], df["macd_signal"], df["macd_hist"] =             macd.macd(), macd.macd_signal(), macd.macd_diff()

        df["atr_14"] = ta.volatility.AverageTrueRange(
            high, low, close, window=14
        ).average_true_range()

        df["true_range"] = pd.concat([
            (high - low).abs(),
            (high - close.shift()).abs(),
            (low  - close.shift()).abs(),
        ], axis=1).max(axis=1)

        bb = ta.volatility.BollingerBands(close, 20, 2)
        df["bollinger_mid"]   = bb.bollinger_mavg()
        df["bollinger_upper"] = bb.bollinger_hband()
        df["bollinger_lower"] = bb.bollinger_lband()

        df = compute_supertrend(df)

        # VWAP needs date grouping — convert ts to IST NOW for date extraction
        # Use pandas native conversion — no format string, no coerce
        ts_col = pd.to_datetime(df["ts"], errors="coerce")
        if ts_col.dt.tz is None:
            ts_col = ts_col.dt.tz_localize("UTC")
        ts_ist = ts_col.dt.tz_convert("Asia/Kolkata")
        df["date"] = ts_ist.dt.date

        typical    = (high + low + close) / 3
        df["vwap"] = (
            (typical * volume).groupby(df["date"]).cumsum() /
            volume.groupby(df["date"]).cumsum().replace(0, np.nan)
        )

        df["volume_sma_20"]  = volume.rolling(20).mean()
        df["volume_sma_200"] = volume.rolling(200).mean()
        df["volume_ratio"]   = df["volume"] / df["volume_sma_20"].replace(0, np.nan)
        df["obv"]            = ta.volume.OnBalanceVolumeIndicator(close, volume).on_balance_volume()

        # Now assign IST ts back for ORB time comparisons
        df["ts"] = ts_ist

        orb_start, orb_end = dtime(9, 15), dtime(9, 20)
        df["orb_high"] = np.nan
        df["orb_low"]  = np.nan

        for current_date in df["ts"].dt.date.unique():
            day = df[df["ts"].dt.date == current_date]
            win = day[
                (day["ts"].dt.time >= orb_start) &
                (day["ts"].dt.time <= orb_end)
            ]
            if win.empty:
                continue
            df.loc[df["ts"].dt.date == current_date, "orb_high"] = win["high"].max()
            df.loc[df["ts"].dt.date == current_date, "orb_low"]  = win["low"].min()

        df["orb_high"]     = df.groupby(df["ts"].dt.date)["orb_high"].ffill()
        df["orb_low"]      = df.groupby(df["ts"].dt.date)["orb_low"].ffill()
        df["orb_breakout"] = df["close"] > df["orb_high"]
        df["orb_breakdown"]= df["close"] < df["orb_low"]

        df["supertrend_signal"] = np.where(df["close"] > df["supertrend"], "UP", "DOWN")
        df["signal"]            = np.where(
            df["orb_breakout"], "BUY",
            np.where(df["orb_breakdown"], "SELL", "HOLD")
        )
        df["signal_strength"] = np.round(df["rsi_14"].fillna(50) / 2, 2)

        df = df.replace({np.nan: None})

        now  = datetime.now()
        rows = [
            (symbol, exchange, timeframe, row.ts,
             row.open, row.high, row.low, row.close, row.volume,
             row.ema_9, row.ema_21, row.ema_50, row.ema_200,
             row.supertrend, row.vwap, row.rsi_14,
             row.macd, row.macd_signal, row.macd_hist, row.atr_14,
             row.bollinger_mid, row.bollinger_upper, row.bollinger_lower,
             row.true_range, row.volume_sma_20, row.volume_sma_200,
             row.volume_ratio, row.obv,
             row.orb_high, row.orb_low, row.orb_breakout, row.orb_breakdown,
             row.signal, row.signal_strength, row.supertrend_signal,
             now, now)
            for row in df.itertuples()
        ]

        with get_db_conn() as conn:
            with conn.cursor() as cur:
                execute_values(cur, _UPSERT_SQL, rows)

        return jsonify({"status": "SUCCESS", "rows": len(rows)})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
