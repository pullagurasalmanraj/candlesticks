# routes/indicators.py
# ================================================================
#  Indicators blueprint â€” NUMPY REWRITE
#
#  Why rewritten:
#    ta library builds a new pandas Series for every indicator call
#    and wraps each in a Python class with __init__ overhead.
#    On 74k rows (1m WELSPUNLIV full history):
#      ta library total  : ~800â€“1500 ms
#      numpy rewrite     : ~170 ms
#      Speedup           : ~5â€“8x
#
#  Changes from original:
#  1.  ta library removed entirely â€” zero external dependencies
#      beyond numpy/pandas.
#  2.  All indicators implemented with pandas.ewm / numpy arrays.
#      These are C-level operations â€” no Python loops except
#      Supertrend which has a band-dependency that prevents
#      full vectorisation (still 10x faster than ta because it
#      operates on numpy arrays, not pandas Series per step).
#  3.  ORB computation: fixed clock window 09:15â€“09:30 IST.
#      Bar-count derivation drifts on irregular timestamps.
#  4.  VWAP: per-day reset (intraday), typical price (daily).
#      Cumulative VWAP removed â€” acts as anchored VWAP from day 1,
#      not useful for trading decisions.
#  5.  Volume ratio: log1p(v/sma20) â€” tames right-skew spikes.
#  6.  Row building: vectorised column extraction, no itertuples().
#  7.  signal / signal_strength columns: written as NULL.
#      Indicator computation has no business generating trading
#      signals. That separation is the entire reason strategy.py
#      exists. signal and signal_strength columns are kept in the
#      schema for backward compatibility but always NULL here.
#      supertrend_signal (UP/DOWN) is retained â€” it is a raw
#      indicator output derived from price/ATR, not a decision.
#
#  Endpoints unchanged:
#    GET /api/indicators/daily
#    GET /api/indicators/intraday
# ================================================================

import traceback
from datetime import datetime, date, time as dtime, timezone
from dateutil.relativedelta import relativedelta

import numpy as np
import pandas as pd
from flask import Blueprint, request, jsonify
from psycopg2.extras import execute_values, execute_batch

from config import UPSTOX_V3_BASE, safe_requests
from db import get_db_conn
from services.token_service import get_valid_token
from utils.symbol_map import SYMBOL_TO_KEY

indicators_bp = Blueprint("indicators", __name__)

