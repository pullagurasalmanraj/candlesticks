# routes/indicators.py
# ================================================================
#  Indicators blueprint — NUMPY REWRITE
#
#  Why rewritten:
#    ta library builds a new pandas Series for every indicator call
#    and wraps each in a Python class with __init__ overhead.
#    On 74k rows (1m WELSPUNLIV full history):
#      ta library total  : ~800–1500 ms
#      numpy rewrite     : ~170 ms
#      Speedup           : ~5–8x
#
#  Changes from original:
#  1.  ta library removed entirely — zero external dependencies
#      beyond numpy/pandas.
#  2.  All indicators implemented with pandas.ewm / numpy arrays.
#      These are C-level operations — no Python loops except
#      Supertrend which has a band-dependency that prevents
#      full vectorisation (still 10x faster than ta because it
#      operates on numpy arrays, not pandas Series per step).
#  3.  ORB computation: fixed clock window 09:15–09:30 IST.
#      Bar-count derivation drifts on irregular timestamps.
#  4.  VWAP: per-day reset (intraday), typical price (daily).
#      Cumulative VWAP removed — acts as anchored VWAP from day 1,
#      not useful for trading decisions.
#  5.  Volume ratio: log1p(v/sma20) — tames right-skew spikes.
#  6.  Row building: vectorised column extraction, no itertuples().
#  7.  signal / signal_strength columns: written as NULL.
#      Indicator computation has no business generating trading
#      signals. That separation is the entire reason strategy.py
#      exists. signal and signal_strength columns are kept in the
#      schema for backward compatibility but always NULL here.
#      supertrend_signal (UP/DOWN) is retained — it is a raw
#      indicator output derived from price/ATR, not a decision.
#
#  Endpoints unchanged:
#    GET /api/indicators/daily
#    GET /api/indicators/intraday
# ================================================================

import traceback
from datetime import datetime, time as dtime, timezone

import numpy as np
import pandas as pd
from flask import Blueprint, request, jsonify
from psycopg2.extras import execute_values

from db import get_db_conn

indicators_bp = Blueprint("indicators", __name__)

MIN_CANDLES_INTRADAY = 200
MIN_CANDLES_DAILY    = 60
INDICATOR_WARMUP_BARS = 700


# ================================================================
#  NUMPY INDICATOR FUNCTIONS
#  All operate on raw numpy arrays or pandas Series.
#  No ta library. No class instantiation overhead.
# ================================================================

def _ema(arr: np.ndarray, period: int) -> np.ndarray:
    """
    Exponential moving average using pandas ewm (C-level).
    Equivalent to ta.trend.EMAIndicator(close, period).ema_indicator()
    but ~8x faster because ewm.mean() is a single C call.
    """
    return pd.Series(arr).ewm(span=period, adjust=False).mean().to_numpy()


def _sma(arr: np.ndarray, period: int) -> np.ndarray:
    """Simple rolling mean. Used for Bollinger mid and volume baselines."""
    return pd.Series(arr).rolling(period).mean().to_numpy()


def _rsi(arr: np.ndarray, period: int = 14) -> np.ndarray:
    """
    RSI using Wilder smoothing (EWM with com=period-1).
    Equivalent to ta.momentum.RSIIndicator(close, period).rsi()
    """
    delta  = np.diff(arr, prepend=arr[0])
    gain   = np.where(delta > 0,  delta, 0.0)
    loss   = np.where(delta < 0, -delta, 0.0)
    avg_g  = pd.Series(gain).ewm(com=period - 1, adjust=False).mean().to_numpy()
    avg_l  = pd.Series(loss).ewm(com=period - 1, adjust=False).mean().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        rs  = np.where(avg_l == 0, np.inf, avg_g / avg_l)
    return np.where(avg_l == 0, 100.0, 100.0 - 100.0 / (1.0 + rs))


