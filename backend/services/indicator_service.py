# services/indicator_service.py
# ================================================================
#  Centralized, high-performance Technical Indicators engine.
#  Uses 100% C-vectorized NumPy and Pandas computations to guarantee
#  consistent calculations across REST API, WebSockets, and ML models.
# ================================================================
import numpy as np
import pandas as pd


def calculate_ema(arr: np.ndarray | pd.Series, period: int) -> np.ndarray:
    """Calculates Exponential Moving Average."""
    values = np.asarray(arr, dtype=np.float64)
    return pd.Series(values).ewm(span=period, adjust=False).mean().to_numpy()


def calculate_sma(arr: np.ndarray | pd.Series, period: int) -> np.ndarray:
    """Calculates Simple Moving Average."""
    values = np.asarray(arr, dtype=np.float64)
    return pd.Series(values).rolling(period).mean().to_numpy()


def calculate_rsi(arr: np.ndarray | pd.Series, period: int = 14) -> np.ndarray:
    """
    RSI using Wilder's smoothing (EWM with com=period-1).
    Uses total gain/loss relative smoothing to prevent 0/100 lockup on flat prices.
    """
    values = np.asarray(arr, dtype=np.float64)
    if len(values) == 0:
        return np.array([], dtype=np.float64)
        
    delta = np.diff(values, prepend=values[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    
    avg_g = pd.Series(gain).ewm(com=period - 1, adjust=False).mean().to_numpy()
    avg_l = pd.Series(loss).ewm(com=period - 1, adjust=False).mean().to_numpy()
    
    total = avg_g + avg_l
    rsi = np.full(len(values), 50.0, dtype=np.float64)
    
    nonzero_mask = total > 1e-12
    rsi[nonzero_mask] = 100.0 * (avg_g[nonzero_mask] / total[nonzero_mask])
    return rsi


def calculate_macd(
    arr: np.ndarray | pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    MACD (Fast EMA - Slow EMA), Signal (EMA of MACD), Histogram (MACD - Signal).
    """
    values = np.asarray(arr, dtype=np.float64)
    if len(values) == 0:
        empty = np.array([], dtype=np.float64)
        return empty, empty, empty

    fast_ema = calculate_ema(values, fast)
    slow_ema = calculate_ema(values, slow)
    macd_line = fast_ema - slow_ema
    signal_line = calculate_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calculate_true_range(h: np.ndarray, l: np.ndarray, c: np.ndarray) -> np.ndarray:
    n = len(c)
    if n == 0:
        return np.array([], dtype=np.float64)
    prev_c = np.roll(c, 1)
    prev_c[0] = c[0]
    tr1 = h - l
    tr2 = np.abs(h - prev_c)
    tr3 = np.abs(l - prev_c)
    return np.maximum(tr1, np.maximum(tr2, tr3))


def calculate_atr(h: np.ndarray, l: np.ndarray, c: np.ndarray, period: int = 14) -> np.ndarray:
    tr = calculate_true_range(h, l, c)
    if len(tr) == 0:
        return np.array([], dtype=np.float64)
    return pd.Series(tr).ewm(com=period - 1, adjust=False).mean().to_numpy()


def calculate_bollinger(arr: np.ndarray | pd.Series, period: int = 20, num_std: float = 2.0):
    values = np.asarray(arr, dtype=np.float64)
    if len(values) == 0:
        empty = np.array([], dtype=np.float64)
        return empty, empty, empty

    s = pd.Series(values)
    mid = s.rolling(period).mean()
    std = s.rolling(period).std(ddof=0)
    upper = mid + num_std * std
    lower = mid - num_std * std
    return mid.to_numpy(), upper.to_numpy(), lower.to_numpy()


def calculate_obv(c: np.ndarray, v: np.ndarray) -> np.ndarray:
    n = len(c)
    if n == 0:
        return np.array([], dtype=np.float64)
    direction = np.sign(np.diff(c, prepend=c[0]))
    return np.cumsum(direction * v)


def calculate_supertrend(
    h: np.ndarray,
    l: np.ndarray,
    c: np.ndarray,
    period: int = 10,
    mult: float = 3.0
) -> tuple[np.ndarray, np.ndarray]:
    """
    Supertrend indicator.
    Returns: (st_values, st_signal) where 1 = bullish, -1 = bearish
    Fixes Bug 3: Pre-seeds initial bars before seed_idx to valid signal 1.
    """
    n = len(c)
    if n == 0:
        return np.array([], dtype=np.float64), np.array([], dtype=np.int8)

    atr = calculate_atr(h, l, c, period)
    hl2 = (h + l) * 0.5
    ub = hl2 + mult * atr
    lb = hl2 - mult * atr

    final_ub = np.empty(n, dtype=np.float64)
    final_lb = np.empty(n, dtype=np.float64)
    final_ub[0] = ub[0]
    final_lb[0] = lb[0]

    for i in range(1, n):
        final_ub[i] = ub[i] if (ub[i] < final_ub[i-1] or c[i-1] > final_ub[i-1]) else final_ub[i-1]
        final_lb[i] = lb[i] if (lb[i] > final_lb[i-1] or c[i-1] < final_lb[i-1]) else final_lb[i-1]

    st_val = np.full(n, np.nan, dtype=np.float64)
    st_sig = np.ones(n, dtype=np.int8)  # Initialize with 1 (Bullish) instead of 0

    seed_idx = min(period - 1, n - 1)
    st_val[0:seed_idx+1] = final_lb[0:seed_idx+1]
    st_sig[0:seed_idx+1] = 1

    for i in range(seed_idx + 1, n):
        if st_sig[i-1] == 1:
            st_val[i] = final_lb[i]
            st_sig[i] = -1 if c[i] < final_lb[i] else 1
        else:
            st_val[i] = final_ub[i]
            st_sig[i] = 1 if c[i] > final_ub[i] else -1

    return st_val, st_sig


def calculate_signals(
    c: np.ndarray,
    ema9: np.ndarray,
    ema21: np.ndarray,
    rsi: np.ndarray,
    macd_h: np.ndarray,
    st_sig: np.ndarray | list
) -> tuple[list[str], np.ndarray]:
    """
    Computes technical indicator consensus signal ('BUY', 'SELL', 'NEUTRAL')
    and signal_strength float (0.00 to 1.00) using 100% vectorized NumPy operations.
    """
    c_arr = np.asarray(c, dtype=np.float64)
    n = len(c_arr)
    if n == 0:
        return [], np.array([], dtype=np.float64)

    e9_arr = np.where(np.isnan(ema9), c_arr, ema9) if len(ema9) == n else c_arr
    e21_arr = np.where(np.isnan(ema21), c_arr, ema21) if len(ema21) == n else c_arr
    rsi_arr = np.where(np.isnan(rsi), 50.0, rsi) if len(rsi) == n else np.full(n, 50.0)
    mh_arr = np.where(np.isnan(macd_h), 0.0, macd_h) if len(macd_h) == n else np.zeros(n)

    score = np.zeros(n, dtype=np.float64)

    # 1. Supertrend Trend Alignment (+0.35 / -0.35)
    if st_sig is not None:
        st_arr = np.asarray(st_sig)
        if len(st_arr) == n:
            score += np.where((st_arr == 1) | (st_arr == "1") | (st_arr == "UP") | (st_arr == "BUY"), 0.35, 0.0)
            score -= np.where((st_arr == -1) | (st_arr == "-1") | (st_arr == "DOWN") | (st_arr == "SELL"), 0.35, 0.0)

    # 2. Moving Average Alignment (+0.30 / -0.30)
    score += np.where(e9_arr > e21_arr, 0.30, 0.0)
    score -= np.where(e9_arr < e21_arr, 0.30, 0.0)

    # 3. MACD Momentum (+0.20 / -0.20)
    score += np.where(mh_arr > 0, 0.20, 0.0)
    score -= np.where(mh_arr < 0, 0.20, 0.0)

    # 4. RSI Momentum & Overbought/Oversold (+0.15 / -0.15)
    score += np.where((rsi_arr >= 50.0) & (rsi_arr < 70.0), 0.15, 0.0)
    score -= np.where((rsi_arr > 30.0) & (rsi_arr < 50.0), 0.15, 0.0)

    strengths = np.clip(np.round(np.abs(score), 2), 0.0, 1.0)
    signals = np.where(score >= 0.40, "BUY", np.where(score <= -0.40, "SELL", "NEUTRAL")).tolist()
    return signals, strengths


def compute_all_indicators(df: pd.DataFrame, force_recompute: bool = False) -> pd.DataFrame:
    """
    Applies standard indicators to an OHLCV DataFrame in-place and returns it.
    Includes validation to prevent redundant re-computation if indicators are already calculated.
    Required columns: ['open', 'high', 'low', 'close', 'volume']
    """
    if df.empty:
        return df

    # Check if key indicator columns are already present and populated
    indicator_cols = [
        'ema_9', 'ema_20', 'ema_50', 'ema_200', 'rsi_14',
        'macd', 'macd_signal', 'macd_hist', 'bb_mid', 'bb_upper',
        'bb_lower', 'atr_14', 'obv', 'supertrend', 'supertrend_signal'
    ]

    if not force_recompute and all(col in df.columns for col in indicator_cols):
        # Fix Bug 2: Validate that indicators exist AND trailing row is populated
        if not pd.isna(df['rsi_14'].iloc[-1]) and not pd.isna(df['supertrend'].iloc[-1]):
            return df

    c = df['close'].to_numpy(dtype=np.float64)
    h = df['high'].to_numpy(dtype=np.float64)
    l = df['low'].to_numpy(dtype=np.float64)
    v = df['volume'].to_numpy(dtype=np.float64) if 'volume' in df.columns else np.zeros(len(c))

    def _stale(col: str) -> bool:
        """True if the column is missing entirely, or exists but its
        trailing row is still NaN (i.e. never actually computed)."""
        return col not in df.columns or pd.isna(df[col].iloc[-1])

    # Compute only missing/stale indicator groups unless force_recompute is True
    if force_recompute or _stale('ema_9'):
        df['ema_9'] = calculate_ema(c, 9)
    if force_recompute or _stale('ema_20'):
        df['ema_20'] = calculate_ema(c, 20)
    if force_recompute or _stale('ema_50'):
        df['ema_50'] = calculate_ema(c, 50)
    if force_recompute or _stale('ema_200'):
        df['ema_200'] = calculate_ema(c, 200)

    if force_recompute or _stale('rsi_14'):
        df['rsi_14'] = calculate_rsi(c, 14)

    if force_recompute or any(_stale(k) for k in ['macd', 'macd_signal', 'macd_hist']):
        macd_line, macd_sig, macd_hist = calculate_macd(c)
        df['macd'] = macd_line
        df['macd_signal'] = macd_sig
        df['macd_hist'] = macd_hist

    if force_recompute or any(_stale(k) for k in ['bb_mid', 'bb_upper', 'bb_lower']):
        bb_mid, bb_upper, bb_lower = calculate_bollinger(c)
        df['bb_mid'] = bb_mid
        df['bb_upper'] = bb_upper
        df['bb_lower'] = bb_lower

    if force_recompute or _stale('atr_14'):
        df['atr_14'] = calculate_atr(h, l, c, 14)

    if force_recompute or _stale('obv'):
        df['obv'] = calculate_obv(c, v)

    if force_recompute or any(_stale(k) for k in ['supertrend', 'supertrend_signal']):
        st_val, st_sig = calculate_supertrend(h, l, c)
        df['supertrend'] = st_val
        df['supertrend_signal'] = st_sig

    return df