MIN_CANDLES_INTRADAY = 200
MIN_CANDLES_DAILY    = 60
INDICATOR_WARMUP_BARS = 700
INTRADAY_ALIGN_YEARS_DEFAULT = 2
INTRADAY_STABILIZE_WITH_TF_DEFAULT = "15m"
INTRADAY_TF_MAP = {"1": "1m", "3": "3m", "5": "5m", "15": "15m", "30": "30m", "60": "60m"}
INTRADAY_TF_MINUTES = {"1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30, "60m": 60}
INTRADAY_TRADING_MINUTES_PER_SESSION = 375
INTRADAY_PAD_BUFFER_CALENDAR_DAYS = 14


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
    Equivalent to ta.trend.MACD(close) â€” all three values.
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
    Vectorised â€” no loop.
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
    direction = sign of price change; OBV = cumsum(direction Ã— volume).
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
        st_values : float array â€” supertrend line price
        st_signal : int8 array â€” 1 = bullish (price above ST), -1 = bearish

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

    # Pass 1 â€” finalise bands
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

    # Pass 2 â€” assign supertrend line and signal
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
    Intraday VWAP â€” resets at the start of each trading day.

    date_int: integer array where each value encodes the trading date
              (e.g. ordinal date number). Must be monotonically non-decreasing.

    Operates on numpy arrays â€” no groupby, no intermediate DataFrames.
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
    Opening Range Breakout high and low â€” FIXED CLOCK WINDOW.

    Uses actual IST timestamps (09:15â€“09:30 inclusive) regardless
    of timeframe. This is the industry-standard definition:
      - 1m : bars at 09:15, 09:16, â€¦, 09:29, 09:30 (16 bars)
      - 3m : bars at 09:15, 09:18, 09:21, 09:24, 09:27, 09:30
      - 5m : bars at 09:15, 09:20, 09:25, 09:30
      - 15m: bars at 09:15, 09:30

    Bar-count derivation (old: `5 // tf_min - 1`) drifts on
    irregular timestamps â€” one missing tick shifts every subsequent
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
    # bar_of_day resets â€” the NaN gap between days is filled from
    # the new day's 09:15 bar forward.
    orb_h = pd.Series(orb_h).ffill().to_numpy()
    orb_l = pd.Series(orb_l).ffill().to_numpy()
    return orb_h, orb_l


# â”€â”€ Shared: upsert SQL â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
    """Convert numpy array to Python list with NaN â†’ None for psycopg2."""
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
    Converts NaN â†’ None for psycopg2 in a single pass per column.
    Avoids itertuples() object creation overhead.

    signal and signal_strength are always written as NULL.
    Indicator files compute raw market data only â€” trading
    decisions belong in strategy.py and the ML pipeline.
    supertrend_signal (UP/DOWN) is retained as a raw indicator.
    """
    n = len(ts_list)

    # Convert all float arrays â€” NaN â†’ None
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

    # Boolean arrays â€” True/False
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


# â”€â”€ Daily indicators â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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


def _intraday_aligned_cutoff_ist(years: int = INTRADAY_ALIGN_YEARS_DEFAULT) -> pd.Timestamp:
    """
    Shared intraday cutoff across all timeframes:
    (yesterday 09:15 IST) - `years`.
    """
    years = max(int(years), 1)
    now_ist = pd.Timestamp.now(tz="Asia/Kolkata")
    yesterday_midnight_ist = (now_ist - pd.Timedelta(days=1)).normalize()
    yesterday_open_ist = yesterday_midnight_ist + pd.Timedelta(hours=9, minutes=15)
    return yesterday_open_ist - pd.DateOffset(years=years)


def _slice_from_ist_open(df: pd.DataFrame, *arrays, cutoff_ist: pd.Timestamp):
    """
    Slice dataframe and arrays from first 09:15 IST bar on/after cutoff.
    If 09:15 bar is missing, falls back to first bar on/after cutoff.
    """
    if df.empty:
        return df.copy(), tuple(np.asarray(a) for a in arrays)

    ts = pd.to_datetime(df["ts"], errors="coerce")
    ge_cutoff = ts >= cutoff_ist
    is_open_915 = (ts.dt.hour == 9) & (ts.dt.minute == 15)

    open_candidates = np.flatnonzero((ge_cutoff & is_open_915).to_numpy())
    if len(open_candidates) > 0:
        start_idx = int(open_candidates[0])
    else:
        fallback_candidates = np.flatnonzero(ge_cutoff.to_numpy())
        if len(fallback_candidates) == 0:
            empty_df = df.iloc[0:0].copy().reset_index(drop=True)
            empty_arrays = tuple(np.asarray(a)[0:0] for a in arrays)
            return empty_df, empty_arrays
        start_idx = int(fallback_candidates[0])

    keep = slice(start_idx, None)
    df_out = df.iloc[keep].copy().reset_index(drop=True)
    arr_out = tuple(np.asarray(a)[keep] for a in arrays)
    return df_out, arr_out


def _slice_from_ist_date(df: pd.DataFrame, *arrays, cutoff_date: date):
    """
    Slice dataframe and arrays from first bar whose IST trading date is
    on/after cutoff_date. Used for daily alignment where 09:15 time
    boundaries are not applicable.
    """
    if df.empty:
        return df.copy(), tuple(np.asarray(a) for a in arrays)

    ts = pd.to_datetime(df["ts"], errors="coerce")
    keep_candidates = np.flatnonzero((ts.dt.date >= cutoff_date).to_numpy())
    if len(keep_candidates) == 0:
        empty_df = df.iloc[0:0].copy().reset_index(drop=True)
        empty_arrays = tuple(np.asarray(a)[0:0] for a in arrays)
        return empty_df, empty_arrays

    keep = slice(int(keep_candidates[0]), None)
    df_out = df.iloc[keep].copy().reset_index(drop=True)
    arr_out = tuple(np.asarray(a)[keep] for a in arrays)
    return df_out, arr_out


def _normalize_intraday_timeframe(timeframe: str) -> str:
    tf = (timeframe or "").strip().lower()
    return INTRADAY_TF_MAP.get(tf, tf)


def _first_idx_on_or_after_ist_open(ts_ist: pd.Series, cutoff_ist: pd.Timestamp) -> int | None:
    """
    Return first index at/after cutoff, preferring a 09:15 IST bar.
    Falls back to the first bar at/after cutoff when 09:15 is absent.
    """
    if ts_ist is None or len(ts_ist) == 0:
        return None

    ts = pd.to_datetime(ts_ist, errors="coerce")
    ge_cutoff = ts >= cutoff_ist
    is_open_915 = (ts.dt.hour == 9) & (ts.dt.minute == 15)

    open_candidates = np.flatnonzero((ge_cutoff & is_open_915).to_numpy())
    if len(open_candidates) > 0:
        return int(open_candidates[0])

    fallback_candidates = np.flatnonzero(ge_cutoff.to_numpy())
    if len(fallback_candidates) == 0:
        return None
    return int(fallback_candidates[0])


def _stabilized_cutoff_ist(
    ts_ist: pd.Series,
    aligned_start_ist: pd.Timestamp,
    required_warmup_bars: int,
) -> pd.Timestamp | None:
    """
    Compute bar-count based stabilization cutoff.

    If there are fewer than `required_warmup_bars` rows before aligned_start,
    push cutoff forward by the exact shortfall in rows, then re-align to the
    next 09:15 bar.
    """
    aligned_idx = _first_idx_on_or_after_ist_open(ts_ist, aligned_start_ist)
    if aligned_idx is None:
        return None

    if required_warmup_bars <= 0 or aligned_idx >= required_warmup_bars:
        return aligned_start_ist

    shortfall = required_warmup_bars - aligned_idx
    target_idx = aligned_idx + shortfall
    if target_idx >= len(ts_ist):
        return None

    target_ts = pd.Timestamp(ts_ist.iloc[target_idx])
    re_aligned_idx = _first_idx_on_or_after_ist_open(ts_ist, target_ts)
    if re_aligned_idx is None:
        return target_ts
    return pd.Timestamp(ts_ist.iloc[re_aligned_idx])


def _load_intraday_ts_ist(symbol: str, exchange: str, timeframe: str) -> pd.Series:
    """
    Load sorted intraday timestamps for one symbol/exchange/timeframe in IST.
    """
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT timestamp
                FROM intraday_candles
                WHERE symbol=%s AND exchange=%s AND timeframe=%s
                ORDER BY timestamp ASC
                """,
                (symbol, exchange, timeframe),
            )
            rows = cur.fetchall()

    if not rows:
        return pd.Series([], dtype="datetime64[ns, Asia/Kolkata]")

    vals = []
    for r in rows:
        vals.append(r["timestamp"] if isinstance(r, dict) else r[0])

    ts = pd.to_datetime(pd.Series(vals), errors="coerce").dropna().reset_index(drop=True)
    if ts.empty:
        return pd.Series([], dtype="datetime64[ns, Asia/Kolkata]")

    if ts.dt.tz is None:
        ts = ts.dt.tz_localize("UTC")
    return ts.dt.tz_convert("Asia/Kolkata")