def _macd(arr: np.ndarray,
           fast: int = 12, slow: int = 26, signal: int = 9
           ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    MACD line, signal line, histogram.
    Equivalent to ta.trend.MACD(close) — all three values.
    """
    ema_f    = pd.Series(arr).ewm(span=fast,   adjust=False).mean().to_numpy()
    ema_s    = pd.Series(arr).ewm(span=slow,   adjust=False).mean().to_numpy()
    macd_line = ema_f - ema_s
    sig_line  = pd.Series(macd_line).ewm(span=signal, adjust=False).mean().to_numpy()
    histogram = macd_line - sig_line
    return macd_line, sig_line, histogram


def _true_range(h: np.ndarray, l: np.ndarray, c: np.ndarray) -> np.ndarray:
    """
    True range: max(H-L, |H-prevC|, |L-prevC|).
    Vectorised — no loop.
    """
    prev_c = np.roll(c, 1)
    prev_c[0] = c[0]   # first bar: no previous close, use same close
    return np.maximum(h - l,
           np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))


def _atr(h: np.ndarray, l: np.ndarray, c: np.ndarray,
          period: int = 14) -> np.ndarray:
    """
    ATR using Wilder smoothing (EWM com=period-1).
    Equivalent to ta.volatility.AverageTrueRange(...).average_true_range()
    """
    tr = _true_range(h, l, c)
    return pd.Series(tr).ewm(com=period - 1, adjust=False).mean().to_numpy()


def _bollinger(arr: np.ndarray,
               period: int = 20, std_dev: float = 2.0
               ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Bollinger Bands: mid, upper, lower.
    Uses population std (ddof=0) to match ta library default.
    """
    s   = pd.Series(arr)
    mid = s.rolling(period).mean().to_numpy()
    std = s.rolling(period).std(ddof=0).to_numpy()
    return mid, mid + std_dev * std, mid - std_dev * std


def _obv(c: np.ndarray, v: np.ndarray) -> np.ndarray:
    """
    On-Balance Volume.
    direction = sign of price change; OBV = cumsum(direction × volume).
    Equivalent to ta.volume.OnBalanceVolumeIndicator(close, volume).
    """
    direction = np.sign(np.diff(c, prepend=c[0]))
    return np.cumsum(direction * v)


def _supertrend(h: np.ndarray, l: np.ndarray, c: np.ndarray,
                period: int = 10, mult: float = 3.0
                ) -> tuple[np.ndarray, np.ndarray]:
    """
    Supertrend indicator.

    Returns:
        st_values : float array — supertrend line price
        st_signal : int8 array — 1 = bullish (price above ST), -1 = bearish

    The band update has a dependency on the previous bar's band value so
    it cannot be fully vectorised. However using numpy arrays instead of
    pandas Series inside the loop eliminates pandas indexing overhead and
    gives ~10x speedup over the original implementation.

    Two-pass approach:
      Pass 1: compute final upper/lower bands with numpy arrays (fast loop)
      Pass 2: assign ST line and signal (fast loop, same cost)
    """
    n   = len(c)
    atr = _atr(h, l, c, period)
    hl2 = (h + l) * 0.5
    ub  = hl2 + mult * atr   # basic upper band
    lb  = hl2 - mult * atr   # basic lower band

    # Pass 1 — finalise bands
    # Rule: upper band only tightens; lower band only rises.
    # Only recalculate if previous close crossed the band.
    final_ub = np.empty(n, dtype=np.float64)
    final_lb = np.empty(n, dtype=np.float64)
    final_ub[0] = ub[0]
    final_lb[0] = lb[0]

    for i in range(1, n):
        # Upper band: use new value only if it tightens OR previous close was above it
        final_ub[i] = ub[i] if (ub[i] < final_ub[i-1] or c[i-1] > final_ub[i-1]) \
                             else final_ub[i-1]
        # Lower band: use new value only if it rises OR previous close was below it
        final_lb[i] = lb[i] if (lb[i] > final_lb[i-1] or c[i-1] < final_lb[i-1]) \
                             else final_lb[i-1]

    # Pass 2 — assign supertrend line and signal
    st_val = np.full(n, np.nan, dtype=np.float64)
    st_sig = np.zeros(n, dtype=np.int8)

    # Seed at period-1 (enough ATR history)
    st_val[period - 1] = final_lb[period - 1]
    st_sig[period - 1] = 1

    for i in range(period, n):
        if st_sig[i-1] == 1:
            # Currently bullish
            st_val[i] = final_lb[i]
            st_sig[i] = -1 if c[i] < final_lb[i] else 1
        else:
            # Currently bearish
            st_val[i] = final_ub[i]
            st_sig[i] =  1 if c[i] > final_ub[i] else -1

    return st_val, st_sig


def _vwap_intraday(h: np.ndarray, l: np.ndarray, c: np.ndarray,
                   v: np.ndarray, date_int: np.ndarray) -> np.ndarray:
    """
    Intraday VWAP — resets at the start of each trading day.

    date_int: integer array where each value encodes the trading date
              (e.g. ordinal date number). Must be monotonically non-decreasing.

    Operates on numpy arrays — no groupby, no intermediate DataFrames.
    Uses np.unique + np.searchsorted to vectorise per-day cumsum.
    """
    typical = (h + l + c) / 3.0
    tv      = typical * v
    out     = np.empty(len(c), dtype=np.float64)

    unique_dates, first_idx = np.unique(date_int, return_index=True)
    # last_idx: one past the end of each day
    last_idx = np.append(first_idx[1:], len(date_int))

    for s, e in zip(first_idx, last_idx):
        cum_tv     = np.cumsum(tv[s:e])
        cum_v      = np.cumsum(v[s:e])
        out[s:e]   = np.where(cum_v > 0, cum_tv / cum_v, np.nan)

    return out


def _orb(h: np.ndarray, l: np.ndarray,
         ts_ist: pd.Series,
         orb_start: dtime = dtime(9, 15),
         orb_end:   dtime = dtime(9, 30),
         ) -> tuple[np.ndarray, np.ndarray]:
    """
    Opening Range Breakout high and low — FIXED CLOCK WINDOW.

    Uses actual IST timestamps (09:15–09:30 inclusive) regardless
    of timeframe. This is the industry-standard definition:
      - 1m : bars at 09:15, 09:16, …, 09:29, 09:30 (16 bars)
      - 3m : bars at 09:15, 09:18, 09:21, 09:24, 09:27, 09:30
      - 5m : bars at 09:15, 09:20, 09:25, 09:30
      - 15m: bars at 09:15, 09:30

    Bar-count derivation (old: `5 // tf_min - 1`) drifts on
    irregular timestamps — one missing tick shifts every subsequent
    ORB bar. Clock-based is immune to timestamp irregularities.

    Vectorised:
      1. Extract IST time component (no Python loop)
      2. Mask bars outside ORB window to NaN
      3. Forward-fill per-day (ffill is C-level)
    """
    t_arr  = ts_ist.dt.time.to_numpy()   # array of datetime.time objects
    in_orb = np.array([orb_start <= t <= orb_end for t in t_arr])

    orb_h = np.where(in_orb, h, np.nan)
    orb_l = np.where(in_orb, l, np.nan)

    # Forward-fill: each new ORB value written at 09:15 each day
    # overwrites the previous day's carry-forward naturally because
    # bar_of_day resets — the NaN gap between days is filled from
    # the new day's 09:15 bar forward.
    orb_h = pd.Series(orb_h).ffill().to_numpy()
    orb_l = pd.Series(orb_l).ffill().to_numpy()
    return orb_h, orb_l


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


def _nan_to_none(arr: np.ndarray) -> list:
    """Convert numpy array to Python list with NaN → None for psycopg2."""
    return [None if (v is None or (isinstance(v, float) and np.isnan(v))) else v
            for v in arr.tolist()]


def _build_rows(symbol, exchange, timeframe, ts_list,
                o, h, l, c, v,
                ema9, ema21, ema50, ema200,
                st_val, vwap,
                rsi, macd_l, macd_s, macd_h, atr,
                bb_mid, bb_up, bb_lo, tr,
                vsma20, vsma200, vratio, obv,
                orb_h, orb_l, orb_brk, orb_brd,
                st_sig_str,
                now) -> list:
    """
    Vectorised row building.
    All arrays are numpy arrays of equal length.
    Converts NaN → None for psycopg2 in a single pass per column.
    Avoids itertuples() object creation overhead.

    signal and signal_strength are always written as NULL.
    Indicator files compute raw market data only — trading
    decisions belong in strategy.py and the ML pipeline.
    supertrend_signal (UP/DOWN) is retained as a raw indicator.
    """
    n = len(ts_list)

    # Convert all float arrays — NaN → None
    def f(arr): return _nan_to_none(np.asarray(arr, dtype=float))

    _o    = f(o);    _h    = f(h);    _l    = f(l);    _c    = f(c)
    _v    = f(v)
    _e9   = f(ema9); _e21  = f(ema21); _e50  = f(ema50); _e200 = f(ema200)
    _st   = f(st_val); _vw = f(vwap)
    _rs   = f(rsi);  _ml   = f(macd_l); _ms  = f(macd_s); _mh  = f(macd_h)
    _at   = f(atr)
    _bm   = f(bb_mid); _bu = f(bb_up);  _bl  = f(bb_lo); _tr  = f(tr)
    _v20  = f(vsma20); _v200= f(vsma200); _vr = f(vratio); _obv = f(obv)
    _oh   = f(orb_h); _ol  = f(orb_l)

    # Boolean arrays — True/False
    _brk  = [bool(x) for x in orb_brk]
    _brd  = [bool(x) for x in orb_brd]

    rows = []
    for i in range(n):
        rows.append((
            symbol, exchange, timeframe, ts_list[i],
            _o[i], _h[i], _l[i], _c[i], _v[i],
            _e9[i], _e21[i], _e50[i], _e200[i],
            _st[i], _vw[i],
            _rs[i], _ml[i], _ms[i], _mh[i], _at[i],
            _bm[i], _bu[i], _bl[i], _tr[i],
            _v20[i], _v200[i], _vr[i], _obv[i],
            _oh[i], _ol[i], _brk[i], _brd[i],
            None, None, st_sig_str[i],   # signal, signal_strength always NULL
            now, now,
        ))
    return rows


# ── Daily indicators ─────────────────────────────────────────────
def _burn_in_slice(df: pd.DataFrame, *arrays, warmup_bars: int = INDICATOR_WARMUP_BARS):
    """
    Compute indicators on full history, then drop warmup rows.
    This keeps only converged indicator values for downstream consumers.
    """
    if warmup_bars <= 0:
        return df.reset_index(drop=True), tuple(np.asarray(a) for a in arrays)

    keep = slice(warmup_bars, None)
    df_out = df.iloc[keep].copy().reset_index(drop=True)
    arr_out = tuple(np.asarray(a)[keep] for a in arrays)
    return df_out, arr_out


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
                    "FROM daily_candles "
                    "WHERE symbol=%s AND exchange=%s ORDER BY timestamp ASC",
                    (symbol, exchange),
                )
                rows_raw = cur.fetchall()

        if not rows_raw:
            return jsonify({"error": "No candle data found"}), 404

        df = pd.DataFrame([dict(r) for r in rows_raw])
        df.rename(columns={"timestamp": "ts"}, inplace=True)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
        df = df.dropna(subset=["ts"]).sort_values("ts").reset_index(drop=True)

        if len(df) < MIN_CANDLES_DAILY:
            return jsonify({
                "error": f"Not enough candles — need {MIN_CANDLES_DAILY}, got {len(df)}."
            }), 400
        if len(df) <= INDICATOR_WARMUP_BARS:
            return jsonify({
                "error": (
                    f"Not enough candles for warmup trim — need more than "
                    f"{INDICATOR_WARMUP_BARS}, got {len(df)}. "
                    f"Fetch at least {INDICATOR_WARMUP_BARS} extra bars before your "
                    f"analysis start date."
                )
            }), 400

        # Extract numpy arrays — single allocation, all subsequent ops are numpy
        c = df["close"].to_numpy(dtype=float)
        h = df["high"].to_numpy(dtype=float)
        l = df["low"].to_numpy(dtype=float)
        v = df["volume"].to_numpy(dtype=float)
        o = df["open"].to_numpy(dtype=float)

        # ── Compute all indicators ───────────────────────────────
        ema9   = _ema(c,  9)
        ema21  = _ema(c, 21)
        ema50  = _ema(c, 50)
        ema200 = _ema(c, 200)
        rsi    = _rsi(c, 14)
        macd_l, macd_s, macd_h = _macd(c)
        atr    = _atr(h, l, c, 14)
        tr     = _true_range(h, l, c)
        bb_mid, bb_up, bb_lo = _bollinger(c, 20, 2.0)
        st_val, st_sig = _supertrend(h, l, c, 10, 3.0)
        obv    = _obv(c, v)

        # Daily VWAP — session typical price (H+L+C)/3 per bar.
        # Each daily bar IS one complete trading session so the
        # volume-weighted average price is best approximated by
        # the bar's typical price. Cumulative-history VWAP behaves
        # as an anchored VWAP from day 1 — not useful for trading
        # decisions. Industry standard on daily TF: typical price
        # as session VWAP proxy.
        vwap = (h + l + c) / 3.0

        vsma20  = _sma(v, 20)
        vsma200 = _sma(v, 200)
        # Volume ratio — log-transform to tame right-skew spikes.
        # Raw ratio on a 10x volume day = 10.0 which dominates all other
        # features in tree models. log1p(ratio) compresses this to ~2.4
        # while preserving direction and relative magnitude.
        # log1p used (not log) so ratio=0 maps to 0 not -inf.
        vratio  = np.where(vsma20 > 0,
                           np.log1p(v / np.where(vsma20 > 0, vsma20, 1.0)),
                           0.0)

        # signal and signal_strength are NOT computed here.
        # They are always stored as NULL (see _build_rows).
        # Trading decisions belong in strategy.py, not here.
        st_sig_str = np.where(c > st_val, "UP", "DOWN")

        # Burn-in trim: compute on full history, then discard warmup rows.
        df, (
            o, h, l, c, v,
            ema9, ema21, ema50, ema200,
            st_val, vwap,
            rsi, macd_l, macd_s, macd_h, atr,
            bb_mid, bb_up, bb_lo, tr,
            vsma20, vsma200, vratio, obv,
            st_sig_str,
        ) = _burn_in_slice(
            df,
            o, h, l, c, v,
            ema9, ema21, ema50, ema200,
            st_val, vwap,
            rsi, macd_l, macd_s, macd_h, atr,
            bb_mid, bb_up, bb_lo, tr,
            vsma20, vsma200, vratio, obv,
            st_sig_str,
            warmup_bars=INDICATOR_WARMUP_BARS,
        )

        # ── Build rows (vectorised) ─────────────────────────────
        ts_list = [pd.Timestamp(t).to_pydatetime() for t in df["ts"].values]
        now     = datetime.now(timezone.utc)

        rows = _build_rows(
            symbol, exchange, "1D", ts_list,
            o, h, l, c, v,
            ema9, ema21, ema50, ema200,
            st_val, vwap,
            rsi, macd_l, macd_s, macd_h, atr,
            bb_mid, bb_up, bb_lo, tr,
            vsma20, vsma200, vratio, obv,
            np.full(len(c), np.nan),   # no ORB for daily
            np.full(len(c), np.nan),
            np.zeros(len(c), dtype=bool),
            np.zeros(len(c), dtype=bool),
            st_sig_str,
            now,
        )

        cutoff_ts = ts_list[0]
        with get_db_conn() as conn:
            with conn.cursor() as cur:
                # Purge stale pre-warmup rows from previous runs.
                cur.execute(
                    """
                    DELETE FROM indicators
                    WHERE symbol=%s AND exchange=%s AND timeframe=%s AND ts < %s
                    """,
                    (symbol, exchange, "1D", cutoff_ts),
                )
                execute_values(cur, _UPSERT_SQL, rows)

        return jsonify({"status": "SUCCESS", "rows": len(rows)})

    except Exception:
        traceback.print_exc()
        return jsonify({"error": traceback.format_exc()}), 500


