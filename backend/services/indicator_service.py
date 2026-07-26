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
    Guarantees standard technical analysis values across all views.
    """
    values = np.asarray(arr, dtype=np.float64)
    if len(values) == 0:
        return np.array([], dtype=np.float64)
        
    delta = np.diff(values, prepend=values[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    
    avg_g = pd.Series(gain).ewm(com=period - 1, adjust=False).mean().to_numpy()
    avg_l = pd.Series(loss).ewm(com=period - 1, adjust=False).mean().to_numpy()
    
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = np.where(avg_l == 0, np.inf, avg_g / avg_l)
    return np.where(avg_l == 0, 100.0, 100.0 - 100.0 / (1.0 + rs))


def calculate_macd(
    arr: np.ndarray | pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Calculates MACD line, signal line, and histogram."""
    values = np.asarray(arr, dtype=np.float64)
    ema_f = pd.Series(values).ewm(span=fast, adjust=False).mean().to_numpy()
    ema_s = pd.Series(values).ewm(span=slow, adjust=False).mean().to_numpy()
    macd_line = ema_f - ema_s
    sig_line = pd.Series(macd_line).ewm(span=signal, adjust=False).mean().to_numpy()
    histogram = macd_line - sig_line
    return macd_line, sig_line, histogram


def calculate_true_range(h: np.ndarray, l: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Vectorized True Range calculation."""
    prev_c = np.roll(c, 1)
    prev_c[0] = c[0]
    return np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))


def calculate_atr(h: np.ndarray, l: np.ndarray, c: np.ndarray, period: int = 14) -> np.ndarray:
    """ATR using Wilder's smoothing."""
    tr = calculate_true_range(h, l, c)
    return pd.Series(tr).ewm(com=period - 1, adjust=False).mean().to_numpy()


def calculate_bollinger(
    arr: np.ndarray | pd.Series,
    period: int = 20,
    std_dev: float = 2.0
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bollinger Bands: mid, upper, lower."""
    s = pd.Series(np.asarray(arr, dtype=np.float64))
    mid = s.rolling(period).mean().to_numpy()
    std = s.rolling(period).std(ddof=0).to_numpy()
    return mid, mid + std_dev * std, mid - std_dev * std


def calculate_obv(c: np.ndarray, v: np.ndarray) -> np.ndarray:
    """On-Balance Volume (OBV)."""
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
    st_sig = np.zeros(n, dtype=np.int8)

    seed_idx = min(period - 1, n - 1)
    st_val[seed_idx] = final_lb[seed_idx]
    st_sig[seed_idx] = 1

    for i in range(seed_idx + 1, n):
        if st_sig[i-1] == 1:
            st_val[i] = final_lb[i]
            st_sig[i] = -1 if c[i] < final_lb[i] else 1
        else:
            st_val[i] = final_ub[i]
            st_sig[i] = 1 if c[i] > final_ub[i] else -1

    return st_val, st_sig


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
        # Validation: If indicators exist and are populated, skip re-computing
        if not df['rsi_14'].isna().all():
            return df

    c = df['close'].to_numpy(dtype=np.float64)
    h = df['high'].to_numpy(dtype=np.float64)
    l = df['low'].to_numpy(dtype=np.float64)
    v = df['volume'].to_numpy(dtype=np.float64) if 'volume' in df.columns else np.zeros(len(c))

    # Compute only missing indicator groups unless force_recompute is True
    if force_recompute or 'ema_9' not in df.columns:
        df['ema_9'] = calculate_ema(c, 9)
    if force_recompute or 'ema_20' not in df.columns:
        df['ema_20'] = calculate_ema(c, 20)
    if force_recompute or 'ema_50' not in df.columns:
        df['ema_50'] = calculate_ema(c, 50)
    if force_recompute or 'ema_200' not in df.columns:
        df['ema_200'] = calculate_ema(c, 200)

    if force_recompute or 'rsi_14' not in df.columns:
        df['rsi_14'] = calculate_rsi(c, 14)

    if force_recompute or not all(k in df.columns for k in ['macd', 'macd_signal', 'macd_hist']):
        macd_line, macd_sig, macd_hist = calculate_macd(c)
        df['macd'] = macd_line
        df['macd_signal'] = macd_sig
        df['macd_hist'] = macd_hist

    if force_recompute or not all(k in df.columns for k in ['bb_mid', 'bb_upper', 'bb_lower']):
        bb_mid, bb_upper, bb_lower = calculate_bollinger(c)
        df['bb_mid'] = bb_mid
        df['bb_upper'] = bb_upper
        df['bb_lower'] = bb_lower

    if force_recompute or 'atr_14' not in df.columns:
        df['atr_14'] = calculate_atr(h, l, c, 14)

    if force_recompute or 'obv' not in df.columns:
        df['obv'] = calculate_obv(c, v)

    if force_recompute or not all(k in df.columns for k in ['supertrend', 'supertrend_signal']):
        st_val, st_sig = calculate_supertrend(h, l, c)
        df['supertrend'] = st_val
        df['supertrend_signal'] = st_sig

    return df