def _warmup_calendar_days_estimate(required_warmup_bars: int, tf_min: int) -> int:
    """
    Estimate calendar days required to acquire `required_warmup_bars` intraday rows.

    Uses trading-session bars/day, then converts sessions->calendar days and adds
    buffer for exchange holidays and occasional missing sessions.
    """
    bars_per_session = max(INTRADAY_TRADING_MINUTES_PER_SESSION // max(tf_min, 1), 1)
    sessions_needed = int(np.ceil(max(required_warmup_bars, 0) / bars_per_session))
    calendar_days = int(np.ceil(sessions_needed * (7.0 / 5.0)))
    return max(calendar_days + INTRADAY_PAD_BUFFER_CALENDAR_DAYS, INTRADAY_PAD_BUFFER_CALENDAR_DAYS)


def _tf_to_api_minutes(timeframe: str) -> str | None:
    tf = (timeframe or "").strip().lower()
    mapping = {"1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30", "60m": "60"}
    return mapping.get(tf)


def _resolve_instrument_key(symbol: str, exchange: str) -> str | None:
    entry = SYMBOL_TO_KEY.get((symbol or "").upper().strip())
    if not entry:
        return None
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        ex = (exchange or "").upper().strip()
        return entry.get(ex) or entry.get("NSE") or entry.get("BSE") or entry.get("INDEX")
    return None


def _fetch_and_store_intraday_padding(
    symbol: str,
    exchange: str,
    timeframe: str,
    instrument_key: str,
    start_date: date,
    end_date: date,
):
    """
    Fetch historical intraday candles from Upstox and upsert into intraday_candles.
    Returns (inserted_rows, received_rows).
    """
    if start_date > end_date:
        return 0, 0

    api_tf = _tf_to_api_minutes(timeframe)
    if not api_tf:
        raise ValueError(f"Unsupported timeframe for padding: {timeframe}")

    token = get_valid_token()
    if not token:
        raise ValueError("No Upstox access token for auto-padding")

    tf = str(timeframe).strip().lower()
    if tf.endswith("m"):
        interval = int(tf[:-1])
        delta = relativedelta(months=1 if interval <= 15 else 3)
    elif tf.endswith("h"):
        delta = relativedelta(months=3)
    else:
        raise ValueError(f"Unsupported timeframe for padding: {timeframe}")

    chunks = []
    cur = start_date
    while cur <= end_date:
        chunk_to = min(cur + delta - relativedelta(days=1), end_date)
        chunks.append((cur, chunk_to))
        cur = chunk_to + relativedelta(days=1)

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    total_inserted = 0
    total_received = 0
    for cf, ct in chunks:
        url = f"{UPSTOX_V3_BASE}/historical-candle/{instrument_key}/minutes/{api_tf}/{ct}/{cf}"
        r = safe_requests.get(url, headers=headers, timeout=30)
        if r.status_code != 200:
            raise ValueError(f"Upstox padding fetch failed ({r.status_code}): {r.text}")

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
                    execute_batch(
                        cur_db,
                        """
                        INSERT INTO intraday_candles (symbol,exchange,timestamp,open,high,low,close,volume,timeframe)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (symbol,exchange,timestamp,timeframe)
                        DO UPDATE SET open=EXCLUDED.open,high=EXCLUDED.high,low=EXCLUDED.low,
                                      close=EXCLUDED.close,volume=EXCLUDED.volume
                        """,
                        rows,
                        page_size=500,
                    )
            total_inserted += len(rows)
    return total_inserted, total_received


@indicators_bp.route("/api/indicators/daily", methods=["GET"])
def api_indicators_daily():
    try:
        symbol   = request.args.get("symbol",  "").upper().strip()
        exchange = request.args.get("exchange", "NSE").upper().strip()
        history_years_raw = (request.args.get("history_years") or "").strip()
        warmup_bars_raw = (request.args.get("warmup_bars") or "").strip()
        debug_warmup_raw = (request.args.get("debug_warmup") or "").strip().lower()
        debug_warmup = debug_warmup_raw in {"1", "true", "yes", "y", "on"}

        def _dbg(msg: str):
            if debug_warmup:
                print(f"[indicators][daily-warmup] {msg}", flush=True)

        if not symbol:
            return jsonify({"error": "symbol is required"}), 400

        history_years = INTRADAY_ALIGN_YEARS_DEFAULT
        if history_years_raw:
            try:
                history_years = int(history_years_raw)
            except ValueError:
                return jsonify({"error": "history_years must be an integer"}), 400
            if history_years <= 0:
                return jsonify({"error": "history_years must be >= 1"}), 400

        required_warmup_bars = INDICATOR_WARMUP_BARS
        if warmup_bars_raw:
            try:
                required_warmup_bars = int(warmup_bars_raw)
            except ValueError:
                return jsonify({"error": "warmup_bars must be an integer"}), 400
            if required_warmup_bars < 0:
                return jsonify({"error": "warmup_bars must be >= 0"}), 400

        aligned_start_ist = _intraday_aligned_cutoff_ist(history_years)
        aligned_start_date = aligned_start_ist.date()
        _dbg(
            "symbol={symbol} exchange={exchange} history_years={history_years} "
            "warmup_bars={required_warmup_bars} aligned_start_ist={aligned_start_ist} "
            "aligned_start_date={aligned_start_date}".format(
                symbol=symbol,
                exchange=exchange,
                history_years=history_years,
                required_warmup_bars=required_warmup_bars,
                aligned_start_ist=aligned_start_ist,
                aligned_start_date=aligned_start_date,
            )
        )

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
        if df.empty:
            return jsonify({"error": "No valid candle timestamps found"}), 404

        ts_col = pd.to_datetime(df["ts"], errors="coerce")
        if ts_col.dt.tz is None:
            ts_col = ts_col.dt.tz_localize("UTC")
        ts_ist = ts_col.dt.tz_convert("Asia/Kolkata")
        df["ts"] = ts_ist
        if debug_warmup:
            _dbg(f"pulled_rows={len(df)}")
            _dbg(f"pulled_ts_range_ist first={df['ts'].iloc[0]} last={df['ts'].iloc[-1]}")

        if len(df) < MIN_CANDLES_DAILY:
            return jsonify({
                "error": f"Not enough candles â€” need {MIN_CANDLES_DAILY}, got {len(df)}."
            }), 400

        aligned_candidates = np.flatnonzero((ts_ist.dt.date >= aligned_start_date).to_numpy())
        if len(aligned_candidates) == 0:
            cutoff_str = aligned_start_ist.strftime("%Y-%m-%d %H:%M %Z")
            return jsonify({
                "error": (
                    "No daily rows available at/after aligned cutoff "
                    f"({cutoff_str}). Fetch more recent history and retry."
                )
            }), 400

        aligned_idx = int(aligned_candidates[0])
        if aligned_idx < required_warmup_bars:
            missing = required_warmup_bars - aligned_idx
            return jsonify({
                "error": (
                    "Not enough pre-alignment daily history for indicator stabilization. "
                    f"Need {required_warmup_bars} warmup bars before {aligned_start_date}, "
                    f"but only {aligned_idx} found. Fetch at least {missing} older daily bars."
                )
            }), 400

        warmup_start_idx = max(aligned_idx - required_warmup_bars, 0)
        df = df.iloc[warmup_start_idx:].copy().reset_index(drop=True)
        _dbg(
            "stage1_done aligned_idx={aligned_idx} warmup_start_idx={warmup_start_idx} "
            "rows_after_stage1={rows} first_ts_ist={first_ts} last_ts_ist={last_ts}".format(
                aligned_idx=aligned_idx,
                warmup_start_idx=warmup_start_idx,
                rows=len(df),
                first_ts=df["ts"].iloc[0],
                last_ts=df["ts"].iloc[-1],
            )
        )

        # Extract numpy arrays â€” single allocation, all subsequent ops are numpy
        c = df["close"].to_numpy(dtype=float)
        h = df["high"].to_numpy(dtype=float)
        l = df["low"].to_numpy(dtype=float)
        v = df["volume"].to_numpy(dtype=float)
        o = df["open"].to_numpy(dtype=float)

        # â”€â”€ Compute all indicators â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

        # Daily VWAP â€” session typical price (H+L+C)/3 per bar.
        # Each daily bar IS one complete trading session so the
        # volume-weighted average price is best approximated by
        # the bar's typical price. Cumulative-history VWAP behaves
        # as an anchored VWAP from day 1 â€” not useful for trading
        # decisions. Industry standard on daily TF: typical price
        # as session VWAP proxy.
        vwap = (h + l + c) / 3.0

        vsma20  = _sma(v, 20)
        vsma200 = _sma(v, 200)
        # Volume ratio â€” log-transform to tame right-skew spikes.
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

        # Stage 2 trim: remove warmup bars from output and align by shared date.
        df, (
            o, h, l, c, v,
            ema9, ema21, ema50, ema200,
            st_val, vwap,
            rsi, macd_l, macd_s, macd_h, atr,
            bb_mid, bb_up, bb_lo, tr,
            vsma20, vsma200, vratio, obv,
            st_sig_str,
        ) = _slice_from_ist_date(
            df,
            o, h, l, c, v,
            ema9, ema21, ema50, ema200,
            st_val, vwap,
            rsi, macd_l, macd_s, macd_h, atr,
            bb_mid, bb_up, bb_lo, tr,
            vsma20, vsma200, vratio, obv,
            st_sig_str,
            cutoff_date=aligned_start_date,
        )
        if df.empty:
            cutoff_str = aligned_start_ist.strftime("%Y-%m-%d %H:%M %Z")
            return jsonify({
                "error": (
                    "No daily rows left after aligned cut "
                    f"({cutoff_str}). Fetch more history and retry."
                )
            }), 400
        _dbg(
            "stage2_done rows_out={rows} first_ts_ist={first_ts} last_ts_ist={last_ts}".format(
                rows=len(df),
                first_ts=df["ts"].iloc[0],
                last_ts=df["ts"].iloc[-1],
            )
        )

        # â”€â”€ Build rows (vectorised) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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


# â”€â”€ Intraday indicators â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@indicators_bp.route("/api/indicators/intraday", methods=["GET"])
def api_indicators_intraday():
    try:
        symbol    = request.args.get("symbol",    "").upper().strip()
        timeframe = _normalize_intraday_timeframe(request.args.get("timeframe", ""))
        exchange  = request.args.get("exchange",  "NSE").upper().strip()
        history_years_raw = (request.args.get("history_years") or "").strip()
        warmup_bars_raw = (request.args.get("warmup_bars") or "").strip()
        debug_warmup_raw = (request.args.get("debug_warmup") or "").strip().lower()
        auto_pad_raw = (request.args.get("auto_pad") or "").strip().lower()
        stabilize_with_raw = (request.args.get("stabilize_with_tf") or "").strip()
        debug_warmup = debug_warmup_raw in {"1", "true", "yes", "y", "on"}
        auto_pad = auto_pad_raw not in {"0", "false", "no", "off"}

        def _dbg(msg: str):
            if debug_warmup:
                print(f"[indicators][warmup] {msg}", flush=True)

        if not symbol or not timeframe:
            return jsonify({"error": "symbol & timeframe required"}), 400

        if timeframe not in INTRADAY_TF_MINUTES:
            return jsonify({"error": f"Unsupported timeframe: {timeframe}"}), 400

        history_years = INTRADAY_ALIGN_YEARS_DEFAULT
        if history_years_raw:
            try:
                history_years = int(history_years_raw)
            except ValueError:
                return jsonify({"error": "history_years must be an integer"}), 400
            if history_years <= 0:
                return jsonify({"error": "history_years must be >= 1"}), 400

        required_warmup_bars = INDICATOR_WARMUP_BARS
        if warmup_bars_raw:
            try:
                required_warmup_bars = int(warmup_bars_raw)
            except ValueError:
                return jsonify({"error": "warmup_bars must be an integer"}), 400
            if required_warmup_bars < 0:
                return jsonify({"error": "warmup_bars must be >= 0"}), 400

        stabilize_with_tf = _normalize_intraday_timeframe(
            stabilize_with_raw or INTRADAY_STABILIZE_WITH_TF_DEFAULT
        )
        if stabilize_with_tf not in INTRADAY_TF_MINUTES:
            return jsonify({"error": f"Unsupported stabilize_with_tf: {stabilize_with_tf}"}), 400

        tf_min = INTRADAY_TF_MINUTES[timeframe]
        stabilize_tf_min = INTRADAY_TF_MINUTES[stabilize_with_tf]
        warmup_tf_min = max(tf_min, stabilize_tf_min)
        warmup_calendar_days = _warmup_calendar_days_estimate(
            required_warmup_bars, warmup_tf_min
        )

        aligned_start_ist = _intraday_aligned_cutoff_ist(history_years)
        warmup_cutoff_ist = aligned_start_ist - pd.Timedelta(days=warmup_calendar_days)
        _dbg(
            "symbol={symbol} exchange={exchange} timeframe={timeframe} "
            "history_years={history_years} warmup_bars={required_warmup_bars} "
            "tf_min={tf_min} stabilize_with_tf={stabilize_with_tf} "
            "warmup_tf_min={warmup_tf_min} warmup_calendar_days={warmup_calendar_days} "
            "aligned_start_ist={aligned_start_ist} warmup_cutoff_ist={warmup_cutoff_ist}".format(
                symbol=symbol,
                exchange=exchange,
                timeframe=timeframe,
                history_years=history_years,
                required_warmup_bars=required_warmup_bars,
                tf_min=tf_min,
                stabilize_with_tf=stabilize_with_tf,
                warmup_tf_min=warmup_tf_min,
                warmup_calendar_days=warmup_calendar_days,
                aligned_start_ist=aligned_start_ist,
                warmup_cutoff_ist=warmup_cutoff_ist,
            )
        )

        def _load_rows():
            with get_db_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT timestamp, open, high, low, close, volume "
                        "FROM intraday_candles "
                        "WHERE symbol=%s AND timeframe=%s AND exchange=%s "
                        "ORDER BY timestamp ASC",
                        (symbol, timeframe, exchange),
                    )
                    return cur.fetchall()

        rows_raw = _load_rows()

        if not rows_raw and auto_pad:
            instrument_key = _resolve_instrument_key(symbol, exchange)
            if not instrument_key:
                return jsonify({
                    "error": (
                        f"No data found and auto-padding failed: instrument key not found for {symbol}/{exchange}."
                    )
                }), 404
            pad_from = warmup_cutoff_ist.date()
            pad_to = (pd.Timestamp.now(tz="Asia/Kolkata") - pd.Timedelta(days=1)).date()
            _dbg(
                "auto_pad_bootstrap fetch_from={pad_from} fetch_to={pad_to} instrument_key={ik}".format(
                    pad_from=pad_from,
                    pad_to=pad_to,
                    ik=instrument_key,
                )
            )
            inserted, received = _fetch_and_store_intraday_padding(
                symbol=symbol,
                exchange=exchange,
                timeframe=timeframe,
                instrument_key=instrument_key,
                start_date=pad_from,
                end_date=pad_to,
            )
            _dbg(f"auto_pad_bootstrap_done received={received} inserted={inserted}")
            rows_raw = _load_rows()

        if not rows_raw:
            return jsonify({"error": "No data found"}), 404

        df = pd.DataFrame([dict(r) for r in rows_raw])
        _dbg(f"pulled_rows={len(df)}")
        df.rename(columns={"timestamp": "ts"}, inplace=True)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.sort_values("ts").reset_index(drop=True)
        if debug_warmup and not df.empty:
            _dbg(f"pulled_ts_range_utc first={df['ts'].iloc[0]} last={df['ts'].iloc[-1]}")

        # Option-1 data padding fix: ensure DB physically includes pre-warmup window.
        if auto_pad and not df.empty:
            ts_probe = pd.to_datetime(df["ts"], errors="coerce")
            if ts_probe.dt.tz is None:
                ts_probe = ts_probe.dt.tz_localize("UTC")
            earliest_ist = ts_probe.dt.tz_convert("Asia/Kolkata").iloc[0]
            if earliest_ist > warmup_cutoff_ist:
                instrument_key = _resolve_instrument_key(symbol, exchange)
                if not instrument_key:
                    return jsonify({
                        "error": (
                            f"Auto-padding failed: instrument key not found for {symbol}/{exchange}. "
                            "Backfill missing history manually or disable auto_pad."
                        )
                    }), 400

                pad_from = warmup_cutoff_ist.date()
                pad_to = (earliest_ist - pd.Timedelta(days=1)).date()
                _dbg(
                    "auto_pad_needed earliest_ist={earliest} warmup_cutoff_ist={cutoff} "
                    "fetch_from={pad_from} fetch_to={pad_to} instrument_key={ik}".format(
                        earliest=earliest_ist,
                        cutoff=warmup_cutoff_ist,
                        pad_from=pad_from,
                        pad_to=pad_to,
                        ik=instrument_key,
                    )
                )
                inserted, received = _fetch_and_store_intraday_padding(
                    symbol=symbol,
                    exchange=exchange,
                    timeframe=timeframe,
                    instrument_key=instrument_key,
                    start_date=pad_from,
                    end_date=pad_to,
                )
                _dbg(f"auto_pad_done received={received} inserted={inserted}")
                rows_raw = _load_rows()
                if not rows_raw:
                    return jsonify({"error": "No data found after auto-padding"}), 404
                df = pd.DataFrame([dict(r) for r in rows_raw])
                df.rename(columns={"timestamp": "ts"}, inplace=True)
                for col in ["open", "high", "low", "close", "volume"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                df = df.sort_values("ts").reset_index(drop=True)
                _dbg(f"post_auto_pad_rows={len(df)}")

        if len(df) < MIN_CANDLES_INTRADAY:
            return jsonify({
                "error": f"Not enough candles â€” need {MIN_CANDLES_INTRADAY}, "
                         f"got {len(df)}. Fetch more history for {symbol} ({timeframe})."
            }), 400

        # â”€â”€ IST conversion â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # Must happen BEFORE indicator computation so bar_of_day
        # and date grouping use the correct NSE session boundaries.
        ts_col = pd.to_datetime(df["ts"], errors="coerce")
        if ts_col.dt.tz is None:
            ts_col = ts_col.dt.tz_localize("UTC")
        ts_ist  = ts_col.dt.tz_convert("Asia/Kolkata")
        df["ts"] = ts_ist
        raw_rows_total = len(df)
        if raw_rows_total <= required_warmup_bars:
            return jsonify({
                "error": (
                    f"Insufficient data: Retrieved {raw_rows_total} rows, "
                    f"but {required_warmup_bars} are needed just for warmup."
                )
            }), 400

        own_stabilized_cutoff_ist = _stabilized_cutoff_ist(
            ts_ist, aligned_start_ist, required_warmup_bars
        )
        if own_stabilized_cutoff_ist is None:
            return jsonify({
                "error": (
                    "Insufficient rows to stabilize indicators by bar-count before aligned start. "
                    "Fetch older history and retry."
                )
            }), 400

        # Stage 1 trim: keep exactly `required_warmup_bars` rows before aligned start.
        # This is bar-count based and robust to overnight/weekend market gaps.
        aligned_idx_base = _first_idx_on_or_after_ist_open(ts_ist, aligned_start_ist)
        if aligned_idx_base is None:
            cutoff_str = aligned_start_ist.strftime("%Y-%m-%d %H:%M %Z")
            return jsonify({
                "error": (
                    "No rows available at/after aligned cutoff "
                    f"({cutoff_str}). Fetch newer history and retry."
                )
            }), 400

        stage1_in_rows = len(df)
        stage1_start_idx = max(aligned_idx_base - required_warmup_bars, 0)
        df = df.iloc[stage1_start_idx:].copy().reset_index(drop=True)
        if df.empty:
            return jsonify({
                "error": "No rows left after bar-count warmup trim."
            }), 400

        effective_cutoff_ist = own_stabilized_cutoff_ist
        anchor_cutoff_ist = None
        if stabilize_with_tf != timeframe:
            anchor_ts_ist = _load_intraday_ts_ist(symbol, exchange, stabilize_with_tf)
            if anchor_ts_ist.empty:
                return jsonify({
                    "error": (
                        f"Cannot align for labeling: no {stabilize_with_tf} candles found for "
                        f"{symbol}/{exchange}."
                    )
                }), 400

            anchor_cutoff_ist = _stabilized_cutoff_ist(
                anchor_ts_ist, aligned_start_ist, required_warmup_bars
            )
            if anchor_cutoff_ist is None:
                return jsonify({
                    "error": (
                        f"Cannot align for labeling: insufficient {stabilize_with_tf} history "
                        "to satisfy warmup bars."
                    )
                }), 400
            effective_cutoff_ist = max(effective_cutoff_ist, anchor_cutoff_ist)
            _dbg(
                "anchor_alignment anchor_tf={anchor_tf} anchor_cutoff_ist={anchor_cutoff} "
                "effective_cutoff_ist={effective}".format(
                    anchor_tf=stabilize_with_tf,
                    anchor_cutoff=anchor_cutoff_ist,
                    effective=effective_cutoff_ist,
                )
            )

        _dbg(
            "stage1_done rows_in={rows_in} rows_out={rows_out} start_idx={start_idx} "
            "first_ts_ist={first_ts} last_ts_ist={last_ts} own_cutoff_ist={own_cutoff} "
            "effective_cutoff_ist={effective_cutoff}".format(
                rows_in=stage1_in_rows,
                rows_out=len(df),
                start_idx=stage1_start_idx,
                first_ts=df["ts"].iloc[0],
                last_ts=df["ts"].iloc[-1],
                own_cutoff=own_stabilized_cutoff_ist,
                effective_cutoff=effective_cutoff_ist,
            )
        )
        ts_ist = pd.to_datetime(df["ts"], errors="coerce")

        # bar_of_day: 0 = 09:15, 1 = 09:16 (for 1m), etc.
        # Used for ORB and VWAP date grouping â€” avoids re-parsing dates.
        ist_hour   = ts_ist.dt.hour.to_numpy()
        ist_minute = ts_ist.dt.minute.to_numpy()
        bar_of_day = (ist_hour * 60 + ist_minute - 555) // tf_min
        # Negative values can appear before 09:15 â€” clamp to 0
        bar_of_day = np.maximum(bar_of_day, 0)

        # Integer date for VWAP grouping (ordinal avoids string overhead)
        date_int = ts_ist.dt.date.map(lambda d: d.toordinal()).to_numpy()

        # â”€â”€ Extract arrays â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        c = df["close"].to_numpy(dtype=float)
        h = df["high"].to_numpy(dtype=float)
        l = df["low"].to_numpy(dtype=float)
        v = df["volume"].to_numpy(dtype=float)
        o = df["open"].to_numpy(dtype=float)

        # â”€â”€ Compute all indicators â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

        # â”€â”€ VWAP â€” resets each trading day â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        vwap = _vwap_intraday(h, l, c, v, date_int)

        # â”€â”€ Volume baselines â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        vsma20  = _sma(v, 20)
        vsma200 = _sma(v, 200)
        # Volume ratio â€” log-transform (same reasoning as daily).
        vratio  = np.where(vsma20 > 0,
                           np.log1p(v / np.where(vsma20 > 0, vsma20, 1.0)),
                           0.0)

        # â”€â”€ ORB â€” Opening Range Breakout (fixed clock window) â”€â”€â”€â”€â”€â”€â”€
        # Industry standard: 09:15 to 09:30 IST regardless of TF.
        # Fixed clock is immune to irregular timestamps; bar-count
        # derivation drifts by one bar on any missing tick.
        orb_h, orb_l = _orb(h, l, ts_ist,
                             orb_start=dtime(9, 15),
                             orb_end=dtime(9, 30))

        orb_brk = c > orb_h
        orb_brd = c < orb_l

        # signal and signal_strength are NOT computed here â€” always NULL.
        # orb_breakout / orb_breakdown boolean columns carry ORB state.
        # strategy.py reads those and makes the actual trading decisions.
        st_sig_str = np.where(c > st_val, "UP", "DOWN")

        # Stage 2 trim: final aligned start for output/DB writes.
        # All timeframes now begin from the same aligned 09:15 IST session start.
        stage2_in_rows = len(df)
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
        ) = _slice_from_ist_open(
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
            cutoff_ist=effective_cutoff_ist,
        )

        if df.empty:
            cutoff_str = effective_cutoff_ist.strftime("%Y-%m-%d %H:%M %Z")
            return jsonify({
                "error": (
                    "No rows available at/after aligned cutoff "
                    f"({cutoff_str}). Fetch older history and retry."
                )
            }), 400
        _dbg(
            "stage2_done rows_in={rows_in} rows_out={rows_out} first_ts_ist={first_ts} last_ts_ist={last_ts}".format(
                rows_in=stage2_in_rows,
                rows_out=len(df),
                first_ts=df["ts"].iloc[0],
                last_ts=df["ts"].iloc[-1],
            )
        )

        # â”€â”€ Build rows and upsert â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
        _dbg(f"upsert_done rows={len(rows)} cutoff_ts={cutoff_ts}")

        response = {"status": "SUCCESS", "rows": len(rows)}
        if debug_warmup:
            response["debug"] = {
                "timeframe": timeframe,
                "stabilize_with_tf": stabilize_with_tf,
                "required_warmup_bars": required_warmup_bars,
                "raw_rows_total": raw_rows_total,
                "stage1_start_idx": stage1_start_idx,
                "stage1_rows_out": stage2_in_rows,
                "stage2_rows_out": len(df),
                "rows_dropped_total": raw_rows_total - len(df),
                "aligned_start_ist": str(aligned_start_ist),
                "own_stabilized_cutoff_ist": str(own_stabilized_cutoff_ist),
                "anchor_stabilized_cutoff_ist": str(anchor_cutoff_ist) if anchor_cutoff_ist is not None else None,
                "effective_cutoff_ist": str(effective_cutoff_ist),
                "first_output_ts_ist": str(df["ts"].iloc[0]),
                "last_output_ts_ist": str(df["ts"].iloc[-1]),
            }

        return jsonify(response)

    except Exception:
        traceback.print_exc()
        return jsonify({"error": traceback.format_exc()}), 500