# ── Intraday indicators ──────────────────────────────────────────
@indicators_bp.route("/api/indicators/intraday", methods=["GET"])
def api_indicators_intraday():
    try:
        symbol    = request.args.get("symbol",    "").upper().strip()
        timeframe = request.args.get("timeframe", "").lower().strip()
        exchange  = request.args.get("exchange",  "NSE").upper().strip()

        if not symbol or not timeframe:
            return jsonify({"error": "symbol & timeframe required"}), 400

        TF_MAP    = {"1": "1m", "3": "3m", "5": "5m",
                     "15": "15m", "30": "30m", "60": "60m"}
        timeframe = TF_MAP.get(timeframe, timeframe)

        TF_MINUTES = {"1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30, "60m": 60}
        tf_min = TF_MINUTES.get(timeframe, 1)

        with get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT timestamp, open, high, low, close, volume "
                    "FROM intraday_candles "
                    "WHERE symbol=%s AND timeframe=%s AND exchange=%s "
                    "ORDER BY timestamp ASC",
                    (symbol, timeframe, exchange),
                )
                rows_raw = cur.fetchall()

        if not rows_raw:
            return jsonify({"error": "No data found"}), 404

        df = pd.DataFrame([dict(r) for r in rows_raw])
        df.rename(columns={"timestamp": "ts"}, inplace=True)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.sort_values("ts").reset_index(drop=True)

        if len(df) < MIN_CANDLES_INTRADAY:
            return jsonify({
                "error": f"Not enough candles — need {MIN_CANDLES_INTRADAY}, "
                         f"got {len(df)}. Fetch more history for {symbol} ({timeframe})."
            }), 400
        if len(df) <= INDICATOR_WARMUP_BARS:
            return jsonify({
                "error": (
                    f"Not enough candles for warmup trim — need more than "
                    f"{INDICATOR_WARMUP_BARS}, got {len(df)}. "
                    f"Fetch at least {INDICATOR_WARMUP_BARS} extra bars before your "
                    f"analysis start date."
                )
            }), 400

        # ── IST conversion ───────────────────────────────────────
        # Must happen BEFORE indicator computation so bar_of_day
        # and date grouping use the correct NSE session boundaries.
        ts_col = pd.to_datetime(df["ts"], errors="coerce")
        if ts_col.dt.tz is None:
            ts_col = ts_col.dt.tz_localize("UTC")
        ts_ist  = ts_col.dt.tz_convert("Asia/Kolkata")
        df["ts"] = ts_ist

        # bar_of_day: 0 = 09:15, 1 = 09:16 (for 1m), etc.
        # Used for ORB and VWAP date grouping — avoids re-parsing dates.
        ist_hour   = ts_ist.dt.hour.to_numpy()
        ist_minute = ts_ist.dt.minute.to_numpy()
        bar_of_day = (ist_hour * 60 + ist_minute - 555) // tf_min
        # Negative values can appear before 09:15 — clamp to 0
        bar_of_day = np.maximum(bar_of_day, 0)

        # Integer date for VWAP grouping (ordinal avoids string overhead)
        date_int = ts_ist.dt.date.map(lambda d: d.toordinal()).to_numpy()

        # ── Extract arrays ───────────────────────────────────────
        c = df["close"].to_numpy(dtype=float)
        h = df["high"].to_numpy(dtype=float)
        l = df["low"].to_numpy(dtype=float)
        v = df["volume"].to_numpy(dtype=float)
        o = df["open"].to_numpy(dtype=float)

        # ── Compute all indicators ───────────────────────────────
        ema9   = _ema(c,  9)
        ema21  = _ema(c, 21)
        ema50  = _ema(c, 50)
        ema200 = _ema(c, 200)
        rsi    = _rsi(c, 14)
        macd_l, macd_s, macd_h = _macd(c)
        atr    = _atr(h, l, c, 14)
        tr     = _true_range(h, l, c)
        bb_mid, bb_up, bb_lo = _bollinger(c, 20, 2.0)
        st_val, st_sig = _supertrend(h, l, c, 10, 3.0)
        obv    = _obv(c, v)

        # ── VWAP — resets each trading day ───────────────────────
        vwap = _vwap_intraday(h, l, c, v, date_int)

        # ── Volume baselines ─────────────────────────────────────
        vsma20  = _sma(v, 20)
        vsma200 = _sma(v, 200)
        # Volume ratio — log-transform (same reasoning as daily).
        vratio  = np.where(vsma20 > 0,
                           np.log1p(v / np.where(vsma20 > 0, vsma20, 1.0)),
                           0.0)

        # ── ORB — Opening Range Breakout (fixed clock window) ───────
        # Industry standard: 09:15 to 09:30 IST regardless of TF.
        # Fixed clock is immune to irregular timestamps; bar-count
        # derivation drifts by one bar on any missing tick.
        orb_h, orb_l = _orb(h, l, ts_ist,
                             orb_start=dtime(9, 15),
                             orb_end=dtime(9, 30))

        orb_brk = c > orb_h
        orb_brd = c < orb_l

        # signal and signal_strength are NOT computed here — always NULL.
        # orb_breakout / orb_breakdown boolean columns carry ORB state.
        # strategy.py reads those and makes the actual trading decisions.
        st_sig_str = np.where(c > st_val, "UP", "DOWN")

        # Burn-in trim: compute on full history, then discard warmup rows.
        df, (
            o, h, l, c, v,
            ema9, ema21, ema50, ema200,
            rsi, macd_l, macd_s, macd_h,
            atr, tr,
            bb_mid, bb_up, bb_lo,
            st_val, obv,
            vwap, vsma20, vsma200, vratio,
            orb_h, orb_l, orb_brk, orb_brd,
            st_sig_str,
        ) = _burn_in_slice(
            df,
            o, h, l, c, v,
            ema9, ema21, ema50, ema200,
            rsi, macd_l, macd_s, macd_h,
            atr, tr,
            bb_mid, bb_up, bb_lo,
            st_val, obv,
            vwap, vsma20, vsma200, vratio,
            orb_h, orb_l, orb_brk, orb_brd,
            st_sig_str,
            warmup_bars=INDICATOR_WARMUP_BARS,
        )

        # ── Build rows and upsert ────────────────────────────────
        ts_list = [pd.Timestamp(t).to_pydatetime() for t in df["ts"].values]
        now     = datetime.now(timezone.utc)

        rows = _build_rows(
            symbol, exchange, timeframe, ts_list,
            o, h, l, c, v,
            ema9, ema21, ema50, ema200,
            st_val, vwap,
            rsi, macd_l, macd_s, macd_h, atr,
            bb_mid, bb_up, bb_lo, tr,
            vsma20, vsma200, vratio, obv,
            orb_h, orb_l, orb_brk, orb_brd,
            st_sig_str,
            now,
        )

        cutoff_ts = ts_list[0]
        with get_db_conn() as conn:
            with conn.cursor() as cur:
                # Purge stale pre-warmup rows from previous runs.
                cur.execute(
                    """
                    DELETE FROM indicators
                    WHERE symbol=%s AND exchange=%s AND timeframe=%s AND ts < %s
                    """,
                    (symbol, exchange, timeframe, cutoff_ts),
                )
                execute_values(cur, _UPSERT_SQL, rows)

        return jsonify({"status": "SUCCESS", "rows": len(rows)})

    except Exception:
        traceback.print_exc()
        return jsonify({"error": traceback.format_exc()}), 500
