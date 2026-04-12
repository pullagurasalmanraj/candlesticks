# routes/strategy.py
# ================================================================
#  Strategy blueprint --- MARKET-BEHAVIOUR IMPROVED VERSION
#
#  ------ PREVIOUS IMPROVEMENTS (v1---v13) ---------------------------------------------------------------------------------------
#  1-8.  Performance, cost model, slippage, chunked inserts (see below)
#  9-13. State machine calibration: p33 compression, EMA stacking,
#        LARGE_GAP_AUCTION demoted, BALANCE_CHOP --- NEUTRAL
#
#  ------ NEW IMPROVEMENTS (v28, data-driven from 490-day outcomes) ------
#
#  28a. PHASE_MODEL TP/SL recalibrated from actual MFE/MAE distributions.
#       Previous TPs (1.5---2.0) were set above p75 of actual MFE, causing
#       TP hit rate of only 11---25% across all phases. New TPs target p50
#       of MFE (TP hit rate ~50%) with sl widened to keep cost_r < 0.70.
#       Net R:R floor 1.5:1 enforced on every phase after recalibration.
#
#  28b. LARGE_GAP_UP direction flipped LONG --- SHORT (fade).
#       490-day data: WR=28.2%, TP%=12.6% as LONG. Gap-up on 15m fades
#       in first 30 min (SL hit rate 50.5% = price falls ---1R from entry).
#       Flipping to SHORT (fade) converts those SL hits into TP hits.
#       Aligned with MODERATE_GAP_UP which already uses SHORT/fade correctly.
#
#  28c. MODERATE_GAP_DOWN direction flipped LONG --- SHORT (continuation).
#       Was treating moderate gap down as fade (LONG) --- data shows 75% SL
#       hit rate and MAE p50 = -1.75R, meaning price continues DOWN strongly.
#       Flipping to SHORT (follow the gap) makes those SL hits into TP hits.
#
#  28d. PULLBACK_FAIL and REJECTION demoted to NEUTRAL.
#       PULLBACK_FAIL: 3.2% TP rate --- the FADE direction almost never works.
#       REJECTION:     9.3% TP rate --- same issue. Both still generate outcome
#       rows so ML trains to skip them.
#
#  28e. ABSORPTION and DISTRIBUTION demoted to NEUTRAL direction.
#       ABSORPTION: FOLLOW direction yields only 22.9% TP --- absorbed volume
#       does not reliably signal next direction at 15m bar granularity.
#       DISTRIBUTION: 17% TP --- fires in bull-trend markets where shorts fail.
#       Both already mapped to NEUTRAL in PHASE_TO_ML; now consistent in PHASE_MODEL.
#
#  28f. GAP_TIMEOUT demoted to NEUTRAL direction.
#       Only 10.9% TP rate with FOLLOW. Gap timeout on 15m resolves into
#       chop not continuation. Outcome rows retained for ML training.
#
#  28g. price_structure swing detector window widened (4--n --- 8--n bars).
#       SWING_N=2 for 15m produced only 15 bars of lookback (9 for detection).
#       With a 9-bar window, finding 2 confirmed swing highs AND 2 swing lows
#       is extremely rare --- 99.9% of bars returned NEUTRAL, disabling the
#       price_structure alignment gate (fix 19) entirely.
#       New 8--n window = 17 bars (255 min) --- enough structure to identify HH/HL.
#
#  28h. End-of-session guard added to calc_strategy_outcomes.
#       Bars with minute_of_day --- 330 (14:45+) skipped for ABSORPTION,
#       DISTRIBUTION, POST_IMPULSE_DIGESTION, COMPRESSION. These phases in the
#       last 45 min have avg_r = -0.81 (worst intraday), driven by low volume
#       and wide spreads near close. Trend/impulse phases unaffected.
#
#  28i. Macro regime gate extended to SHORT phases in BEAR_MACRO.
#       Previously only LONG in BEAR_MACRO was gated. Added: skip SHORT in
#       BEAR_MACRO when phase is BEAR_TREND_CONTINUATION/ACCEPTANCE --- counter-
#       intuitive but 490-day data shows macro alignment is bidirectional.
#       Note: gate is disabled for FOLLOW/FADE/MEAN (directional resolved at runtime).
#
#  ------ NEW IMPROVEMENTS (v23---v27, issue-list driven) ---------------------------------------------
#
#  23. FOLLOW/FADE/MEAN/BREAKOUT direction resolved (was always LONG)
#      FOLLOW  --- gap_atr direction (>0=LONG, <0=SHORT), fallback EMA slope
#      FADE    --- opposite of last impulse_dir, fallback opposite EMA slope
#      MEAN    --- vwap_dist_pct sign (above VWAP --- SHORT, below --- LONG)
#      BREAKOUT--- EMA slope direction
#      NEUTRAL --- skip (no directional bet)
#      Poisoned outcomes for GAP_TIMEOUT, GAP_CONTINUATION, PULLBACK_FAIL,
#      REJECTION, COMPRESSION, ABSORPTION. All now resolve correctly.
#
#  24. Cost viability gate: skip trades where cost_r > 0.70
#      cost_r = (entry -- 0.0015) / R.  At 1m avg ATR, cost_r --- 1.3---1.5R.
#      Gate naturally eliminates most 1m setups while leaving 15m intact.
#      Threshold configurable via "cost_r_gate" body param. Default 0.70.
#      Exposes true viable subset --- ML trains on achievable trades only.
#
#  25. LARGE_GAP_AUCTION_BULL/BEAR restored to GAP_UP/GAP_DOWN
#      Original NEUTRAL demotion was based on 1m data poisoned by SHORT bug.
#      Clean data: 3m=57.5% WR, 5m=40% WR, both with real MFE edge.
#      Bear side restored symmetrically; will produce clean data after fix 14.
#
#  26. Directional confirmation gate on entry bar (fix 1)
#      Signal bar must close in the trade direction before entry is taken.
#      LONG: bar_close > bar_open required. SHORT: bar_close < bar_open.
#      Applied to LONG/SHORT/FOLLOW/FADE only. Skipped for gap phases
#      (bar_of_day==0) and MEAN/BREAKOUT/NEUTRAL (no directional assumption).
#      Eliminates the worst entries --- adverse closes into your direction.
#
#  27. Lookahead uses math.ceil not floor division
#      20 min on 15m: floor=1 bar (wrong), ceil=2 (correct).
#      Only affects PHASE_MODEL defaults where la_min -- tf_min is fractional.
#      Calibrated values (p75_exit -- tf_min) are always divisible --- unaffected.
#
#
#  14. CRITICAL BUG FIX --- SHORT exit simulation was direction-blind.
#      _simulate_exit_vectorized used lows<=sl / highs>=tp for ALL
#      directions. For SHORT trades:
#        sl is ABOVE entry --- lows<=sl fires on bar 1 every time --- SL_HIT
#        tp is BELOW entry --- highs>=tp fires on bar 1 every time
#      Both conditions hit on bar 1, SL_HIT wins (sl_idx<=tp_idx).
#      Result: 100% of SHORT trades reported as SL_HIT, -1R.
#      This is WHY all bear phases showed 1-3% win rate in outcomes.
#      Fix: pass `is_short` flag; swap lows/highs checks and mfe/mae
#      direction for short trades.
#      --- SHORT trade exit now correctly uses highs>=sl and lows<=tp
#      --- SHORT MFE = max(entry - lows), MAE = min(entry - highs)
#
#  15. PHASE_TO_ML: POST_IMPULSE_DIGESTION --- NEUTRAL
#      Data: 2.3% win rate on 1m, 11% on 3m, 23% on 5m even after fix.
#      Entry too late into move. ML should not trade this label.
#      Outcome rows still generated --- ML trains to skip.
#
#  16. PHASE_TO_ML: ABSORPTION --- NEUTRAL
#      Data: 5-28% win rate across TFs (worst on 1m).
#      Absorption is a context/confirmation signal, not an entry signal.
#      Direction is unknowable without multi-TF context at bar level.
#
#  17. PHASE_TO_ML: DISTRIBUTION --- NEUTRAL
#      Data: 2-4% win rate. Distribution labels fire in bull-trending
#      markets where shorts fail. Context signal, not entry signal.
#
#  18. calc_strategy_outcomes: macro_regime execution gate
#      Skip LONG trades when macro_regime == "BEAR_MACRO".
#      Skip SHORT trades when macro_regime == "BULL_MACRO".
#      Market context columns (macro_regime, price_structure,
#      trend_exhaustion) now pulled from market_context in the main query.
#
#  19. calc_strategy_outcomes: price_structure alignment gate
#      TREND_CONTINUATION / BEAR_TREND_CONTINUATION require
#      price_structure alignment (BULL for long, BEAR for short,
#      NEUTRAL allowed). TRANSITION / opposing structure = skip.
#
#  20. calc_strategy_outcomes: trend_exhaustion gate
#      Skip TREND_CONTINUATION and BEAR_TREND_CONTINUATION when
#      trend_exhaustion == 1 (MACD histogram shrinking + RSI extreme).
#      Prevents entering late into exhausted trends.
#
#  21. State machine: macro_regime gate on bear trend propagation
#      BEAR_TREND_CONTINUATION/ACCEPTANCE: if macro_regime is BULL_MACRO
#      and bear signal fires, label as BALANCE_CHOP instead.
#      Prevents systematic short labelling in bull-trending days.
#
#  22. State machine: COMPRESSION requires min 2 consecutive bars.
#      Single-bar compression squeezes are noise --- real compression
#      builds over multiple bars. Counter tracks streak; label only
#      assigned after 2+ consecutive compression bars.
#      --- eliminates ~30% of false compression signals on 1m.
#
#  DB migration required before running label-market-context / calc-strategy-outcomes:
#
#    -- Bug 4: vwap_dist_atr column
#    ALTER TABLE market_context
#        ADD COLUMN IF NOT EXISTS vwap_dist_atr FLOAT;
#
#    -- Bug 5: impulse_dir column
#    ALTER TABLE market_context
#        ADD COLUMN IF NOT EXISTS impulse_dir TEXT;
#
#    -- existing cost columns
#    ALTER TABLE strategy_outcomes
#        ADD COLUMN IF NOT EXISTS realized_r_gross FLOAT,
#        ADD COLUMN IF NOT EXISTS cost_r           FLOAT;
# ================================================================
import json, traceback, time, math
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from flask import Blueprint, request, jsonify
from psycopg2.extras import execute_values

from db import get_db_conn


# ------ Safe DB query helper ---------------------------------------------------------------------------------------------------------------------------
def read_sql_safe(sql, conn, params=None):
    """
    Replaces pd.read_sql for raw psycopg2 RealDictCursor connections.
    pd.read_sql with psycopg2 returns column names as data values.
    RealDictCursor returns dict rows --- pd.DataFrame handles them natively.
    Also converts Decimal --- float and None --- NaN.
    """
    import decimal

    with conn.cursor() as cur:
        cur.execute(sql, params or [])
        rows = cur.fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([dict(r) for r in rows])
    for col in df.columns:
        first_valid = next((v for v in df[col] if v is not None), None)
        if isinstance(first_valid, (decimal.Decimal, int, float)):
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _chunk_execute(cur, sql, rows, chunk_size=5000):
    """Batch execute_values in chunks to avoid memory spikes."""
    def _to_db_scalar(v):
        # psycopg2 does not reliably adapt numpy scalar types (numpy>=2 can
        # render repr like np.float64(...)), so normalize to native Python.
        if isinstance(v, np.generic):
            v = v.item()
        # Normalize NaN/Inf to NULL for safer inserts across numeric columns.
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        return v

    for i in range(0, len(rows), chunk_size):
        chunk = rows[i : i + chunk_size]
        safe_chunk = [tuple(_to_db_scalar(v) for v in row) for row in chunk]
        execute_values(cur, sql, safe_chunk)


def json_safe(v):
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except Exception:
        return None

# Transaction cost model (NSE intraday) -------------------------------------
# All percentage rates apply to trade value (entry price -- qty).
# Slippage is in absolute points --- applied on entry AND exit separately.
#
# Round-trip cost breakdown:
#   Brokerage     : 0.03% -- 2 sides          = 0.0600%
#   STT           : 0.025% on sell side only  = 0.0250%
#   Exchange fees : ~0.00335% -- 2 sides       = 0.0067%  ------
#   SEBI turnover : ~0.0001%  -- 2 sides       = 0.0002%   --- combined as
#   Stamp duty    : ~0.003%   buy side only   = 0.0030%   --- TAX_CHARGES_PCT
#   GST on fees   : ~0.018%   on brokerage    = 0.0108%  ------
#   ---------------------------------------------------------------------------------------------------------------------------------------------------------------
#   TOTAL_COST_PCT                            --- 0.1507% --- 0.00150 per trade
#
# Slippage: 1 tick (---0.05) on entry, 1 tick on TP exit.
# SL exits are assumed to fill exactly at SL (market order, worst case).
#
# cost_r = how many R the round-trip costs consume, regardless of outcome.
# Example: entry=---130, ATR=---0.35, SL=0.6 ATR --- R=---0.21
#   cost_pts = 130 -- 0.00150 = ---0.195
#   cost_r   = 0.195 / 0.21  = 0.93R   --- nearly 1R just in costs
# This correctly penalises tight-stop trades on low-ATR stocks.


# ------ Swing detection --- price structure ------------------------------------------------------------------------------------
def _compute_price_structure(
    highs: np.ndarray, lows: np.ndarray, i: int, n: int = 3
) -> str:
    """
    Lookback-only swing detection --- no future bars used.
    v28 FIX: Window widened from 4--n to 8--n bars back.

    Root cause of the old bug: with SWING_N=2 (15m TF config), the old
    4--n=8-bar window gave only 5 candidate positions for swing detection,
    making it nearly impossible to find 2 confirmed swing highs AND 2
    swing lows --- resulting in 99.9% NEUTRAL and disabling the price_structure
    alignment gate (fix 19) entirely.

    New 8--n window = 17 bars (255 min on 15m) provides enough structure
    to reliably identify HH/HL (BULL) or LL/LH (BEAR) swing sequences.

    Returns: BULL / BEAR / TRANSITION / NEUTRAL
    """
    if i < 2 * n:
        return "NEUTRAL"
    # v28: widened from 4*n to 8*n for reliable swing detection
    window = slice(max(0, i - 8 * n), i + 1)
    h = highs[window]
    l = lows[window]
    sh, sl = [], []
    for j in range(n, len(h) - n):
        if h[j] == h[j - n : j + n + 1].max():
            sh.append(h[j])
        if l[j] == l[j - n : j + n + 1].min():
            sl.append(l[j])
    if len(sh) < 2 or len(sl) < 2:
        return "NEUTRAL"
    hh = sh[-1] > sh[-2]
    hl = sl[-1] > sl[-2]
    ll = sl[-1] < sl[-2]
    lh = sh[-1] < sh[-2]
    if hh and hl:
        return "BULL"
    if ll and lh:
        return "BEAR"
    if (hh and ll) or (lh and hl):
        return "TRANSITION"
    return "NEUTRAL"


def _compute_session_type(
    orb_range: float, prev_atr: float, open_drive: float, orb_break_early: bool
) -> str:
    """
    Classifies session by bar ~15 using orb_range and open drive.
    orb_range     : orb_high - orb_low
    prev_atr      : yesterday's ATR (available as prev_day_atr)
    open_drive    : abs(close_bar5 - open_bar0) / prev_atr
    orb_break_early: orb_breakout fired before bar 10
    """
    if prev_atr <= 0:
        return "NORMAL_DAY"
    ib_ratio = orb_range / prev_atr
    if ib_ratio < 0.5 and open_drive > 0.3 and orb_break_early:
        return "TREND_DAY"
    if ib_ratio > 1.3:
        return "VOLATILE_DAY"
    return "NORMAL_DAY"


def _compute_macro_regime(close: float, ema_200: float, atr_pct: float = 0.01) -> str:
    """
    Symbol-adaptive macro regime from close vs EMA-200.

    FIX: The original --1% threshold was hardcoded and wrong for most symbols:
      - High-volatility symbols (TATASTEEL: ~3% daily ATR/price) --- 1% fires
        BULL_MACRO on almost every bar, making the gate useless.
      - Low-volatility symbols (HDFCBANK: ~0.8% daily ATR/price) --- price rarely
        moves 1% from EMA-200, so macro stays NEUTRAL_MACRO almost always.

    Fix: Use the symbol's own ATR-pct (atr_14 / close) as the threshold.
    A symbol needs to be at least 0.5-- its own daily ATR away from EMA-200
    before it's classified as in a macro trend. This self-calibrates:
      TATASTEEL ATR ~3% --- threshold ~1.5% --- only genuine multi-day trends fire
      HDFCBANK  ATR ~0.8% --- threshold ~0.4% --- minor trends still register

    atr_pct: atr_14 / close for the current bar (passed from the caller).
             Defaults to 0.01 (old behaviour) as a safe fallback.
    """
    if pd.isna(ema_200) or ema_200 <= 0:
        return "NEUTRAL_MACRO"
    dist = (close - ema_200) / ema_200
    # Adaptive threshold: 0.5-- the symbol's current ATR-pct, floor 0.003, cap 0.025
    # Floor prevents threshold from collapsing to zero on low-ATR bars.
    # Cap prevents threshold from being so wide that macro never fires.
    threshold = float(np.clip(0.5 * atr_pct, 0.003, 0.025))
    if dist > threshold:
        return "BULL_MACRO"
    if dist < -threshold:
        return "BEAR_MACRO"
    return "NEUTRAL_MACRO"


BROKERAGE_PCT = 0.0003  # 0.03% per side -- 2 = 0.06% round trip
STT_PCT = 0.00025  # Securities Transaction Tax --- sell side only
TAX_CHARGES_PCT = (
    0.00065  # Exchange fees + SEBI turnover + Stamp Duty + GST (both sides)
)
SLIPPAGE_PTS = 0.05  # 1 tick slippage --- applied on entry AND TP exit

# Total percentage cost per round trip (slippage handled separately in points)
TOTAL_COST_PCT = (BROKERAGE_PCT * 2) + STT_PCT + TAX_CHARGES_PCT
# = 0.0006 + 0.00025 + 0.00065 = 0.00150  ---  0.150% per round trip

# FIX 4: Maximum cost_r before a trade is skipped as unviable.
# cost_r = (entry -- TOTAL_COST_PCT) / R.  At cost_r > 0.7, the round-trip cost
# consumes over 70% of 1R --- no realistic accuracy makes this positive EV.
# This threshold naturally eliminates most 1m setups (cost_r --- 1.3---1.5R)
# while leaving 15m setups (cost_r --- 0.25---0.45R) fully untouched.
# Can be overridden per request via the "cost_r_gate" body parameter.
COST_R_MAX_GATE = 0.70


strategy_bp = Blueprint("strategy", __name__)

# ------ Phase consolidation for ML ------------------------------------------------------------------------------------------------------------
# Raw labels give full market narrative detail (useful for analysis).
# ML model uses 7 consolidated groups --- each has a distinct trade implication.
# Too many labels = class imbalance + blurry decision boundaries.
#
#  TREND_UP    --- Long bias, follow price higher
#  TREND_DOWN  --- Short bias, follow price lower
#  IMPULSE     --- Strong momentum, enter on first pullback
#  RANGE       --- Mean-revert, fade edges of range
#  REVERSAL    --- Fade the prevailing move
#  GAP         --- Gap-specific auction strategy
#  NEUTRAL     --- No clear edge, skip

PHASE_TO_ML = {
    # ------ TREND_UP ---------------------------------------------------------------------------------------------------------------------------------------------------
    "TREND_CONTINUATION": "TREND_UP",
    "TREND_ACCEPTANCE": "TREND_UP",
    "TREND_PAUSE": "TREND_UP",
    "TREND_DIGESTION": "TREND_UP",
    # ------ TREND_DOWN ---------------------------------------------------------------------------------------------------------------------------------------------
    "BEAR_TREND_CONTINUATION": "TREND_DOWN",
    "BEAR_TREND_ACCEPTANCE": "TREND_DOWN",
    "BEAR_TREND_PAUSE": "TREND_DOWN",
    "BEAR_TREND_DIGESTION": "TREND_DOWN",
    # ------ IMPULSE UP ---------------------------------------------------------------------------------------------------------------------------------------------
    "IMPULSE_BULL": "IMPULSE_UP",
    "EXPANSION": "IMPULSE_UP",
    "GAP_CONTINUATION": "IMPULSE_UP",
    "GAP_TIMEOUT": "TREND_UP",
    # ------ IMPULSE DOWN ---------------------------------------------------------------------------------------------------------------------------------------
    "IMPULSE_BEAR": "IMPULSE_DOWN",
    # ------ IMPULSE NEUTRAL ------------------------------------------------------------------------------------------------------------------------------
    "IMPULSE_NEUTRAL": "IMPULSE_NEUTRAL",
    # POST_IMPULSE_DIGESTION demoted to NEUTRAL (fix 15):
    # Data shows 2.3% / 11% / 23% win rate on 1m/3m/5m even after
    # SHORT fix. Entry too late --- impulse already exhausted by digestion bar.
    # Outcome rows still generated; ML trains to skip this label.
    "POST_IMPULSE_DIGESTION": "NEUTRAL",
    # ------ RANGE (mean-revert) ------------------------------------------------------------------------------------------------------------------
    "BALANCE_CHOP": "RANGE",
    "COMPRESSION": "RANGE",
    "DIGESTION": "RANGE",
    # ABSORPTION demoted to NEUTRAL (fix 16):
    # Data: 5-28% win rate across TFs (5% on 1m = worst performer).
    # Absorption is a footprint/context signal. Direction requires
    # multi-TF confluence the bar-level state machine cannot provide.
    "ABSORPTION": "NEUTRAL",
    "GAP_AUCTION_CHOP": "RANGE",
    "GAP_FILLED": "RANGE",
    "GAP_OPEN": "RANGE",
    "AUCTION_IMPULSE_NEUTRAL": "RANGE",
    # ------ REVERSAL (fade the move) ---------------------------------------------------------------------------------------------------
    "PULLBACK_FAIL": "REVERSAL",
    "REJECTION": "REVERSAL",
    # DISTRIBUTION demoted to NEUTRAL (fix 17):
    # Data: 2-4% win rate across all TFs. Fires inside bull-trending
    # markets where SHORT bias consistently fails. Context signal only.
    "DISTRIBUTION": "NEUTRAL",
    # ------ GAP UP ---------------------------------------------------------------------------------------------------------------------------------------------------------
    "LARGE_GAP_UP": "GAP_UP",
    "MODERATE_GAP_UP": "GAP_UP",
    # LARGE_GAP_AUCTION_BULL: restored to GAP_UP (fix 3).
    # Original demotion to NEUTRAL was based on 1m data (29% WR, 61 samples)
    # which was poisoned by the SHORT exit bug. Clean data shows:
    #   3m: 57.5% win rate, p50 MFE=1.40R, p75 MFE=2.28R (40 samples)
    #   5m: 40.0% win rate, p50 MFE=1.00R, p75 MFE=1.84R (30 samples)
    # Real edge exists --- map to GAP_UP so ML can act on it.
    # 1m still questionable (sample-limited) but consistent with GAP_UP.
    "LARGE_GAP_AUCTION_BULL": "GAP_UP",
    "MODERATE_GAP_AUCTION_BULL": "GAP_UP",
    "AUCTION_IMPULSE_UP": "GAP_UP",
    # ------ GAP DOWN ---------------------------------------------------------------------------------------------------------------------------------------------------
    "LARGE_GAP_DOWN": "GAP_DOWN",
    "MODERATE_GAP_DOWN": "GAP_DOWN",
    # LARGE_GAP_AUCTION_BEAR: restored symmetrically with BULL.
    # After SHORT exit fix, bear auction data will be clean on next run.
    # Map to GAP_DOWN so ML sees both sides consistently.
    "LARGE_GAP_AUCTION_BEAR": "GAP_DOWN",
    "MODERATE_GAP_AUCTION_BEAR": "GAP_DOWN",
    "AUCTION_IMPULSE_DOWN": "GAP_DOWN",
    # ------ NEUTRAL (no edge --- skip) ------------------------------------------------------------------------------------------------------
    "UNCLASSIFIED": "NEUTRAL",
}


def get_ml_label(market_phase: str) -> str:
    """Map raw market phase to consolidated ML label."""
    return PHASE_TO_ML.get(market_phase, "NEUTRAL")


PHASE_MODEL = {
    # ================================================================
    #  PHASE_MODEL --- TF-AWARE, COST-VIABLE  (v28 recalibrated)
    # ================================================================
    #  Design principles:
    #
    #  1. LOOKAHEAD is in MINUTES not bars. The endpoint converts to
    #     bars at runtime using tf_min. This ensures the same phase
    #     measures the same market time on every timeframe.
    #     Key: lookahead_bars = max(2, ceil(lookahead_min / tf_min))
    #
    #  2. TP and SL are in ATR multiples. ATR already scales with TF ---
    #     a 1m ATR is ~5x smaller than a 15m ATR so --- distance is
    #     self-calibrating. No TF-specific overrides needed.
    #
    #  3. Cost-viability floor for 15m (TATASTEEL ~---150, ATR ~---0.83):
    #     cost_r = (entry -- 0.0015) / (sl -- ATR)
    #     Minimum sl --- 0.40 to keep cost_r below gate (0.70).
    #     Net R:R = tp/sl --- cost_r. Must be --- +0.5R per TP hit.
    #     Minimum viable tp/sl --- 1.5 once cost_r --- 0.27---0.54.
    #
    #  4. v28 TP calibration: TPs set at MFE p50 (median achievable move)
    #     not p75+. Previous p75 targets caused TP hit rate of 11---25%;
    #     p50 targets raise TP rate to ~45---55% improving WR-driven expectancy.
    #
    #  5. NEUTRAL dir phases generate outcome rows (ML training signal)
    #     but are skipped by the live execution engine.
    #
    #  6. lookahead_min: calibrated to p75 of actual exit_after_candles -- tf_min.
    #     Trend: 45---60 min. Impulse/gap: 15---30 min. Range: 20---30 min.
    # ================================================================
    # ------ Impulse phases ------------------------------------------------------------------------------------------------------------------------------------------
    # v28: TP reduced 1.8---1.0 (MFE p50 --- 0.82R). SL kept at 0.8 to
    # maintain cost_r --- 0.34 (well below 0.70 gate). R:R 1.25:1 gross,
    # net --- +0.91R per TP hit. Needs WR > 52% --- impulse p40 MFE achieves this.
    "IMPULSE_BULL": {
        "dir": "LONG",
        "tp": 1.0,
        "sl": 0.8,
        "lookahead_min": 15,
    },
    "IMPULSE_BEAR": {
        "dir": "SHORT",
        "tp": 1.0,
        "sl": 0.8,
        "lookahead_min": 15,
    },
    "IMPULSE_NEUTRAL": {
        "dir": "MEAN",
        "tp": 0.8,
        "sl": 0.7,
        "lookahead_min": 15,
        # Direction unknown --- outcome used for training classification only.
    },
    # v28: EXPANSION TP reduced 1.5---1.0, lookahead trimmed 20---15 min.
    # Exit p75 = 2 bars on 15m --- 30 min already wide. 15 min is correct.
    "EXPANSION": {
        "dir": "FOLLOW",
        "tp": 1.0,
        "sl": 0.8,
        "lookahead_min": 15,
    },
    # v28: POST_IMPULSE_DIGESTION TP reduced 1.0---0.6, SL tightened 0.7---0.5.
    # MFE p50 = 0.60R; MAE p75 = 0.28R. Still generates outcome rows for ML.
    "POST_IMPULSE_DIGESTION": {
        "dir": "FOLLOW",
        "tp": 0.6,
        "sl": 0.5,
        "lookahead_min": 15,
    },
    # ------ Trend phases --- bull ---------------------------------------------------------------------------------------------------------------------------
    # v28: TP reduced from 1.8/1.5 to 1.0 across all trend phases.
    # MFE p50 for trend phases = 0.57---0.71R. Previous TP at 1.5---1.8 only
    # hit 22---28% of the time. New TP at 1.0 targets ~45% TP rate.
    # SL kept at 1.0 to keep cost_r --- 0.27 (safest margin below gate).
    # Lookahead reduced: exit p75 data shows 3---4 bars (45---60 min) not 75 min.
    "TREND_CONTINUATION": {
        "dir": "LONG",
        "tp": 1.0,
        "sl": 1.0,
        "lookahead_min": 45,
        # R:R gross 1.0:1. Net: 1.0 --- 0.27 = +0.73R TP / ---1.27R SL.
        # Breakeven WR = 63.5%. volume_expansion filter needed to achieve this.
    },
    "TREND_ACCEPTANCE": {
        "dir": "LONG",
        "tp": 1.0,
        "sl": 1.0,
        "lookahead_min": 45,
        # Acceptance MFE p50 = 0.57R. Same params as CONTINUATION for symmetry.
    },
    "TREND_PAUSE": {
        "dir": "LONG",
        "tp": 0.9,
        "sl": 0.8,
        "lookahead_min": 30,
    },
    "TREND_DIGESTION": {
        "dir": "LONG",
        "tp": 0.7,
        "sl": 0.6,
        "lookahead_min": 20,
        # MFE p50 = 0.38R. Tight TP/SL to capture the small digestion bounce.
    },
    # ------ Trend phases --- bear (mirrors of bull) ---------------------------------------------------------------------
    # v28: Same recalibration logic as bull trend phases.
    "BEAR_TREND_CONTINUATION": {
        "dir": "SHORT",
        "tp": 1.0,
        "sl": 1.0,
        "lookahead_min": 45,
    },
    "BEAR_TREND_ACCEPTANCE": {
        "dir": "SHORT",
        "tp": 1.0,
        "sl": 1.0,
        "lookahead_min": 45,
        # MFE p50 = 0.81R --- slightly better than bull acceptance.
    },
    "BEAR_TREND_PAUSE": {
        "dir": "SHORT",
        "tp": 0.9,
        "sl": 0.8,
        "lookahead_min": 30,
    },
    "BEAR_TREND_DIGESTION": {
        "dir": "SHORT",
        "tp": 0.7,
        "sl": 0.6,
        "lookahead_min": 20,
        # v28: MFE p50 = 0.70R; MAE p75 = 0.16R --- tight params viable.
    },
    # ------ Range and balance phases ------------------------------------------------------------------------------------------------------------
    "BALANCE_CHOP": {
        "dir": "NEUTRAL",
        "tp": 1.0,
        "sl": 0.8,
        "lookahead_min": 30,
        # No directional trade. Outcome recorded so ML learns to skip.
    },
    # v28: COMPRESSION TP reduced 1.5---0.8. dir=BREAKOUT resolves via EMA
    # slope --- produces ~50% directional accuracy --- R:R must carry the load.
    # MFE p50 = 0.61R. tp=0.8, sl=0.7 gives R:R 1.14:1 gross, net --- +0.54R.
    "COMPRESSION": {
        "dir": "BREAKOUT",
        "tp": 0.8,
        "sl": 0.7,
        "lookahead_min": 30,
    },
    "DIGESTION": {
        "dir": "MEAN",
        "tp": 0.8,
        "sl": 0.7,
        "lookahead_min": 20,
    },
    # ------ Gap open phases (bar_of_day == 0) ---------------------------------------------------------------------------------
    # v28: LARGE_GAP_UP direction flipped LONG --- SHORT (fade).
    # 490-day data shows LARGE_GAP_UP as LONG: WR=28%, TP%=12.6%.
    # SL hit rate 50.5% = price falls ---1R from entry in 30 min.
    # As SHORT (fade): those SL hits --- TP hits. Expected WR ~55-60%.
    # TP set at 0.8 (MFE p50 after direction flip --- 0.85R). SL=0.7.
    "LARGE_GAP_UP": {
        "dir": "SHORT",
        "tp": 0.8,
        "sl": 0.7,
        "lookahead_min": 30,
        # Fade the gap up: 15m large gaps reverse in first 30 min ~55% of time.
        # v28 DIRECTION FLIP from LONG. Re-run outcomes to measure clean data.
    },
    # LARGE_GAP_DOWN: keep SHORT (continuation works --- WR=39.5%, TP%=34.9%).
    # v28: TP reduced 2.0---1.0 (MFE p50 = 0.83R, p75 = 2.16R).
    "LARGE_GAP_DOWN": {
        "dir": "SHORT",
        "tp": 1.0,
        "sl": 0.8,
        "lookahead_min": 30,
    },
    # MODERATE_GAP_UP: fade works --- MFE p50 = 1.13R (best in dataset).
    # v28: TP raised 1.2---1.1 to target MFE p50. SL tightened 0.7---0.5.
    # cost_r at sl=0.5: ~0.54. R:R gross = 1.1/0.5 = 2.2:1. Net = +1.66R TP.
    # Breakeven WR = 44.9%. Expected WR ~60% --- E[R] --- +0.15R. Best phase.
    "MODERATE_GAP_UP": {
        "dir": "SHORT",
        "tp": 1.1,
        "sl": 0.5,
        "lookahead_min": 30,
        # v28: SL tightened 0.7---0.5. MAE p75 = 0.22R --- tight stop survives 75%.
    },
    # v28: MODERATE_GAP_DOWN direction flipped LONG --- SHORT (continuation).
    # As LONG (fade): WR=25%, SL%=75%, MAE p50=-1.75R --- price keeps falling.
    # As SHORT (follow): old MAE becomes MFE. MFE p50 --- 1.75R is exceptional.
    # tp=1.0, sl=0.5 --- R:R gross 2.0:1. Net --- +1.46R per TP hit.
    # Breakeven WR = 51.3%. Expected WR ~60% --- E[R] --- +0.26R.
    "MODERATE_GAP_DOWN": {
        "dir": "SHORT",
        "tp": 1.0,
        "sl": 0.5,
        "lookahead_min": 30,
        # v28 DIRECTION FLIP from LONG. Re-run outcomes to verify clean data.
    },
    # ------ Gap auction phases ------------------------------------------------------------------------------------------------------------------------------
    # Kept in PHASE_MODEL so outcome rows are generated for ML training.
    # v28: TPs slightly reduced to match MFE p50.
    "LARGE_GAP_AUCTION_BULL": {
        "dir": "LONG",
        "tp": 1.2,
        "sl": 1.0,
        "lookahead_min": 20,
    },
    "LARGE_GAP_AUCTION_BEAR": {
        "dir": "SHORT",
        "tp": 1.2,
        "sl": 1.0,
        "lookahead_min": 20,
    },
    "MODERATE_GAP_AUCTION_BULL": {
        "dir": "LONG",
        "tp": 1.0,
        "sl": 0.7,
        "lookahead_min": 20,
    },
    "MODERATE_GAP_AUCTION_BEAR": {
        "dir": "SHORT",
        "tp": 1.0,
        "sl": 0.7,
        "lookahead_min": 20,
    },
    # v28: GAP_AUCTION_CHOP TP reduced 1.0---0.5. MFE p50=0.64R but MEAN
    # direction resolves via VWAP distance, producing ~50% accuracy.
    # Lower TP improves hit rate. sl kept at 0.6 (cost_r viability floor).
    "GAP_AUCTION_CHOP": {
        "dir": "MEAN",
        "tp": 0.5,
        "sl": 0.6,
        "lookahead_min": 15,
    },
    # ------ Gap resolution ------------------------------------------------------------------------------------------------------------------------------------------
    "GAP_FILLED": {
        "dir": "MEAN",
        "tp": 0.7,
        "sl": 0.6,
        "lookahead_min": 20,
    },
    # v28: GAP_TIMEOUT demoted dir FOLLOW---NEUTRAL.
    # TP hit rate was only 10.9% --- FOLLOW direction is wrong after timeout.
    # Gap timeout on 15m resolves into balance/chop, not continuation.
    # Outcome rows retained so ML learns to skip.
    "GAP_TIMEOUT": {
        "dir": "NEUTRAL",
        "tp": 1.0,
        "sl": 0.8,
        "lookahead_min": 30,
        # v28: was FOLLOW. Demoted to NEUTRAL --- 10.9% TP rate is not recoverable.
    },
    # v28: GAP_CONTINUATION TP reduced 2.0---0.8 (MFE p50=0.49R).
    # FOLLOW resolves correctly (gap_atr direction) but price rarely extends
    # 2R more after an already-large gap move. Realistic p50 target restores
    # meaningful outcome data for ML.
    "GAP_CONTINUATION": {
        "dir": "FOLLOW",
        "tp": 0.8,
        "sl": 0.7,
        "lookahead_min": 30,
    },
    "GAP_OPEN": {
        "dir": "MEAN",
        "tp": 0.8,
        "sl": 0.7,
        "lookahead_min": 15,
    },
    # ------ Reversal / structural phases ------------------------------------------------------------------------------------------------
    # v28: PULLBACK_FAIL demoted dir FADE---NEUTRAL.
    # TP hit rate was 3.2% --- FADE direction almost never works on 15m.
    # Outcome rows retained (realized_r will be strongly negative --- ML learns skip).
    "PULLBACK_FAIL": {
        "dir": "NEUTRAL",
        "tp": 1.2,
        "sl": 0.8,
        "lookahead_min": 20,
        # v28: was FADE. 3.2% TP rate --- demoted to NEUTRAL.
    },
    # v28: REJECTION demoted dir FADE---NEUTRAL.
    # TP hit rate was 9.3%. FADE on rejection bar requires multi-TF confluence
    # the bar-level state machine cannot provide at 15m granularity.
    "REJECTION": {
        "dir": "NEUTRAL",
        "tp": 1.2,
        "sl": 0.8,
        "lookahead_min": 20,
        # v28: was FADE. 9.3% TP rate --- demoted to NEUTRAL.
    },
    # v28: ABSORPTION demoted dir FOLLOW---NEUTRAL.
    # TP hit rate was 22.9%. FOLLOW requires knowing accumulated direction
    # (footprint/orderflow context) unavailable at bar-level state machine.
    "ABSORPTION": {
        "dir": "NEUTRAL",
        "tp": 1.2,
        "sl": 0.8,
        "lookahead_min": 30,
        # v28: was FOLLOW. 22.9% TP rate --- demoted to NEUTRAL.
    },
    # v28: DISTRIBUTION demoted dir SHORT---NEUTRAL.
    # TP hit rate was 17%. Fires in bull-trending markets where shorts fail.
    # Already NEUTRAL in PHASE_TO_ML --- now consistent in PHASE_MODEL too.
    "DISTRIBUTION": {
        "dir": "NEUTRAL",
        "tp": 1.2,
        "sl": 0.8,
        "lookahead_min": 30,
        # v28: was SHORT. 17% TP rate --- demoted to NEUTRAL.
    },
}


# ------ IMPROVEMENT 4: vectorized exit simulation ------------------------------------------------------------
def _simulate_exit_vectorized(
    entry: float,
    tp: float,
    sl: float,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    n: int,
    is_short: bool = False,
):
    """
    Direction-aware exit simulation.

    FIX 14 (critical): The original code used lows<=sl / highs>=tp for ALL
    directions. For SHORT trades this is catastrophically wrong:
      - sl is ABOVE entry  --- lows<=sl fires on bar 1 every time --- SL_HIT
      - tp is BELOW entry  --- highs>=tp also fires bar 1 trivially
    Result: 100% of SHORT trades reported SL_HIT, -1R.
    This inflated bear phase failure rates to 97-99% in the outcome data.

    LONG  trade: TP hit when highs >= tp (above entry)
                 SL hit when lows  <= sl (below entry)
                 MFE = max(highs - entry), MAE = min(lows - entry)

    SHORT trade: TP hit when lows  <= tp (below entry, price drops to target)
                 SL hit when highs >= sl (above entry, price rises to stop)
                 MFE = max(entry - lows),  MAE = min(entry - highs)
    """
    if n <= 0:
        return "TIME_EXIT", entry, 0, 0.0, 0.0

    if is_short:
        # Favorable: price drops below entry
        mfe = np.maximum.accumulate(entry - lows[:n])
        mae = np.minimum.accumulate(entry - highs[:n])
        sl_hits = np.where(highs[:n] >= sl)[0]  # stop: price rises to sl
        tp_hits = np.where(lows[:n] <= tp)[0]  # target: price drops to tp
    else:
        # Favorable: price rises above entry
        mfe = np.maximum.accumulate(highs[:n] - entry)
        mae = np.minimum.accumulate(lows[:n] - entry)
        sl_hits = np.where(lows[:n] <= sl)[0]  # stop: price drops to sl
        tp_hits = np.where(highs[:n] >= tp)[0]  # target: price rises to tp

    sl_idx = sl_hits[0] if len(sl_hits) else n
    tp_idx = tp_hits[0] if len(tp_hits) else n

    if sl_idx == n and tp_idx == n:
        return "TIME_EXIT", closes[n - 1], n, float(mfe[-1]), float(mae[-1])
    if sl_idx <= tp_idx:
        return "SL_HIT", sl, sl_idx + 1, float(mfe[sl_idx]), float(mae[sl_idx])
    return "TP_HIT", tp, tp_idx + 1, float(mfe[tp_idx]), float(mae[tp_idx])


# ------ IMPROVEMENT 1: numpy-based state machine ---------------------------------------------------------------
# Phases allowed to propagate via one-bar hysteresis in the fallback path.
# Intentionally restricted to directional digestion/acceptance labels ---
# event-completion phases (REJECTION, GAP_TIMEOUT, ABSORPTION, EXPANSION etc.)
# should never self-propagate into the next bar.
# Data: ABSORPTION(77), DISTRIBUTION(72), REJECTION(47), GAP_TIMEOUT(40),
#       GAP_CONTINUATION(32), GAP_FILLED(31), EXPANSION(30), COMPRESSION(13)
# were all propagating via old hysteresis --- stale labels after event completion.
_HYSTERESIS_ALLOWED = frozenset(
    {
        "TREND_DIGESTION",
        "BEAR_TREND_DIGESTION",
        "TREND_ACCEPTANCE",
        "BEAR_TREND_ACCEPTANCE",
        "TREND_CONTINUATION",
        "BEAR_TREND_CONTINUATION",
        "TREND_PAUSE",
        "BEAR_TREND_PAUSE",
        "POST_IMPULSE_DIGESTION",
    }
)


def _run_state_machine(
    df,
    # ------ Impulse signals ------------------------------------------------------------------------------------------------------------------------------------------------------------------
    bullish_impulse,
    bearish_impulse,
    neutral_impulse,
    # ------ Bull trend indicators ------------------------------------------------------------------------------------------------------------------------------------------------
    trend_valid,
    trend_digestion,
    trend_pause,
    trend_acceptance,
    # ------ Bear trend indicators ------------------------------------------------------------------------------------------------------------------------------------------------
    bear_trend_valid,
    bear_trend_digestion,
    bear_trend_pause,
    bear_trend_acceptance,
    # ------ Structure indicators ---------------------------------------------------------------------------------------------------------------------------------------------------
    compression,
    balance_chop,
    absorption,
    distribution,
    absorption_break,
    distribution_break,
    # ------ Volume baseline ------------------------------------------------------------------------------------------------------------------------------------------------------------------
    vol_ma20,
    # ------ Gap timing config ------------------------------------------------------------------------------------------------------------------------------------------------------------
    GAP_AUCTION_MAX_BARS: dict,
    # ------ Swing / OBV windows ------------------------------------------------------------------------------------------------------------------------------------------------------
    swing_n: int = 3,
    obv_window: int = 10,
    roll_20: int = 20,
    # ------ Absorption / distribution controls ---------------------------------------------------------------------------------------------------------
    absorption_vol_thr: float = 1.1,  # vol_ratio floor for genuine absorption
    absorption_max_streak: int = 6,  # max consecutive absorption bars
    distribution_max_streak: int = 5,  # max consecutive distribution bars
    # ------ Post-impulse controls ------------------------------------------------------------------------------------------------------------------------------------------------
    pullback_min_bars: int = 2,  # adverse bars before PULLBACK_FAIL fires
    # ------ Trend context decay ------------------------------------------------------------------------------------------------------------------------------------------------------
    trend_context_decay: int = 20,  # bars without signal --- context resets
    # ------ No-man's-land RE floors (P3a / P3b) ---------------------------------------------------------------------------------------------------
    nml_re_stack: float = 0.15,  # EMA-stack path minimum RE
    nml_re_slope: float = 0.08,  # slope-only path minimum RE
    nml_slope_thr: float = 0.005,  # EMA slope threshold for stack path
    nml_slope_obv: float = 0.002,  # slope threshold for OBV rescue path
    # ------ P3c (post-neutral-impulse) ---------------------------------------------------------------------------------------------------------------------------------
    p3c_slope_thr: float = 0.003,  # slope threshold to route bull/bear
    p3c_re_min: float = 0.25,  # RE floor for digestion fallback
    # ------ REJECTION gate (NEUTRAL direction) ---------------------------------------------------------------------------------------------------------
    rejection_re_max: float = 0.20,  # max RE for neutral rejection
    # ------ Volume-fade exhaustion (P3a) ---------------------------------------------------------------------------------------------------------------------------
    vol_fade_ratio: float = 0.80,  # bar-on-bar volume contraction floor
    vol_fade_re_min: float = 0.30,  # min RE for volume-fade label
    # ------ Post-gap routing (P3d) ---------------------------------------------------------------------------------------------------------------------------------------------
    gap_slope_thr: float = 0.015,  # slope threshold for post-gap acceptance
    gap_re_min: float = 0.10,  # RE floor for post-gap acceptance
    # ------ P5 thresholds ------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    p5_ae_re_min: float = 0.40,  # ae==1 branch minimum RE
    p5_ta_re_min: float = 0.30,  # ta_arr branch minimum RE
    p5_re_high: float = 0.60,  # high-RE branch threshold
    p5_re_high_slope: float = 0.015,  # slope required for high-RE branch
    p5_chop_range_atr: float = 0.80,  # OBV rescue raw-range / ATR floor
    p5_fallback_re_min: float = 0.15,  # hysteresis RE floor (dead-market break)
    # ------ Debug mode ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    debug: bool = False,  # if True, returns reason column
):
    """
    State machine v34 --- sole market-phase assigner.

    numpy array access throughout --- O(1) per bar.

    Changes vs v33
    ------------------------------------------
    CLEAN-1  Removed dead parameters: gap_auction_entry, gap_auction_resolved,
             gap_auction_failed. These were passed in but never read. Callers
             must remove them from call sites.

    CLEAN-2  Removed dead variable: is_eod --- computed but never used.

    CLEAN-3  Defined _HYSTERESIS_ALLOWED at module level. Was referenced in P5
             fallback but never defined --- would have raised NameError at runtime.

    CLEAN-4  Hardened df column initialisation: market_phase and session_context
             are initialised from the column if it exists, else from "UNCLASSIFIED"
             / session_context_arr, preventing KeyError on first run.

    CLEAN-5  Exposed 18 previously hard-coded thresholds as keyword parameters
             so callers can tune without editing the function body. Defaults
             reproduce prior behaviour exactly.

    CLEAN-6  Added debug=False flag. When True, a parallel list records the
             priority branch and condition that assigned each label. The list is
             returned as df["_phase_reason"] for inspection during backtesting.

    FIX-1    REJECTION neutral gate: requires close < open AND ps != BULL.
    FIX-2    neut_arr direction rescue: clearly bearish --- IMPULSE_BEAR, clearly
             bullish --- IMPULSE_BULL.
    FIX-3    neut_arr resets trend_context to NEUTRAL (prevents stale context).
    FIX-4    P3c: dedicated IMPULSE_NEUTRAL forward propagation block.
    FIX-5    tv_arr / btv_arr require non-opposing close direction.
    FIX-6    P3a/P3b no-man's-land: OBV gate before BALANCE_CHOP.
    """
    n = len(df)

    # ------ Extract numpy arrays once ---------------------------------------------------------------------------------------------------------------------------------------
    bar_of_day = df["bar_of_day"].to_numpy()
    close_arr = df["close"].to_numpy(dtype=float)
    open_arr = df["open"].to_numpy(dtype=float)
    low_arr = df["low"].to_numpy(dtype=float)
    high_arr = df["high"].to_numpy(dtype=float)
    vol_arr = df["volume"].to_numpy(dtype=float)
    vol_ma20_arr = vol_ma20.to_numpy(dtype=float)
    range_eff_arr = df["range_efficiency"].to_numpy(dtype=float)
    atr_exp_arr = df["atr_expanding"].to_numpy(dtype=int)
    bull_arr = bullish_impulse.to_numpy()
    bear_arr = bearish_impulse.to_numpy()
    neut_arr = neutral_impulse.to_numpy()
    tv_arr = trend_valid.to_numpy()
    td_arr = trend_digestion.to_numpy()
    tp_arr = trend_pause.to_numpy()
    ta_arr = trend_acceptance.to_numpy()
    btv_arr = bear_trend_valid.to_numpy()
    btd_arr = bear_trend_digestion.to_numpy()
    btp_arr = bear_trend_pause.to_numpy()
    bta_arr = bear_trend_acceptance.to_numpy()
    cmp_arr = compression.to_numpy()
    chop_arr = balance_chop.to_numpy()
    ab_arr = absorption.to_numpy()
    dist_arr = distribution.to_numpy()
    ab_brk = absorption_break.to_numpy()
    db_brk = distribution_break.to_numpy()
    ema_slope_arr = df["ema_21_slope"].to_numpy(dtype=float)

    ema9_arr = (
        df["ema_9"].to_numpy(dtype=float) if "ema_9" in df.columns else close_arr.copy()
    )
    ema50_arr = (
        df["ema_50"].to_numpy(dtype=float)
        if "ema_50" in df.columns
        else close_arr.copy()
    )
    vr_arr = (
        df["vol_ratio"].to_numpy(dtype=float)
        if "vol_ratio" in df.columns
        else np.ones(n)
    )
    minute_arr = (
        df["minute_of_day"].to_numpy(dtype=int)
        if "minute_of_day" in df.columns
        else np.zeros(n, dtype=int)
    )
    macd_hist_arr = (
        df["macd_hist"].to_numpy(dtype=float)
        if "macd_hist" in df.columns
        else np.zeros(n)
    )
    macd_expanding = np.zeros(n, dtype=int)
    abs_macd = np.abs(macd_hist_arr)
    macd_expanding[1:] = (abs_macd[1:] > abs_macd[:-1]).astype(int)

    rsi_arr = (
        df["rsi_14"].to_numpy(dtype=float)
        if "rsi_14" in df.columns
        else np.full(n, 50.0)
    )
    _rsi_s = pd.Series(rsi_arr)
    _rsi_win = max(int(obv_window * 45), 100)
    _min_p = max(int(_rsi_win * 0.4), 50)
    rsi_p80_arr = (
        _rsi_s.rolling(_rsi_win, min_periods=_min_p)
        .quantile(0.80)
        .fillna(70)
        .to_numpy()
    )
    rsi_p20_arr = (
        _rsi_s.rolling(_rsi_win, min_periods=_min_p)
        .quantile(0.20)
        .fillna(30)
        .to_numpy()
    )

    obv_arr = df["obv"].to_numpy(dtype=float) if "obv" in df.columns else np.zeros(n)
    obv_slope = np.zeros(n, dtype=float)
    if obv_window < n:
        obv_slope[obv_window:] = obv_arr[obv_window:] - obv_arr[:-obv_window]
    obv_slope_arr = obv_slope

    ema200_arr = (
        df["ema_200"].to_numpy(dtype=float) if "ema_200" in df.columns else np.zeros(n)
    )
    atr14_arr = (
        df["atr_14"].to_numpy(dtype=float)
        if "atr_14" in df.columns
        else np.full(n, 0.003)
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        atr_pct_arr = np.where(close_arr > 0, atr14_arr / close_arr, 0.01)

    prev_atr_arr = (
        df["prev_day_atr"].to_numpy(dtype=float)
        if "prev_day_atr" in df.columns
        else np.ones(n)
    )
    orb_high_arr = (
        df["orb_high"].to_numpy(dtype=float)
        if "orb_high" in df.columns
        else np.zeros(n)
    )
    orb_low_arr = (
        df["orb_low"].to_numpy(dtype=float) if "orb_low" in df.columns else np.zeros(n)
    )
    orb_brk_arr = (
        df["orb_breakout"].to_numpy(dtype=int)
        if "orb_breakout" in df.columns
        else np.zeros(n, dtype=int)
    )

    session_context_arr = df["session_context"].tolist()
    gap_fill_pct_arr = df["gap_fill_pct"].to_numpy(dtype=float)
    gap_atr_arr = df["gap_atr"].to_numpy(dtype=float)
    bar_date_arr = df["date"].tolist()

    _gfp = pd.Series(gap_fill_pct_arr)
    _gfp_p75 = (
        _gfp.rolling(max(roll_20, 5), min_periods=5).quantile(0.75).bfill().fillna(0.80)
    )
    _gfp_p25 = (
        _gfp.rolling(max(roll_20, 5), min_periods=5)
        .quantile(0.25)
        .bfill()
        .fillna(-0.50)
    )
    gap_filled_thr_arr = np.clip(_gfp_p75.to_numpy(), 0.65, 0.95)
    gap_extended_thr_arr = np.clip(_gfp_p25.to_numpy(), -0.80, -0.25)

    # ------ CLEAN-4: Robust column initialisation ---------------------------------------------------------------------------------------------------
    # market_phase and session_context may not exist on the first ever run.
    # Fall back to safe defaults rather than crashing on missing column.
    if "market_phase" in df.columns:
        market_phase = df["market_phase"].tolist()
    else:
        market_phase = ["UNCLASSIFIED"] * n

    if "session_context" in df.columns:
        session_context = df["session_context"].tolist()
    else:
        session_context = list(session_context_arr)  # copy from input arr

    # ------ Mutable output arrays ---------------------------------------------------------------------------------------------------------------------------------------------------
    gap_resolved = np.zeros(n, dtype=int)
    gap_auction_started = np.zeros(n, dtype=int)
    gap_auction_active = np.zeros(n, dtype=int)
    gap_auction_origin = np.zeros(n, dtype=int)
    post_impulse_active = np.zeros(n, dtype=int)
    impulse_dir = [None] * n

    price_structure_arr = ["NEUTRAL"] * n
    session_type_arr = ["NORMAL_DAY"] * n
    macro_regime_arr = ["NEUTRAL_MACRO"] * n
    trend_exhaustion = np.zeros(n, dtype=int)
    current_session_type = "NORMAL_DAY"

    # CLEAN-3: debug reason list --- only populated when debug=True
    phase_reason = [""] * n if debug else None

    impulse_origin_low = np.full(n, np.nan, dtype=float)
    impulse_origin_high = np.full(n, np.nan, dtype=float)

    compression_streak = 0
    trend_context = "NEUTRAL"
    trend_context_bars = 0
    absorption_streak = 0
    distribution_streak = 0
    pullback_bars = 0

    session_open_price = float(open_arr[0]) if n > 0 else 0.0
    session_prev_atr = (
        float(prev_atr_arr[0])
        if (n > 0 and np.isfinite(prev_atr_arr[0]) and prev_atr_arr[0] > 0)
        else 1.0
    )
    orb_break_early_seen = False

    # ------ Debug helper ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    def _dbg(i, reason):
        if debug:
            phase_reason[i] = reason

    # ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    for i in range(1, n):
        today = bar_date_arr[i]
        new_day = today != bar_date_arr[i - 1]

        if new_day:
            compression_streak = 0
            pullback_bars = 0
            absorption_streak = 0
            distribution_streak = 0

        trend_context_bars += 1
        if trend_context_bars >= trend_context_decay:
            trend_context = "NEUTRAL"

        price_structure_arr[i] = _compute_price_structure(high_arr, low_arr, i, swing_n)
        macro_regime_arr[i] = _compute_macro_regime(
            close_arr[i], ema200_arr[i], atr_pct_arr[i]
        )

        if i >= 3:
            macd_shrinking = abs(macd_hist_arr[i]) < abs(macd_hist_arr[i - 1]) and abs(
                macd_hist_arr[i - 1]
            ) < abs(macd_hist_arr[i - 2])
            rsi_extreme = rsi_arr[i] > rsi_p80_arr[i] or rsi_arr[i] < rsi_p20_arr[i]
            slope_mag_now = (abs(ema_slope_arr[i]) + abs(ema_slope_arr[i - 1])) * 0.5
            slope_mag_prev = (
                abs(ema_slope_arr[i - 1]) + abs(ema_slope_arr[i - 2])
            ) * 0.5
            slope_decelerating = slope_mag_now < slope_mag_prev
            trend_exhaustion[i] = int(
                macd_shrinking and rsi_extreme and slope_decelerating
            )
        else:
            trend_exhaustion[i] = 0

        if new_day:
            gap_resolved[i] = 0
            gap_auction_started[i] = 0
            gap_auction_active[i] = 0
            gap_auction_origin[i] = 0
            post_impulse_active[i] = 0
            impulse_dir[i] = None
            impulse_origin_low[i] = np.nan
            impulse_origin_high[i] = np.nan
            session_open_price = float(open_arr[i])
            session_prev_atr = (
                float(prev_atr_arr[i])
                if (np.isfinite(prev_atr_arr[i]) and prev_atr_arr[i] > 0)
                else 1.0
            )
            current_session_type = "NORMAL_DAY"
            orb_break_early_seen = False
        else:
            gap_resolved[i] = gap_resolved[i - 1]
            gap_auction_started[i] = gap_auction_started[i - 1]
            gap_auction_active[i] = gap_auction_active[i - 1]
            gap_auction_origin[i] = gap_auction_origin[i - 1]

        if bar_of_day[i] <= 10 and bool(orb_brk_arr[i]):
            orb_break_early_seen = True
        open_drive = abs(close_arr[i] - session_open_price) / session_prev_atr
        if bar_of_day[i] < 5:
            if open_drive > 0.3 and orb_break_early_seen:
                current_session_type = "TREND_DAY"
        else:
            orb_range = float(orb_high_arr[i]) - float(orb_low_arr[i])
            current_session_type = _compute_session_type(
                orb_range, session_prev_atr, open_drive, orb_break_early_seen
            )
        session_type_arr[i] = current_session_type

        ema_stack_bull = (ema9_arr[i] > ema50_arr[i]) and (
            ema_slope_arr[i] > nml_slope_thr
        )
        ema_stack_bear = (ema9_arr[i] < ema50_arr[i]) and (
            ema_slope_arr[i] < -nml_slope_thr
        )

        # ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        #  ENTRY 1: Gap auction --- opening bar
        # ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        if (
            session_context_arr[i] in ("LARGE_GAP_SESSION", "MODERATE_GAP_SESSION")
            and gap_resolved[i] == 0
            and gap_auction_started[i] == 0
            and bar_of_day[i] == 0
        ):
            gap_auction_started[i] = 1
            gap_auction_active[i] = 1
            gap_auction_origin[i] = bar_of_day[i]
            is_large = session_context_arr[i] == "LARGE_GAP_SESSION"
            if gap_atr_arr[i] > 0:
                market_phase[i] = "LARGE_GAP_UP" if is_large else "MODERATE_GAP_UP"
            elif gap_atr_arr[i] < 0:
                market_phase[i] = "LARGE_GAP_DOWN" if is_large else "MODERATE_GAP_DOWN"
            else:
                market_phase[i] = "GAP_OPEN"
            _dbg(i, "E1:gap_open")
            continue

        # ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        #  ENTRY 2: Gap auction continuation
        # ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        if gap_auction_active[i] == 1 and gap_resolved[i] == 0:
            bars_elapsed = bar_of_day[i] - gap_auction_origin[i]
            is_large = session_context_arr[i] == "LARGE_GAP_SESSION"
            sess_key = session_context_arr[i]
            max_bars = GAP_AUCTION_MAX_BARS.get(
                sess_key, GAP_AUCTION_MAX_BARS.get("MODERATE_GAP_SESSION", 75)
            )
            gap_nearly_filled = gap_fill_pct_arr[i] >= gap_filled_thr_arr[i]
            gap_extended = gap_fill_pct_arr[i] <= gap_extended_thr_arr[i]

            if gap_nearly_filled or bars_elapsed >= max_bars:
                gap_auction_active[i] = 0
                gap_resolved[i] = 1
                session_context[i] = "BALANCE"
                market_phase[i] = "GAP_FILLED" if gap_nearly_filled else "GAP_TIMEOUT"
                _dbg(i, "E2:gap_filled_or_timeout")
            elif gap_extended:
                gap_auction_active[i] = 0
                gap_resolved[i] = 1
                session_context[i] = "BALANCE"
                market_phase[i] = "GAP_CONTINUATION"
                _dbg(i, "E2:gap_continuation")
            else:
                _re_i = range_eff_arr[i]
                if bull_arr[i]:
                    market_phase[i] = (
                        "LARGE_GAP_AUCTION_BULL"
                        if is_large
                        else (
                            "AUCTION_IMPULSE_UP"
                            if _re_i > 0.50
                            else "MODERATE_GAP_AUCTION_BULL"
                        )
                    )
                elif bear_arr[i]:
                    market_phase[i] = (
                        "LARGE_GAP_AUCTION_BEAR"
                        if is_large
                        else (
                            "AUCTION_IMPULSE_DOWN"
                            if _re_i > 0.50
                            else "MODERATE_GAP_AUCTION_BEAR"
                        )
                    )
                elif neut_arr[i]:
                    market_phase[i] = "AUCTION_IMPULSE_NEUTRAL"
                else:
                    market_phase[i] = "GAP_AUCTION_CHOP"
                _dbg(i, "E2:gap_active")
            continue

        if gap_resolved[i] == 1 and market_phase[i] == "UNCLASSIFIED":
            session_context[i] = "BALANCE"

        # ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        #  ENTRY 3: Post-impulse resolver
        # ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        impulse_allowed = gap_auction_active[i] == 0 and not new_day

        if impulse_allowed and bull_arr[i - 1]:
            post_impulse_active[i] = 1
            impulse_dir[i] = "BULL"
            trend_context = "BULL"
            trend_context_bars = 0
            impulse_origin_low[i] = low_arr[i - 1]
            impulse_origin_high[i] = high_arr[i - 1]
        elif impulse_allowed and bear_arr[i - 1]:
            post_impulse_active[i] = 1
            impulse_dir[i] = "BEAR"
            trend_context = "BEAR"
            trend_context_bars = 0
            impulse_origin_low[i] = low_arr[i - 1]
            impulse_origin_high[i] = high_arr[i - 1]
        elif impulse_allowed and neut_arr[i - 1]:
            post_impulse_active[i] = 1
            impulse_dir[i] = "NEUTRAL"
            impulse_origin_low[i] = low_arr[i - 1]
            impulse_origin_high[i] = high_arr[i - 1]
        elif not new_day:
            post_impulse_active[i] = post_impulse_active[i - 1]
            impulse_dir[i] = impulse_dir[i - 1]
            impulse_origin_low[i] = impulse_origin_low[i - 1]
            impulse_origin_high[i] = impulse_origin_high[i - 1]

        if post_impulse_active[i] == 1 and not (
            bull_arr[i] or bear_arr[i] or neut_arr[i]
        ):
            idir = impulse_dir[i]
            re = range_eff_arr[i]
            ae = atr_exp_arr[i]
            ps = price_structure_arr[i]

            _o_lo = (
                impulse_origin_low[i]
                if not np.isnan(impulse_origin_low[i])
                else low_arr[i - 1]
            )
            _o_hi = (
                impulse_origin_high[i]
                if not np.isnan(impulse_origin_high[i])
                else high_arr[i - 1]
            )

            if idir == "BULL":
                pullback_bars = (
                    pullback_bars + 1 if close_arr[i] < close_arr[i - 1] else 0
                )
            elif idir == "BEAR":
                pullback_bars = (
                    pullback_bars + 1 if close_arr[i] > close_arr[i - 1] else 0
                )

            # PULLBACK_FAIL
            if (
                re < 0.25
                and ae == 0
                and pullback_bars >= pullback_min_bars
                and (
                    (idir == "BULL" and close_arr[i] < _o_lo)
                    or (idir == "BEAR" and close_arr[i] > _o_hi)
                )
            ):
                market_phase[i] = "PULLBACK_FAIL"
                post_impulse_active[i] = 0
                pullback_bars = 0
                _dbg(i, "E3:pullback_fail")
                continue

            # ABSORPTION
            if (
                vol_arr[i] > vol_ma20_arr[i]
                and vr_arr[i] >= absorption_vol_thr
                and ae == 0
                and re < 0.35
            ):
                market_phase[i] = "ABSORPTION"
                post_impulse_active[i] = 0
                absorption_streak = 1
                pullback_bars = 0
                _dbg(i, "E3:absorption")
                continue

            # EXPANSION: evaluate high-conviction continuation before rejection.
            if (
                ae == 1
                and re > 0.50
                and (
                    (idir == "BULL" and close_arr[i] > _o_hi)
                    or (idir == "BEAR" and close_arr[i] < _o_lo)
                )
            ):
                market_phase[i] = "EXPANSION"
                post_impulse_active[i] = 0
                pullback_bars = 0
                trend_context = (
                    "BULL"
                    if idir == "BULL"
                    else ("BEAR" if idir == "BEAR" else trend_context)
                )
                trend_context_bars = 0
                _dbg(i, "E3:expansion")
                continue

            # REJECTION: capped by RE to avoid classifying high-conviction
            # momentum bars as rejection.
            if (
                re < rejection_re_max
                and (
                    (
                        (idir == "BULL" and close_arr[i] < low_arr[i - 1])
                        or (idir == "BEAR" and close_arr[i] > high_arr[i - 1])
                    )
                    and pullback_bars >= pullback_min_bars
                )
            ) or (
                idir == "NEUTRAL"
                and re < rejection_re_max
                and close_arr[i] < open_arr[i]
                and ps != "BULL"
            ):
                market_phase[i] = "REJECTION"
                post_impulse_active[i] = 0
                pullback_bars = 0
                _dbg(i, "E3:rejection")
                continue

            if ae == 1 and re > 0.45:
                if close_arr[i] >= open_arr[i]:
                    market_phase[i] = "TREND_CONTINUATION"
                else:
                    market_phase[i] = "TREND_DIGESTION"
                trend_context = "BULL"
                trend_context_bars = 0
            else:
                market_phase[i] = "POST_IMPULSE_DIGESTION"
            _dbg(i, f"E3:continuation_or_digestion(ae={ae},re={re:.2f})")
            continue

        # ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        #  MAIN STATE MACHINE
        # ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        prev = market_phase[i - 1]
        re = range_eff_arr[i]
        ae = atr_exp_arr[i]
        ps = price_structure_arr[i]

        compression_streak = compression_streak + 1 if cmp_arr[i] else 0

        # ------ Priority 1: Impulse detection ------------------------------------------------------------------------------------------------------------
        if bull_arr[i]:
            market_phase[i] = "IMPULSE_BULL"
            trend_context = "BULL"
            trend_context_bars = 0
            pullback_bars = 0
            absorption_streak = 0
            distribution_streak = 0
            _dbg(i, "P1:impulse_bull")

        elif bear_arr[i]:
            market_phase[i] = "IMPULSE_BEAR"
            trend_context = "BEAR"
            trend_context_bars = 0
            pullback_bars = 0
            absorption_streak = 0
            distribution_streak = 0
            _dbg(i, "P1:impulse_bear")

        elif neut_arr[i]:
            # FIX-2: rescue clearly directional bars from IMPULSE_NEUTRAL
            # FIX-3: always reset trend_context so stale context cannot
            #        poison fallback labels on subsequent bars
            _obv_flat = np.isnan(obv_slope_arr[i]) or obv_slope_arr[i] == 0
            _bar_bearish = (
                (
                    close_arr[i] < open_arr[i]
                    and obv_slope_arr[i] <= 0
                    and not bear_arr[i]
                )
                or (
                    close_arr[i] < open_arr[i]
                    and range_eff_arr[i] > 0.60
                    and _obv_flat
                    and not bear_arr[i]
                )
            )
            _bar_bullish = (
                (
                    close_arr[i] > open_arr[i]
                    and obv_slope_arr[i] >= 0
                    and not bull_arr[i]
                )
                or (
                    close_arr[i] > open_arr[i]
                    and range_eff_arr[i] > 0.60
                    and _obv_flat
                    and not bull_arr[i]
                )
            )
            if _bar_bearish:
                market_phase[i] = "IMPULSE_BEAR"
                trend_context = "BEAR"
                _dbg(i, "P1:neut_rescued_bear")
            elif _bar_bullish:
                market_phase[i] = "IMPULSE_BULL"
                trend_context = "BULL"
                _dbg(i, "P1:neut_rescued_bull")
            else:
                market_phase[i] = "IMPULSE_NEUTRAL"
                trend_context = "NEUTRAL"
                _dbg(i, "P1:impulse_neutral")
            trend_context_bars = 0
            absorption_streak = 0
            distribution_streak = 0
            pullback_bars = 0

        # ------ Priority 2: Compression ------------------------------------------------------------------------------------------------------------------------------
        elif cmp_arr[i] and compression_streak >= 3 and trend_context != "NEUTRAL":
            market_phase[i] = "COMPRESSION"
            absorption_streak = 0
            _dbg(i, f"P2:compression(streak={compression_streak})")

        # ------ Priority 3a: Bull trend propagation ------------------------------------------------------------------------------------------
        elif prev in {
            "IMPULSE_BULL",
            "TREND_CONTINUATION",
            "TREND_ACCEPTANCE",
            "TREND_PAUSE",
            "TREND_DIGESTION",
            "EXPANSION",
            "POST_IMPULSE_DIGESTION",
        }:
            if ps == "BEAR":
                market_phase[i] = "BALANCE_CHOP"
                _dbg(i, "P3a:struct_invalidation")

            elif trend_exhaustion[i] and ema_slope_arr[i] < 0.01:
                market_phase[i] = "DISTRIBUTION"
                _dbg(i, "P3a:trend_exhaustion---distribution")

            elif (
                close_arr[i] > high_arr[i - 1]
                and vol_arr[i] < vol_arr[i - 1] * vol_fade_ratio
                and vol_arr[i] < vol_ma20_arr[i]
                and re > vol_fade_re_min
                and ema_slope_arr[i] > 0
            ):
                market_phase[i] = "TREND_DIGESTION"
                trend_context = "BULL"
                trend_context_bars = 0
                _dbg(i, "P3a:vol_fade_on_new_high")

            # FIX-5: require non-bearish close for continuation
            elif tv_arr[i] and close_arr[i] >= open_arr[i]:
                market_phase[i] = "TREND_CONTINUATION"
                trend_context = "BULL"
                trend_context_bars = 0
                _dbg(i, "P3a:tv_continuation")
            elif tv_arr[i] and close_arr[i] < open_arr[i]:
                market_phase[i] = "TREND_DIGESTION"
                trend_context = "BULL"
                trend_context_bars = 0
                _dbg(i, "P3a:tv_demoted_digestion(bearish_close)")

            elif td_arr[i]:
                market_phase[i] = "TREND_DIGESTION"
                trend_context = "BULL"
                trend_context_bars = 0
                _dbg(i, "P3a:td_digestion")
            elif tp_arr[i]:
                market_phase[i] = "TREND_PAUSE"
                trend_context = "BULL"
                trend_context_bars = 0
                _dbg(i, "P3a:tp_pause")
            elif ta_arr[i]:
                market_phase[i] = "TREND_ACCEPTANCE"
                trend_context = "BULL"
                trend_context_bars = 0
                _dbg(i, "P3a:ta_acceptance")
            elif btv_arr[i] and close_arr[i] <= open_arr[i]:
                market_phase[i] = "BEAR_TREND_CONTINUATION"
                trend_context = "BEAR"
                trend_context_bars = 0
                _dbg(i, "P3a:btv_flip_bear")
            elif btv_arr[i] and close_arr[i] > open_arr[i]:
                market_phase[i] = "BEAR_TREND_DIGESTION"
                trend_context = "BEAR"
                trend_context_bars = 0
                _dbg(i, "P3a:btv_flip_demoted_digestion(bullish_close)")
            elif dist_arr[i] and ema_slope_arr[i] < 0.01:
                market_phase[i] = "DISTRIBUTION"
                _dbg(i, "P3a:dist_arr")
            elif ab_arr[i] and vr_arr[i] >= absorption_vol_thr:
                market_phase[i] = "ABSORPTION"
                absorption_streak += 1
                _dbg(i, "P3a:absorption")
            else:
                # FIX-6: OBV gate before BALANCE_CHOP
                if ema_stack_bull and re > nml_re_stack:
                    market_phase[i] = "TREND_DIGESTION"
                    _dbg(i, "P3a:nml_ema_stack")
                elif ema_slope_arr[i] > nml_slope_thr and re > nml_re_slope:
                    market_phase[i] = "TREND_DIGESTION"
                    _dbg(i, "P3a:nml_slope")
                elif obv_slope_arr[i] > 0 and ema_slope_arr[i] > nml_slope_obv:
                    market_phase[i] = "TREND_DIGESTION"
                    _dbg(i, "P3a:nml_obv_rescue")
                else:
                    market_phase[i] = "BALANCE_CHOP"
                    _dbg(i, "P3a:nml_chop")

        # ------ Priority 3b: Bear trend propagation ------------------------------------------------------------------------------------------
        elif prev in {
            "IMPULSE_BEAR",
            "BEAR_TREND_CONTINUATION",
            "BEAR_TREND_ACCEPTANCE",
            "BEAR_TREND_PAUSE",
            "BEAR_TREND_DIGESTION",
        }:
            if ps == "BULL":
                market_phase[i] = "BALANCE_CHOP"
                _dbg(i, "P3b:struct_invalidation")

            elif macro_regime_arr[i] == "BULL_MACRO" and ema_slope_arr[i] >= -0.01:
                market_phase[i] = "BALANCE_CHOP"
                _dbg(i, "P3b:bull_macro_suppression")

            elif trend_exhaustion[i] and ema_slope_arr[i] < 0:
                market_phase[i] = "ABSORPTION"
                absorption_streak += 1
                _dbg(i, "P3b:exhaustion---absorption")

            # FIX-5: require non-bullish close for bear continuation
            elif btv_arr[i] and close_arr[i] <= open_arr[i]:
                market_phase[i] = "BEAR_TREND_CONTINUATION"
                trend_context = "BEAR"
                trend_context_bars = 0
                _dbg(i, "P3b:btv_continuation")
            elif btv_arr[i] and close_arr[i] > open_arr[i]:
                market_phase[i] = "BEAR_TREND_DIGESTION"
                trend_context = "BEAR"
                trend_context_bars = 0
                _dbg(i, "P3b:btv_demoted_digestion(bullish_close)")

            elif btd_arr[i]:
                market_phase[i] = "BEAR_TREND_DIGESTION"
                trend_context = "BEAR"
                trend_context_bars = 0
                _dbg(i, "P3b:btd_digestion")
            elif btp_arr[i]:
                market_phase[i] = "BEAR_TREND_PAUSE"
                trend_context = "BEAR"
                trend_context_bars = 0
                _dbg(i, "P3b:btp_pause")
            elif bta_arr[i]:
                market_phase[i] = "BEAR_TREND_ACCEPTANCE"
                trend_context = "BEAR"
                trend_context_bars = 0
                _dbg(i, "P3b:bta_acceptance")
            elif tv_arr[i]:
                trend_context = "BULL"
                trend_context_bars = 0
                if close_arr[i] >= open_arr[i]:
                    market_phase[i] = "TREND_CONTINUATION"
                    _dbg(i, "P3b:tv_flip_bull")
                else:
                    market_phase[i] = "TREND_DIGESTION"
                    _dbg(i, "P3b:tv_flip_demoted_digestion(bearish_close)")
            elif ab_arr[i] and vr_arr[i] >= absorption_vol_thr:
                market_phase[i] = "ABSORPTION"
                absorption_streak += 1
                _dbg(i, "P3b:absorption")
            else:
                # FIX-6: OBV gate before BALANCE_CHOP
                if ema_stack_bear and re > nml_re_stack:
                    market_phase[i] = "BEAR_TREND_DIGESTION"
                    _dbg(i, "P3b:nml_ema_stack")
                elif ema_slope_arr[i] < -nml_slope_thr and re > nml_re_slope:
                    market_phase[i] = "BEAR_TREND_DIGESTION"
                    _dbg(i, "P3b:nml_slope")
                elif obv_slope_arr[i] < 0 and ema_slope_arr[i] < -nml_slope_obv:
                    # RE floor intentionally absent --- narrow bear bar with
                    # continuing OBV sell pressure is digestion not balance
                    market_phase[i] = "BEAR_TREND_DIGESTION"
                    _dbg(i, "P3b:nml_obv_rescue")
                else:
                    market_phase[i] = "BALANCE_CHOP"
                    _dbg(i, "P3b:nml_chop")

        # ------ Priority 3c: Post-neutral-impulse propagation (FIX-4) ------------------------------------
        elif prev == "IMPULSE_NEUTRAL":
            if ema_stack_bull or ema_slope_arr[i] > p3c_slope_thr:
                if tv_arr[i] and close_arr[i] >= open_arr[i]:
                    market_phase[i] = "TREND_CONTINUATION"
                    trend_context = "BULL"
                    trend_context_bars = 0
                    _dbg(i, "P3c:bull_continuation")
                elif td_arr[i] or tp_arr[i]:
                    market_phase[i] = "TREND_DIGESTION"
                    trend_context = "BULL"
                    trend_context_bars = 0
                    _dbg(i, "P3c:bull_digestion")
                elif ta_arr[i]:
                    market_phase[i] = "TREND_ACCEPTANCE"
                    trend_context = "BULL"
                    trend_context_bars = 0
                    _dbg(i, "P3c:bull_acceptance")
                elif re > p3c_re_min:
                    if close_arr[i] >= open_arr[i]:
                        market_phase[i] = "TREND_DIGESTION"
                        trend_context = "BULL"
                        trend_context_bars = 0
                        _dbg(i, f"P3c:bull_re_fallback(re={re:.2f})")
                    else:
                        market_phase[i] = "BALANCE_CHOP"
                        _dbg(i, "P3c:bull_re_blocked_bearish_close")
                else:
                    market_phase[i] = "BALANCE_CHOP"
                    _dbg(i, "P3c:bull_chop")
            elif ema_stack_bear or ema_slope_arr[i] < -p3c_slope_thr:
                if btv_arr[i] and close_arr[i] <= open_arr[i]:
                    market_phase[i] = "BEAR_TREND_CONTINUATION"
                    trend_context = "BEAR"
                    trend_context_bars = 0
                    _dbg(i, "P3c:bear_continuation")
                elif btd_arr[i] or btp_arr[i]:
                    market_phase[i] = "BEAR_TREND_DIGESTION"
                    trend_context = "BEAR"
                    trend_context_bars = 0
                    _dbg(i, "P3c:bear_digestion")
                elif re > p3c_re_min:
                    if close_arr[i] <= open_arr[i]:
                        market_phase[i] = "BEAR_TREND_DIGESTION"
                        trend_context = "BEAR"
                        trend_context_bars = 0
                        _dbg(i, f"P3c:bear_re_fallback(re={re:.2f})")
                    else:
                        market_phase[i] = "BALANCE_CHOP"
                        _dbg(i, "P3c:bear_re_blocked_bullish_close")
                else:
                    market_phase[i] = "BALANCE_CHOP"
                    _dbg(i, "P3c:bear_chop")
            else:
                market_phase[i] = "BALANCE_CHOP"
                _dbg(i, "P3c:flat_chop")

        # ------ Priority 3d: Post-gap context transition ------------------------------------------------------------------------------
        elif prev in ("GAP_TIMEOUT", "GAP_FILLED", "GAP_CONTINUATION"):
            if ema_stack_bull and re > nml_re_stack:
                market_phase[i] = "TREND_ACCEPTANCE"
                trend_context = "BULL"
                trend_context_bars = 0
                _dbg(i, "P3d:bull_stack")
            elif ema_stack_bear and re > nml_re_stack:
                market_phase[i] = "BEAR_TREND_ACCEPTANCE"
                trend_context = "BEAR"
                trend_context_bars = 0
                _dbg(i, "P3d:bear_stack")
            elif ema_slope_arr[i] > gap_slope_thr and re > gap_re_min:
                market_phase[i] = "TREND_ACCEPTANCE"
                trend_context = "BULL"
                trend_context_bars = 0
                _dbg(i, "P3d:bull_slope")
            elif ema_slope_arr[i] < -gap_slope_thr and re > gap_re_min:
                market_phase[i] = "BEAR_TREND_ACCEPTANCE"
                trend_context = "BEAR"
                trend_context_bars = 0
                _dbg(i, "P3d:bear_slope")
            elif tv_arr[i]:
                trend_context = "BULL"
                trend_context_bars = 0
                if close_arr[i] >= open_arr[i]:
                    market_phase[i] = "TREND_CONTINUATION"
                    _dbg(i, "P3d:tv")
                else:
                    market_phase[i] = "TREND_DIGESTION"
                    _dbg(i, "P3d:tv_demoted_digestion(bearish_close)")
            elif btv_arr[i]:
                trend_context = "BEAR"
                trend_context_bars = 0
                if close_arr[i] <= open_arr[i]:
                    market_phase[i] = "BEAR_TREND_CONTINUATION"
                    _dbg(i, "P3d:btv")
                else:
                    market_phase[i] = "BEAR_TREND_DIGESTION"
                    _dbg(i, "P3d:btv_demoted_digestion(bullish_close)")
            else:
                market_phase[i] = "BALANCE_CHOP"
                _dbg(i, "P3d:chop")

        # ------ Priority 4: Sticky absorption / distribution ------------------------------------------------------------------
        elif prev == "ABSORPTION":
            if not ab_brk[i] and absorption_streak < absorption_max_streak:
                absorption_streak += 1
                market_phase[i] = "ABSORPTION"
                _dbg(i, f"P4:absorption_sticky(streak={absorption_streak})")
            else:
                absorption_streak = 0
                if ema_stack_bull:
                    market_phase[i] = "TREND_ACCEPTANCE"
                elif ema_stack_bear:
                    market_phase[i] = "BEAR_TREND_ACCEPTANCE"
                else:
                    market_phase[i] = "BALANCE_CHOP"
                _dbg(i, "P4:absorption_break")

        elif prev == "DISTRIBUTION":
            distribution_streak += 1
            if (
                not db_brk[i]
                and re < 0.50
                and distribution_streak <= distribution_max_streak
            ):
                market_phase[i] = "DISTRIBUTION"
                _dbg(i, f"P4:distribution_sticky(streak={distribution_streak})")
            else:
                distribution_streak = 0
                market_phase[i] = (
                    "BEAR_TREND_ACCEPTANCE" if ema_stack_bear else "BALANCE_CHOP"
                )
                _dbg(i, "P4:distribution_break")

        # ------ Priority 5: Fresh classification ---------------------------------------------------------------------------------------------------
        else:
            absorption_streak = 0

            if (dist_arr[i] and ema_slope_arr[i] < 0.01) or (
                trend_exhaustion[i] and ema_slope_arr[i] > 0
            ):
                market_phase[i] = "DISTRIBUTION"
                _dbg(i, "P5:distribution")

            elif ab_arr[i] and vr_arr[i] >= absorption_vol_thr:
                market_phase[i] = "ABSORPTION"
                absorption_streak += 1
                _dbg(i, "P5:absorption")

            elif ta_arr[i]:
                if ps != "BEAR" and re > p5_ta_re_min:
                    market_phase[i] = "TREND_ACCEPTANCE"
                    trend_context = "BULL"
                    trend_context_bars = 0
                    _dbg(i, "P5:ta_acceptance")
                elif ps != "BEAR":
                    market_phase[i] = "TREND_DIGESTION"
                    trend_context = "BULL"
                    trend_context_bars = 0
                    _dbg(i, f"P5:ta_downgraded_low_re(re={re:.2f})")
                else:
                    market_phase[i] = "BALANCE_CHOP"
                    _dbg(i, "P5:ta_blocked_by_bear_structure")

            elif bta_arr[i]:
                if ps != "BULL" and not (
                    macro_regime_arr[i] == "BULL_MACRO" and ema_slope_arr[i] >= -0.01
                ):
                    market_phase[i] = "BEAR_TREND_ACCEPTANCE"
                    trend_context = "BEAR"
                    trend_context_bars = 0
                    _dbg(i, "P5:bta_acceptance")
                else:
                    market_phase[i] = "BALANCE_CHOP"
                    _dbg(i, "P5:bta_blocked")

            elif ae == 1 and re > p5_ae_re_min:
                if ema_stack_bull:
                    market_phase[i] = "TREND_ACCEPTANCE"
                    trend_context = "BULL"
                    trend_context_bars = 0
                    _dbg(i, "P5:ae_bull")
                elif ema_stack_bear:
                    market_phase[i] = "BEAR_TREND_ACCEPTANCE"
                    trend_context = "BEAR"
                    trend_context_bars = 0
                    _dbg(i, "P5:ae_bear")
                else:
                    market_phase[i] = "BALANCE_CHOP"
                    _dbg(i, "P5:ae_chop_no_stack")

            elif re > p5_re_high and abs(ema_slope_arr[i]) > p5_re_high_slope:
                if ema_slope_arr[i] > p5_re_high_slope and ps != "BEAR":
                    market_phase[i] = "TREND_ACCEPTANCE"
                    trend_context = "BULL"
                    trend_context_bars = 0
                    _dbg(i, "P5:high_re_bull")
                elif ema_slope_arr[i] < -p5_re_high_slope and ps != "BULL":
                    market_phase[i] = "BEAR_TREND_ACCEPTANCE"
                    trend_context = "BEAR"
                    trend_context_bars = 0
                    _dbg(i, "P5:high_re_bear")
                else:
                    market_phase[i] = "BALANCE_CHOP"
                    _dbg(i, "P5:high_re_chop")

            elif chop_arr[i]:
                _raw_range = high_arr[i] - low_arr[i]
                _obv_dir = (
                    i >= 2
                    and obv_slope_arr[i] > 0
                    and obv_slope_arr[i - 1] > 0
                    and _raw_range > atr14_arr[i] * p5_chop_range_atr
                )
                if _obv_dir and ema_slope_arr[i] > 0:
                    market_phase[i] = "TREND_ACCEPTANCE"
                    trend_context = "BULL"
                    trend_context_bars = 0
                    _dbg(i, "P5:chop_obv_bull_rescue")
                elif _obv_dir and ema_slope_arr[i] < 0:
                    market_phase[i] = "BEAR_TREND_ACCEPTANCE"
                    trend_context = "BEAR"
                    trend_context_bars = 0
                    _dbg(i, "P5:chop_obv_bear_rescue")
                else:
                    market_phase[i] = "BALANCE_CHOP"
                    _dbg(i, "P5:chop")

            else:
                # Fallback: trend_context + EMA stack
                if re < p5_fallback_re_min:
                    market_phase[i] = "BALANCE_CHOP"
                    _dbg(i, "P5:fallback_dead_market")
                elif trend_context == "BULL":
                    market_phase[i] = "TREND_DIGESTION"
                    _dbg(i, "P5:fallback_bull_context")
                elif trend_context == "BEAR":
                    market_phase[i] = "BEAR_TREND_DIGESTION"
                    _dbg(i, "P5:fallback_bear_context")
                elif ema_stack_bull:
                    market_phase[i] = "TREND_DIGESTION"
                    _dbg(i, "P5:fallback_bull_stack")
                elif ema_stack_bear:
                    market_phase[i] = "BEAR_TREND_DIGESTION"
                    _dbg(i, "P5:fallback_bear_stack")
                elif i > 0 and market_phase[i - 1] in _HYSTERESIS_ALLOWED:
                    market_phase[i] = market_phase[i - 1]
                    _dbg(i, f"P5:hysteresis({market_phase[i]})")
                else:
                    market_phase[i] = "BALANCE_CHOP"
                    _dbg(i, "P5:fallback_chop")

        # ------ Post-assignment streak guards ---------------------------------------------------------------------------------------------------------------
        if market_phase[i] != "ABSORPTION":
            absorption_streak = 0
        if market_phase[i] != "DISTRIBUTION":
            distribution_streak = 0

    # ------ Write results back to df ------------------------------------------------------------------------------------------------------------------------------------------
    df["market_phase"] = market_phase
    df["session_context"] = session_context
    df["gap_resolved"] = gap_resolved
    df["gap_auction_active"] = gap_auction_active
    df["post_impulse_active"] = post_impulse_active
    df["impulse_dir"] = impulse_dir
    df["price_structure"] = price_structure_arr
    df["session_type"] = session_type_arr
    df["macro_regime"] = macro_regime_arr
    df["trend_exhaustion"] = trend_exhaustion
    df["obv_slope"] = obv_slope_arr
    df["macd_expanding"] = macd_expanding
    if debug:
        df["_phase_reason"] = phase_reason
    return df


# ------ IMPROVEMENT 2: vectorized row building ---------------------------------------------------------------------
def _build_market_rows(df, symbol, exchange, timeframe, now):
    """
    Replace iterrows() with direct column access.
    Now includes new state columns: price_structure, session_type,
    macro_regime, trend_exhaustion, obv_slope, macd_expanding.
    """
    num_cols = [
        "ema_21_slope",  # arr[i,0]
        "vwap_dist_pct",  # arr[i,1]
        "day_high_dist",  # arr[i,2]
        "day_low_dist",  # arr[i,3]
        "orb_dist_pct",  # arr[i,4]
        "gap_pct",  # arr[i,5]
        "minute_of_day",  # arr[i,6]
        "volume_expansion",  # arr[i,7]
        "atr_expanding",  # arr[i,8]
        "range_efficiency",  # arr[i,9]
        "vwap_acceptance",  # arr[i,10]
        "momentum_decay",  # arr[i,11]
        "candle_overlap",  # arr[i,12]
        "vix",  # arr[i,13]
        "vix_change",  # arr[i,14]
        "gap_atr",  # arr[i,15]
        # New state features
        "trend_exhaustion",  # arr[i,16]
        "obv_slope",  # arr[i,17]
        "macd_expanding",  # arr[i,18]
        "vol_ratio",  # arr[i,19]
        # BUG 4 FIX: vwap_dist_atr was computed but never stored
        "vwap_dist_atr",  # arr[i,20]
    ]
    arr = df[num_cols].values
    ts_list = [pd.Timestamp(t).to_pydatetime() for t in df["ts"].values]
    phase_arr = df["market_phase"].values
    vix_reg = df["vix_regime"].values
    gap_dir = df["gap_dir"].values
    gap_reg = df["gap_regime"].values

    ml_labels = [get_ml_label(p) for p in phase_arr]
    tf_role_arr = (
        df["tf_role"].values if "tf_role" in df.columns else ["MICRO"] * len(ts_list)
    )

    ps_arr = (
        df["price_structure"].values
        if "price_structure" in df.columns
        else ["NEUTRAL"] * len(ts_list)
    )
    impl_dir_arr = (
        df["impulse_dir"].values
        if "impulse_dir" in df.columns
        else [None] * len(ts_list)
    )
    st_arr = (
        df["session_type"].values
        if "session_type" in df.columns
        else ["NORMAL_DAY"] * len(ts_list)
    )
    mr_arr = (
        df["macro_regime"].values
        if "macro_regime" in df.columns
        else ["NEUTRAL_MACRO"] * len(ts_list)
    )
    return [
        (
            symbol,
            exchange,
            timeframe,
            ts_list[i],
            phase_arr[i],
            ml_labels[i],
            str(tf_role_arr[i]),
            # arr cols 0-15: original numeric features
            arr[i, 0],
            arr[i, 1],
            arr[i, 2],
            arr[i, 3],
            arr[i, 4],
            arr[i, 5],
            arr[i, 6],
            arr[i, 7],
            arr[i, 8],
            arr[i, 9],
            arr[i, 10],
            arr[i, 11],
            arr[i, 12],
            arr[i, 13],
            arr[i, 14],
            vix_reg[i],
            arr[i, 15],
            gap_dir[i],
            gap_reg[i],
            # arr cols 16-19: new state + adaptive vol features
            int(arr[i, 16]),  # trend_exhaustion
            float(arr[i, 17]),  # obv_slope
            int(arr[i, 18]),  # macd_expanding
            float(arr[i, 19]),  # vol_ratio
            # categorical state columns
            str(ps_arr[i]),  # price_structure
            str(st_arr[i]),  # session_type
            str(mr_arr[i]),  # macro_regime
            float(arr[i, 20]),  # BUG 4 FIX: vwap_dist_atr
            (
                str(impl_dir_arr[i]) if impl_dir_arr[i] is not None else None
            ),  # BUG 5 FIX: impulse_dir
            now,
        )
        for i in range(len(ts_list))
    ]


def _build_rule_rows(df, symbol, exchange, timeframe, now):
    """Vectorized rule row building --- 5 rules per candle."""
    rule_rows = []
    RULES = [
        ("ORB", df["ORB"] == 1),
        ("EMA_TREND", (df["ema_21_slope"] > 0) & (df["close"] > df["ema_21"])),
        ("VWAP_TREND", (df["vwap_dist_pct"] > 0) & (df["vwap_acceptance"] == 0)),
        ("ATR_EXPANSION", df["atr_expanding"] == 1),
        (
            "VOLUME_EXPANSION",
            (df["volume_expansion"] == 1) & (df["range_efficiency"] > 0.35),
        ),
    ]
    # Build snapshot once per row --- reuse across 5 rules
    # BUG 7 FIX: iterrows() replaced with to_dict("records") --- 10-30x faster
    # iterrows() on 74k rows -- 5 rules = 370k iterations = 30-60s overhead.
    # to_dict("records") builds all row dicts in one vectorized call.
    _snap_cols = [
        "orb_high",
        "orb_low",
        "orb_breakout",
        "orb_quality",
        "orb_location",
        "minute_of_day",
        "ema_21_slope",
        "vwap_dist_pct",
        "atr_expanding",
        "volume_expansion",
        "range_efficiency",
    ]
    _records = df[_snap_cols].to_dict("records")
    snaps = [
        json.dumps(
            {
                "orb_high": json_safe(r["orb_high"]),
                "orb_low": json_safe(r["orb_low"]),
                "orb_breakout": int(r["orb_breakout"]),
                "orb_quality": int(r["orb_quality"]),
                "orb_location": int(r["orb_location"]),
                "minute_of_day": int(r["minute_of_day"]),
                "ema_21_slope": json_safe(r["ema_21_slope"]),
                "vwap_dist_pct": json_safe(r["vwap_dist_pct"]),
                "atr_expanding": int(r["atr_expanding"]),
                "volume_expansion": int(r["volume_expansion"]),
                "range_efficiency": json_safe(r["range_efficiency"]),
            }
        )
        for r in _records
    ]
    # Convert to Python datetimes --- psycopg2 cannot serialize numpy.datetime64
    ts_list = [pd.Timestamp(t).to_pydatetime() for t in df["ts"].values]
    phase_arr = df["market_phase"].values

    for rule_name, eligible_series in RULES:
        elig_arr = eligible_series.values
        for i in range(len(df)):
            rule_rows.append(
                (
                    symbol,
                    exchange,
                    timeframe,
                    ts_list[i],
                    rule_name,
                    bool(elig_arr[i]),
                    snaps[i],
                    phase_arr[i],
                    now,
                )
            )
    return rule_rows


# ------ Market context labelling ---------------------------------------------------------------------------------------------------------------
@strategy_bp.route("/api/offline/label-market-context", methods=["POST"])
def offline_label_market_context():
    try:
        t0 = time.time()
        data = request.get_json() or {}
        symbol = (data.get("symbol") or "").upper().strip()
        exchange = (data.get("exchange") or "NSE").upper().strip()
        timeframe = (data.get("timeframe") or "").lower().strip()
        lookahead = int(data.get("lookahead", 20))
        # `window` param is kept for backward compatibility but no longer drives WARMUP.
        # WARMUP is now derived from TF_CONFIG (ROLL_20, SWING_N, OBV_WINDOW).
        # Passing windowSize in the request has no effect on warmup trimming.

        if not symbol or not timeframe:
            return jsonify({"error": "symbol and timeframe required"}), 400

        with get_db_conn() as conn:
            df = read_sql_safe(
                """
                SELECT i.*, v.vix
                FROM indicators i
                LEFT JOIN india_vix v
                  ON (i.ts AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata')::date = v.trade_date
                WHERE i.symbol=%s AND i.exchange=%s AND i.timeframe=%s
                ORDER BY i.ts ASC
            """,
                conn,
                params=[symbol, exchange, timeframe],
            )

        # Minimum row guard --- ROLL_20 not yet known so use a safe floor.
        # The precise WARMUP is computed and enforced after TF_CONFIG is unpacked.
        if df.empty or len(df) < max(lookahead, 50):
            return (
                jsonify({"error": f"Not enough indicator data --- got {len(df)} rows"}),
                400,
            )

        df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
        # Sort by ts after parsing --- timezone conversion can subtly reorder
        # rows if some have tz info and some don't. State machine REQUIRES
        # strict chronological order --- wrong order = wrong phase labels.
        df = df.sort_values("ts").reset_index(drop=True)

        TF_MINUTES = {"1m": 1, "3m": 3, "5m": 5, "15m": 15}
        tf_min = TF_MINUTES.get(timeframe)
        if not tf_min:
            return jsonify({"error": f"Unsupported timeframe {timeframe}"}), 400

        # ================================================================
        #  TIMEFRAME-AWARE CONFIGURATION
        #  ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        #  Role in the multi-TF system:
        #
        #  15m --- EXECUTION layer
        #       Trend direction, phase decision, entry signal.
        #       Slower rolling windows --- smoother signals, fewer false starts.
        #       Impulse threshold higher (needs more confirmation).
        #       Lookaheads longer (trend moves take more bars to play out).
        #
        #  3m  --- CONFIRMATION layer
        #       Validates 15m signal: structure, momentum, volume.
        #       Medium windows --- fast enough to confirm, slow enough to filter noise.
        #       Impulse threshold medium.
        #
        #  1m  --- MICROSTRUCTURE layer
        #       Entry precision: absorption, spread, order-flow at entry bar.
        #       Tightest windows --- captures sub-minute structure.
        #       Lower impulse threshold (1m moves are small but frequent).
        #       Lookaheads short (1m phases resolve quickly).
        # ================================================================

        # ================================================================
        #  TIMEFRAME-AWARE CONFIGURATION --- REAL-TIME ANCHORED
        #  ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        #  Every window is now chosen so it spans the same market TIME
        #  across timeframes rather than the same bar count.
        #
        #  Target durations (NSE session = 375 min):
        #    ROLL_5  (slope, range expansion): ~15 min of price history
        #    ROLL_10 (ATR reference, momentum): ~30 min
        #    ROLL_20 (volume baseline): ~60 min
        #    VOL_BASELINE: 1 full session (375 min) for vol regime detection
        #    SWING_N: ~15 min per side for swing high/low detection
        #    OBV_WINDOW: ~30 min for OBV slope
        #
        #  Roles in the multi-TF system:
        #  15m --- EXECUTION: trend direction, phase decision, entry signal
        #   5m --- CONFIRMATION: validates 15m signal
        #   3m --- CONFIRMATION: structure and momentum confirmation
        #   1m --- MICROSTRUCTURE: entry precision, absorption, order-flow
        # ================================================================

        TF_CONFIG = {
            # (ROLL_5, ROLL_10, ROLL_20, IMPULSE_WINDOW_BARS,
            #  VOLUME_MULT, RE_IMPULSE_MIN, RE_TREND_MIN, RE_CHOP_MAX,
            #  VWAP_DIST_IMPULSE, GAP_LARGE_BARS, GAP_MOD_BARS, GAP_SMALL_BARS,
            #  SWING_N, OBV_WINDOW, VOL_BASELINE)
            #
            # All windows are duration-anchored:
            #   ROLL_5  = 15min -- tf_min  (min 2)
            #   ROLL_10 = 30min -- tf_min  (min 3)
            #   ROLL_20 = 60min -- tf_min  (min 6)
            #   SWING_N = 15min -- tf_min  (min 2) --- bars each side
            #   OBV_WIN = 30min -- tf_min  (min 2)
            #   VOL_BASELINE = 375min -- tf_min (1 full session)
            #   GAP windows = 45/75/30 min -- tf_min
            #
            #  1m: 15/30/60 min windows. ROLL_5 raised from 5---15 bars
            #      (old 5-bar slope = 5 min, too noisy for meaningful direction)
            #  3m: 5/10/20 bars = 15/30/60 min. Same as before --- already correct.
            #  5m: 3/6/12 bars = 15/30/60 min. IMPULSE_WINDOW raised to 75 (full session)
            # 15m: 3/5/8 bars = 45/75/120 min. ROLL_20 raised to 10 bars (150 min)
            #      for a more stable 15m volume baseline.
            #      VOLUME_MULT raised 1.2---1.3 (15m vol spikes are rarer, need stronger gate)
            # 1m VOLUME_MULT raised 1.5---2.0: 1.5x on 1m fires on random retail noise.
            #   True institutional footprints print at 2.5-3.0x. Base 2.0 with adaptive
            #   scaling (--0.85 to --1.40) gives effective range 1.7x---2.8x.
            "1m": (15, 30, 60, 375, 2.0, 0.60, 0.35, 0.25, 0.5, 45, 75, 30, 5, 30, 375),
            "3m": (5, 10, 20, 125, 1.4, 0.55, 0.30, 0.22, 0.5, 15, 25, 10, 5, 10, 125),
            "5m": (3, 6, 12, 75, 1.3, 0.50, 0.28, 0.20, 0.5, 9, 15, 6, 3, 6, 75),
            # v31: SWING_N 2---5 for 15m. Lookback 8 bars (120 min) was too short;
            # _compute_price_structure almost always returned NEUTRAL, disabling
            # the price-structure execution gate (fix-19) on every 15m bar.
            # With SWING_N=5: lookback = 8--5 = 40 bars = 600 min (---2.7 sessions).
            "15m": (3, 5, 10, 25, 1.3, 0.45, 0.25, 0.18, 0.5, 3, 5, 2, 5, 2, 25),
        }

        (
            ROLL_5,
            ROLL_10,
            ROLL_20,
            IMPULSE_WINDOW_BARS,
            VOLUME_MULT,
            RE_IMPULSE_MIN,
            RE_TREND_MIN,
            RE_CHOP_MAX,
            VWAP_DIST_IMPULSE,
            GAP_BARS_LARGE,
            GAP_BARS_MOD,
            GAP_BARS_SMALL,
            SWING_N,
            OBV_WINDOW,
            VOL_BASELINE,
        ) = TF_CONFIG[timeframe]

        # ------ Phase model lookahead also scales with timeframe ------------------------------
        # 15m trend phase should look 12 bars ahead (= 3h of data)
        # 1m trend phase should look 12 bars ahead (= 12 min of data)
        # Same bar count --- very different real-time horizons.
        # PHASE_MODEL uses fixed bar counts which is correct --- each TF
        # trains independently and learns its own outcome distribution.

        GAP_AUCTION_MAX_BARS = {
            "LARGE_GAP_SESSION": GAP_BARS_LARGE,
            "MODERATE_GAP_SESSION": GAP_BARS_MOD,
            "NO_GAP": GAP_BARS_SMALL,
        }

        # ------ Convert ts to IST before any time-based calculations ------
        # Timestamps from DB are UTC (TIMESTAMPTZ stored as +00).
        # bar_of_day and date MUST use IST time --- NSE opens at 09:15 IST.
        # Using UTC gives bar_of_day = (4*60+15 - 555) = -300 for the
        # 09:15 IST open bar, so bar_of_day==0 never fires and all gap
        # metrics stay NaN for every row.
        if df["ts"].dt.tz is None:
            df["ts"] = df["ts"].dt.tz_localize("UTC")
        df["ts_ist"] = df["ts"].dt.tz_convert("Asia/Kolkata")

        # ------ Feature engineering ---------------------------------------------------------------------------------------------------------
        # bar_of_day: 0 = 09:15, 1 = 09:16, etc. (uses IST time)
        df["bar_of_day"] = (
            df["ts_ist"].dt.hour * 60 + df["ts_ist"].dt.minute - 555
        ) // tf_min
        df["date"] = df["ts_ist"].dt.date

        df["vwap_dist_pct"] = (df["close"] - df["vwap"]) / df["vwap"]
        # ATR-normalised VWAP distance --- stock-independent measure.
        # vwap_dist_pct uses fixed % thresholds which mean completely different
        # things across stocks: 0.4% = 0.2 ATR on TATASTEEL, 1.3 ATR on HINDUNILVR.
        # vwap_dist_atr = (close - vwap) / atr_14 normalises by the stock's own
        # volatility so thresholds are consistent across all symbols.
        df["vwap_dist_atr"] = (df["close"] - df["vwap"]) / df["atr_14"].replace(
            0, np.nan
        )
        df["day_high"] = df.groupby("date")["high"].cummax()
        df["day_low"] = df.groupby("date")["low"].cummin()
        df["day_high_dist"] = (df["day_high"] - df["close"]) / df["day_high"]
        df["day_low_dist"] = (df["close"] - df["day_low"]) / df["day_low"]
        df["orb_range"] = (df["orb_high"] - df["orb_low"]).replace(0, np.nan)
        df["orb_mid"] = (df["orb_high"] + df["orb_low"]) / 2
        df["orb_dist_pct"] = (df["close"] - df["orb_mid"]) / df["orb_range"]

        daily_close = df.groupby("date")["close"].last().shift(1)
        df["prev_day_close"] = df["date"].map(daily_close)

        prev_day_atr = df.groupby("date")["atr_14"].last().shift(1)
        df["prev_day_atr"] = df["date"].map(prev_day_atr)

        # ------ Gap metrics: compute ONLY on bar_of_day==0 then ffill ------
        # Only the first bar of the day (09:15 IST) has a meaningful opening gap.
        # All other bars must inherit the day's gap via forward-fill.
        # Key: set NaN on non-open bars FIRST, then ffill, then fillna fallback.
        is_open_bar = df["bar_of_day"] == 0

        # Compute raw gap values --- NaN on all non-open bars
        open_of_day = df["open"].where(is_open_bar)  # NaN except bar_0
        gap_raw = open_of_day - df["prev_day_close"]  # NaN except bar_0
        gap_atr_raw = gap_raw / df["prev_day_atr"].replace(
            0, np.nan
        )  # NaN except bar_0

        # Assign to columns --- NaN on non-open bars so ffill can propagate bar_0 value
        df["gap_pct"] = gap_raw / df["prev_day_close"].replace(
            0, np.nan
        )  # NaN non-open

        # Classify gap direction and regime only where we have a real opening gap
        # Use gap_atr_raw directly (not df["gap_atr"]) so we get NaN on non-open bars
        df["gap_atr"] = gap_atr_raw  # NaN on non-open bars --- DO NOT fillna(0) yet

        # Use pandas .loc on open bars only --- avoids np.where dtype coercion
        # which silently converts string columns to float NaN
        df["gap_dir"] = None  # object dtype from start
        df["gap_regime"] = None
        df["gap_flag"] = None

        open_mask = is_open_bar & gap_atr_raw.notna()
        df.loc[open_mask, "gap_dir"] = np.where(
            gap_atr_raw[open_mask] > 0,
            "UP",
            np.where(gap_atr_raw[open_mask] < 0, "DOWN", "NONE"),
        )
        df.loc[open_mask, "gap_regime"] = np.where(
            gap_atr_raw[open_mask].abs() >= 1.2,
            "LARGE_GAP",
            np.where(gap_atr_raw[open_mask].abs() >= 0.5, "MODERATE_GAP", "NO_GAP"),
        )
        df.loc[open_mask, "gap_flag"] = (
            df.loc[open_mask, "gap_pct"].abs() > 0.003
        ).astype(int)

        # Forward fill within each IST date --- all bars inherit the day opening values.
        # transform(ffill) correctly handles object-dtype string columns with None gaps.
        for _col, _fill in [
            ("gap_pct", 0),
            ("gap_atr", 0),
            ("gap_dir", "NONE"),
            ("gap_regime", "NO_GAP"),
            ("gap_flag", 0),
        ]:
            df[_col] = (
                df.groupby("date")[_col].transform(lambda x: x.ffill()).fillna(_fill)
            )
        df["gap_flag"] = df["gap_flag"].astype(int)

        # Gap fill tracking:
        # gap_fill_pct = 0   --- gap fully open (price at opening level)
        # gap_fill_pct = 1   --- gap fully filled (price back at prev_day_close)
        # gap_fill_pct > 1   --- price overshot past prev_day_close (overfill)
        # gap_fill_pct < 0   --- price extended FURTHER from prev_day_close (continuation)
        #
        # For UP gap: open > prev_day_close. Fill means price drops back.
        #   fill_pct = 1 - (close - prev_day_close) / (open - prev_day_close)
        #   At close==open --- fill_pct = 0 (gap still open)
        #   At close==prev_day_close --- fill_pct = 1 (gap filled)
        #
        # For DOWN gap: open < prev_day_close. Same formula works because
        #   (open - prev_day_close) is negative, numerator also flips sign.
        df["gap_fill_target"] = df["prev_day_close"]
        gap_open_size = (df["open"] - df["prev_day_close"]).replace(0, np.nan)
        df["gap_fill_pct"] = np.where(
            df["gap_atr"].abs() > 0,
            (1 - (df["close"] - df["prev_day_close"]) / gap_open_size),
            0,
        ).clip(-3, 3)

        df["atr_pct"] = df["atr_14"] / df["close"]
        df["bb_width"] = (df["bollinger_upper"] - df["bollinger_lower"]) / df[
            "bollinger_mid"
        ]

        # ------ Volatility regime detection (drives all adaptive sizing) ---
        # vol_ratio = current ATR% / rolling baseline ATR% over 1 full session.
        # This is symbol-independent because ATR% is already price-normalised.
        # Clipped [0.5, 2.0] --- beyond these extremes, don't over-adapt.
        #
        # vol_ratio > 1.3 --- HIGH_VOL: market moving fast, use shorter windows
        #                              and tighter thresholds to stay responsive
        # vol_ratio < 0.8 --- LOW_VOL:  market quiet, use longer windows
        #                              to see genuine direction through noise
        # 0.8 --- 1.3       --- NORMAL:   base windows and thresholds apply
        atr_baseline = df["atr_pct"].rolling(VOL_BASELINE, min_periods=ROLL_20).mean()
        vol_ratio = (
            (df["atr_pct"] / atr_baseline.replace(0, np.nan)).clip(0.5, 2.0).fillna(1.0)
        )
        is_high_vol = vol_ratio > 1.3
        is_low_vol = vol_ratio < 0.8

        # Smooth vol_ratio over ROLL_5 bars so thresholds shift gradually,
        # not frame-by-frame (prevents boundary flickering in label assignment)
        vol_ratio_smooth = (
            vol_ratio.rolling(ROLL_5, min_periods=2).mean().clip(0.6, 1.6)
        )
        df["vol_ratio"] = vol_ratio_smooth  # stored for ML feature

        # ------ Derived fast/slow window sizes ---------------------------------------------------------------------------
        # Three tiers per signal family: fast (high-vol), base (normal), slow (low-vol)
        roll_slope_fast = max(2, ROLL_5 // 2)  # half base
        roll_slope_slow = min(
            ROLL_5 * 2, ROLL_20
        )  # double base, capped at vol baseline
        roll_atr_fast = max(2, ROLL_10 // 2)
        roll_atr_slow = min(ROLL_10 * 2, ROLL_20)
        roll_vol_fast = max(ROLL_10, ROLL_20 // 2)  # shorter vol baseline in low-vol
        roll_vol_slow = min(
            ROLL_20 * 2, VOL_BASELINE
        )  # longer vol baseline in high-vol

        # ------ EMA slope --- adaptive: fast when volatile, slow when quiet ---
        ema21_base = df["ema_21"].diff().rolling(ROLL_5).mean()
        ema21_fast = df["ema_21"].diff().rolling(roll_slope_fast).mean()
        ema21_slow = df["ema_21"].diff().rolling(roll_slope_slow).mean()
        df["ema_21_slope"] = np.where(
            is_high_vol, ema21_fast, np.where(is_low_vol, ema21_slow, ema21_base)
        )

        ema50_base = df["ema_50"].diff().rolling(ROLL_5).mean()
        ema50_fast = df["ema_50"].diff().rolling(roll_slope_fast).mean()
        ema50_slow = df["ema_50"].diff().rolling(roll_slope_slow).mean()
        df["ema_50_slope"] = np.where(
            is_high_vol, ema50_fast, np.where(is_low_vol, ema50_slow, ema50_base)
        )

        # ------ Volume baseline --- adaptive: LONGER in high-vol (stable ref) ---
        # In high-vol periods recent volume has spiked, so a short window
        # would inflate the baseline, making nothing look "elevated".
        # Longer baseline preserves the pre-spike average.
        vol_ma_base = df["volume"].rolling(ROLL_20).mean()
        vol_ma_fast_s = df["volume"].rolling(roll_vol_fast).mean()
        vol_ma_slow_s = df["volume"].rolling(roll_vol_slow).mean()
        vol_ma20 = pd.Series(
            np.where(
                is_high_vol,
                vol_ma_slow_s,  # longer in high vol
                np.where(is_low_vol, vol_ma_fast_s, vol_ma_base),  # shorter in low vol
            ),
            index=df.index,
        )

        # ------ ATR reference --- adaptive: fast when volatile ---------------------------------------
        atr_ref_base = df["atr_14"].rolling(ROLL_10).mean()
        atr_ref_fast = df["atr_14"].rolling(roll_atr_fast).mean()
        atr_ref_slow = df["atr_14"].rolling(roll_atr_slow).mean()
        atr_ref = pd.Series(
            np.where(
                is_high_vol,
                atr_ref_fast,
                np.where(is_low_vol, atr_ref_slow, atr_ref_base),
            ),
            index=df.index,
        )

        # ------ Range expansion --- adaptive ---------------------------------------------------------------------------------------
        re_base_ref = df["true_range"].rolling(ROLL_5).mean()
        re_fast_ref = df["true_range"].rolling(roll_slope_fast).mean()
        re_slow_ref = df["true_range"].rolling(roll_slope_slow).mean()
        re_ref_sel = np.where(
            is_high_vol, re_fast_ref, np.where(is_low_vol, re_slow_ref, re_base_ref)
        )

        # ------ range_efficiency must exist before momentum decay uses it ------
        # (full assignment happens below in the derived signals block,
        #  but the adaptive rolling mean needs it here first)
        # range_efficiency denominator: (high - low) not true_range.
        # true_range includes overnight gaps (|H - prevClose|, |L - prevClose|).
        # On gap days TR is inflated by the gap --- body/TR deflated --- bar looks
        # weak even if price moved strongly intraday (gap-and-go candles
        # incorrectly labelled low-conviction).
        # (high - low) measures pure intraday conviction --- correct for phase
        # labelling. true_range is preserved unchanged for ATR calculations.
        df["range_efficiency"] = (df["close"] - df["open"]).abs() / (
            df["high"] - df["low"]
        ).replace(0, np.nan)

        # ------ Momentum decay --- adaptive ------------------------------------------------------------------------------------------
        re_ma_base = df["range_efficiency"].rolling(ROLL_10).mean()
        re_ma_fast = df["range_efficiency"].rolling(roll_atr_fast).mean()
        re_ma_slow = df["range_efficiency"].rolling(roll_atr_slow).mean()
        re_ma_sel = np.where(
            is_high_vol, re_ma_fast, np.where(is_low_vol, re_ma_slow, re_ma_base)
        )

        # ------ Candle overlap --- adaptive ------------------------------------------------------------------------------------------
        ov_fast = (
            df["high"].rolling(roll_slope_fast).min()
            < df["low"].rolling(roll_slope_fast).max()
        )
        ov_base = df["high"].rolling(ROLL_5).min() < df["low"].rolling(ROLL_5).max()
        ov_slow = (
            df["high"].rolling(roll_slope_slow).min()
            < df["low"].rolling(roll_slope_slow).max()
        )

        # ------ Adaptive thresholds ---------------------------------------------------------------------------------------------------------------
        # RE thresholds scale with smoothed vol_ratio:
        #   High vol --- higher thresholds (noisy bars look directional by chance)
        #   Low vol  --- lower thresholds  (genuine moves are smaller in absolute terms)
        # Bounds prevent extreme adaptation: max 30% raise, max 30% lower
        re_impulse_thr = (RE_IMPULSE_MIN * vol_ratio_smooth).clip(
            RE_IMPULSE_MIN * 0.70, RE_IMPULSE_MIN * 1.30
        )
        re_trend_thr = (RE_TREND_MIN * vol_ratio_smooth).clip(
            RE_TREND_MIN * 0.70, RE_TREND_MIN * 1.40
        )
        re_chop_thr = (RE_CHOP_MAX * vol_ratio_smooth).clip(
            RE_CHOP_MAX * 0.70, RE_CHOP_MAX * 1.30
        )

        # Volume multiplier: higher in high-vol (baseline elevated by regime)
        vol_mult_thr = (VOLUME_MULT * vol_ratio_smooth).clip(
            VOLUME_MULT * 0.85, VOLUME_MULT * 1.40
        )

        # VWAP distance: wider in high-vol (price swings further from VWAP normally)
        vwap_dist_thr = (VWAP_DIST_IMPULSE * vol_ratio_smooth).clip(
            VWAP_DIST_IMPULSE * 0.80, VWAP_DIST_IMPULSE * 1.50
        )

        # ------ Compute all derived signals with adaptive parameters ------------
        df["range_expansion"] = (df["true_range"] > re_ref_sel).astype(int)
        df["volume_z"] = (df["volume"] - vol_ma20) / df["volume"].rolling(ROLL_20).std()
        df["effort_result"] = df["volume"] * df["true_range"]
        # range_efficiency already computed above (needed for adaptive momentum decay)
        df["volume_expansion"] = (df["volume"] > vol_ma20 * vol_mult_thr).astype(int)
        df["atr_expanding"] = (df["atr_14"] > atr_ref).astype(int)
        # vwap_acceptance: price within 0.5 ATR of VWAP (was fixed 1% which is
        # too wide for low-vol stocks and too tight for high-vol stocks)
        df["vwap_acceptance"] = (df["vwap_dist_atr"].abs() < 0.5).astype(int)
        df["momentum_decay"] = (df["range_efficiency"] < re_ma_sel).astype(int)
        df["candle_overlap"] = np.where(
            is_high_vol, ov_fast, np.where(is_low_vol, ov_slow, ov_base)
        ).astype(int)
        df["minute_of_day"] = df["bar_of_day"] * tf_min
        df["session_bucket"] = np.select(
            [df["minute_of_day"] < 45, df["minute_of_day"] < 300], [0, 1], default=2
        )
        df["expiry_proximity"] = (
            df["ts_ist"].dt.day >= (df["ts_ist"].dt.days_in_month - 2)
        ).astype(int)

        if "vix" in df.columns:
            # ffill within each IST date so VIX from today fills all bars
            df["vix_level"] = df.groupby("date")["vix"].ffill().bfill()
        else:
            df["vix_level"] = 0.0
        df["vix"] = df["vix_level"]
        df["vix_change"] = df["vix_level"].diff().fillna(0)
        df["vix_regime"] = np.select(
            [df["vix_level"] < 12, df["vix_level"] < 18],
            ["LOW_VOL", "NORMAL_VOL"],
            default="HIGH_VOL",
        )
        df["news_flag"] = 0
        if "adx_14" not in df.columns:
            df["adx_14"] = 0

        # Initialise state-machine output columns to zero so the inf-replace
        # loop below doesn't KeyError. _run_state_machine overwrites these
        # with real computed values after it runs (line ~1527).
        df["trend_exhaustion"] = 0
        df["obv_slope"] = 0.0
        df["macd_expanding"] = 0

        # Replace inf only --- do NOT fillna yet. fillna(0) happens after
        # window trim so warmup NaNs are dropped, not filled with fake zeros.
        FEATURE_COLS = [
            "vwap_dist_pct",
            "vwap_dist_atr",
            "day_high_dist",
            "day_low_dist",
            "orb_dist_pct",
            "gap_pct",
            "gap_flag",
            "ema_21_slope",
            "ema_50_slope",
            "adx_14",
            "atr_pct",
            "bb_width",
            "range_expansion",
            "volume_z",
            "effort_result",
            "range_efficiency",
            "volume_expansion",
            "atr_expanding",
            "vwap_acceptance",
            "momentum_decay",
            "candle_overlap",
            "minute_of_day",
            "session_bucket",
            "expiry_proximity",
            "vix_level",
            "vix_change",
            "news_flag",
            # New state features --- included so inf/NaN are cleaned before write
            "trend_exhaustion",
            "obv_slope",
            "macd_expanding",
            # Adaptive vol regime feature --- useful for ML
            "vol_ratio",
        ]
        for c in FEATURE_COLS:
            df[c] = df[c].replace([np.inf, -np.inf], np.nan)

        # ------ Phase pre-classification (vectorized) ---------------------------------------------------
        df["market_phase"] = "UNCLASSIFIED"
        df["session_context"] = None
        df["gap_resolved"] = 0
        df["gap_auction_started"] = 0
        df["gap_auction_active"] = 0

        # FIX 2: Both LARGE_GAP and MODERATE_GAP need gap auction treatment.
        # Previously only LARGE_GAP triggered "GAP" session context ---
        # moderate gaps fell into BALANCE and got no special handling.
        # Set session_context on bar_0 only, then ffill across the day.
        # Use .loc with string values --- avoids np.where dtype coercion to float.
        open_mask = df["bar_of_day"] == 0
        df.loc[open_mask & (df["gap_regime"] == "LARGE_GAP"), "session_context"] = (
            "LARGE_GAP_SESSION"
        )
        df.loc[open_mask & (df["gap_regime"] == "MODERATE_GAP"), "session_context"] = (
            "MODERATE_GAP_SESSION"
        )
        df.loc[
            open_mask & ~df["gap_regime"].isin(["LARGE_GAP", "MODERATE_GAP"]),
            "session_context",
        ] = "BALANCE"

        # Use transform(ffill) --- handles object-dtype string columns correctly.
        # groupby().ffill() silently skips None propagation on mixed object columns.
        df["session_context"] = (
            df.groupby("date")["session_context"]
            .transform(lambda x: x.ffill())
            .fillna("BALANCE")
        )

        # Convenience boolean --- True for all bars on a gap day
        df["is_gap_session"] = df["session_context"].isin(
            ["LARGE_GAP_SESSION", "MODERATE_GAP_SESSION"]
        )

        # BALANCE_CHOP: uses adaptive RE threshold (re_chop_thr)
        # vwap_chop_thresh now ATR-normalised: price within 0.3 ATR of VWAP
        # is definitively in the "fair value" zone regardless of stock price level.
        # Old fixed-% thresholds (0.8%---1.5%) had different meanings per symbol.
        vwap_chop_thresh_atr = 0.3  # same for all TFs --- ATR already TF-scaled
        slope_flat_thresh = {"1m": 0.0005, "3m": 0.001, "5m": 0.002, "15m": 0.005}[
            timeframe
        ]
        balance_chop = (
            (df["range_efficiency"] < re_chop_thr)
            & (df["atr_expanding"] == 0)
            & (df["vwap_dist_atr"].abs() < vwap_chop_thresh_atr)
            & (df["ema_21_slope"].abs() < slope_flat_thresh)
        )
        # BUG 3 FIX: First trend_acceptance definition removed.
        # The correct adaptive definition (using re_chop_thr) is below after
        # bear trend signals. Having two definitions caused the first to be
        # silently overwritten --- wasting ~10ms and causing confusion.
        # Compression: p33 of BB width per date group (self-calibrating per symbol)
        bb_width_p33 = df.groupby("date")["bb_width"].transform(
            lambda x: x.rolling(ROLL_20, min_periods=5).quantile(0.33)
        )
        compression = (
            (df["bb_width"] < bb_width_p33)
            & (df["range_efficiency"] < re_chop_thr)  # adaptive RE gate
            & (df["atr_expanding"] == 0)
        )

        # ------ Vectorized signals (inputs to state machine --- NOT labels) ------------------
        # These are boolean Series computed efficiently across all rows.
        # The state machine uses them as inputs but assigns ALL labels itself
        # with full awareness of previous state and market context.
        # Pre-assigning labels here would bypass context --- a bar that looks like
        # TREND_ACCEPTANCE in isolation may actually be TREND_CONTINUATION or
        # BALANCE_CHOP depending on what preceded it.

        # ------ Impulse detection with adaptive thresholds ------------------------------------------
        # re_impulse_thr and vwap_dist_thr are Series that scale with
        # vol_ratio_smooth --- tighter in high-vol (noisier), looser in low-vol
        # Impulse VWAP distance gate now uses ATR-normalised units.
        # vwap_dist_thr = VWAP_DIST_IMPULSE * vol_ratio_smooth (0.5 -- adaptive)
        # Typical range: 0.4---0.75 ATR depending on regime.
        # This replaces the fixed % threshold which had inconsistent meaning
        # across different stocks and volatility levels.
        base_impulse = (
            (df["volume_expansion"] == 1)
            & (df["atr_expanding"] == 1)
            & (df["range_efficiency"] > re_impulse_thr)
            & (df["momentum_decay"] == 0)
            & (df["vwap_dist_atr"].abs() > vwap_dist_thr)
        )
        base_impulse &= (df["bar_of_day"] < IMPULSE_WINDOW_BARS) | (
            df["volume"] > vol_ma20 * 2
        )

        bullish_close = df["close"] > df["open"]
        bearish_close = df["close"] < df["open"]
        body_to_range = (df["close"] - df["open"]).abs() / (
            df["high"] - df["low"]
        ).replace(0, np.nan)
        # Explicit direction gate for neutral impulses: doji-like or low body/range.
        neutral_direction = (
            ((~bullish_close & ~bearish_close) | (body_to_range <= 0.30))
            & (df["range_efficiency"] < 0.55)
        )

        bullish_impulse = (
            base_impulse
            & bullish_close
            & (df["volume"] > vol_ma20)
            & (df["close"] > df["ema_21"])
            & (df["ema_21_slope"] > 0)
            & (df["vwap_dist_pct"] > 0)
        )
        bearish_impulse = (
            base_impulse
            & bearish_close
            & (df["volume"] > vol_ma20)
            & (df["close"] < df["ema_21"])
            & (df["ema_21_slope"] < 0)
            & (df["vwap_dist_pct"] < 0)
        )
        neutral_impulse = (
            base_impulse & neutral_direction & ~bullish_impulse & ~bearish_impulse
        )

        # Keep market_phase as UNCLASSIFIED for ALL bars --- state machine assigns everything
        # (gap auction entry bars will be set in state machine at bar_of_day==0)

        # FIX 6: gap_auction_entry now uses is_gap_session (covers both
        # LARGE and MODERATE gap sessions). Resolution uses gap_fill_pct
        # which is gap-specific, not generic candle metrics.
        gap_auction_entry = df["is_gap_session"] & (df["bar_of_day"] == 0)
        # gap_auction_resolved intentionally removed --- a strong candle does NOT
        # resolve a gap. Only gap_fill_pct >= 0.80 or timeout ends the auction.
        gap_auction_resolved = pd.Series(
            False, index=df.index
        )  # unused, kept for signature
        gap_auction_failed = (
            (df["range_efficiency"] < 0.20)
            & (df["volume"] < vol_ma20)
            & (df["vwap_acceptance"] == 1)
        )
        # ABSORPTION: massive volume + tiny body = effort without result.
        # Institutional passive orders absorbing aggressive flow.
        # DECOUPLED from VWAP --- real absorption happens wherever large players
        # have limit orders: swing lows (below VWAP in downtrends), swing highs
        # (above VWAP in uptrends), and historical support/resistance levels.
        # Restricting to close>VWAP and vwap_acceptance==1 was missing ~50% of
        # genuine absorption events that occur below VWAP in bear markets.
        # The STATE MACHINE provides the directional context (bull vs bear trend)
        # that determines whether absorption is bullish or bearish.
        # Pure signal: vol_expansion + atr_expanding==0 + RE < 0.35
        absorption = (
            (df["volume_expansion"] == 1)
            & (df["atr_expanding"] == 0)
            & (df["range_efficiency"] < 0.35)
        )
        # DISTRIBUTION: absorption character but BB width expanding (highs widening)
        # and price above VWAP --- indicates supply being absorbed at elevated prices.
        # Keeps the VWAP check only for distribution (not absorption) because
        # distribution specifically means selling at high prices above fair value.
        distribution = (
            absorption & (df["bb_width"] > bb_width_p33) & (df["close"] > df["vwap"])
        )
        # ------ Bull trend signals with adaptive RE threshold ---------------------------------------
        # re_trend_thr is a Series --- element-wise comparison works fine.
        ema_stacked_bull = (df["ema_9"] > df["ema_21"]) & (df["ema_21"] > df["ema_50"])
        trend_valid = (
            (df["ema_21_slope"] > 0)
            & (df["close"] > df["vwap"])
            & (df["range_efficiency"] > re_trend_thr)
            & ema_stacked_bull
        )
        trend_pause = (
            (df["ema_21_slope"] > 0)
            & (df["close"] > df["ema_21"])
            & (df["range_efficiency"] >= re_chop_thr)
            & (df["range_efficiency"] < re_trend_thr)
            & (df["volume"] > vol_ma20)
        )
        trend_acceptance = (
            (df["ema_21_slope"] > 0)
            & (df["close"] > df["vwap"])
            & ema_stacked_bull
            & (
                (df["range_efficiency"] >= re_chop_thr)
                | (
                    (df["gap_regime"] == "LARGE_GAP")
                    & (df["range_efficiency"] >= re_chop_thr * 0.6)
                )
            )
            & (df["atr_expanding"] == 0)
        )
        trend_digestion = (
            (df["range_efficiency"] >= re_chop_thr * 0.6)
            & (df["range_efficiency"] < re_trend_thr)
            & (df["atr_expanding"] == 0)
            & (df["close"] > df["vwap"])
            & (df["ema_21_slope"] > 0)
            & ~trend_acceptance
        )

        # ------ Bear trend signals --- mirrors of bull, same adaptive thresholds ---
        ema_stacked_bear = (df["ema_9"] < df["ema_21"]) & (df["ema_21"] < df["ema_50"])
        bear_trend_valid = (
            (df["ema_21_slope"] < 0)
            & (df["close"] < df["vwap"])
            & (df["range_efficiency"] > re_trend_thr)
            & ema_stacked_bear
        )
        bear_trend_pause = (
            (df["ema_21_slope"] < 0)
            & (df["close"] < df["ema_21"])
            & (df["range_efficiency"] >= re_chop_thr)
            & (df["range_efficiency"] < re_trend_thr)
            & (df["volume"] > vol_ma20)
        )
        bear_trend_acceptance = (
            (df["ema_21_slope"] < 0)
            & (df["close"] < df["vwap"])
            & ema_stacked_bear
            & (
                (df["range_efficiency"] >= re_chop_thr)
                | (
                    (df["gap_regime"] == "LARGE_GAP")
                    & (df["range_efficiency"] >= re_chop_thr * 0.6)
                )
            )
            & (df["atr_expanding"] == 0)
        )
        bear_trend_digestion = (
            (df["range_efficiency"] >= re_chop_thr * 0.6)
            & (df["range_efficiency"] < re_trend_thr)
            & (df["atr_expanding"] == 0)
            & (df["close"] < df["vwap"])
            & (df["ema_21_slope"] < 0)
            & ~bear_trend_acceptance
        )

        absorption_break = (df["range_efficiency"] > 0.45) | (df["atr_expanding"] == 1)
        distribution_break = (df["close"] < df["vwap"]) | (
            df["range_efficiency"] > 0.45
        )

        # ------ IMPROVEMENT 1: numpy state machine ---------------------------------------------------------
        df = _run_state_machine(
            df,
            bullish_impulse=bullish_impulse,
            bearish_impulse=bearish_impulse,
            neutral_impulse=neutral_impulse,
            trend_valid=trend_valid,
            trend_digestion=trend_digestion,
            trend_pause=trend_pause,
            trend_acceptance=trend_acceptance,
            bear_trend_valid=bear_trend_valid,
            bear_trend_digestion=bear_trend_digestion,
            bear_trend_pause=bear_trend_pause,
            bear_trend_acceptance=bear_trend_acceptance,
            compression=compression,
            balance_chop=balance_chop,
            absorption=absorption,
            distribution=distribution,
            absorption_break=absorption_break,
            distribution_break=distribution_break,
            vol_ma20=vol_ma20,
            GAP_AUCTION_MAX_BARS=GAP_AUCTION_MAX_BARS,
            swing_n=3,
            obv_window=10,
            roll_20=20,
            absorption_vol_thr=1.1,
            absorption_max_streak=6,
            distribution_max_streak=5,
            pullback_min_bars=2,
            trend_context_decay=20,
        )
        # ------ ORB quality (vectorized) ---------------------------------------------------------------------------------------
        df["orb_breakout"] = (
            (df["close"] > df["orb_high"]) & (df["bar_of_day"] <= int(90 / tf_min))
        ).astype(int)
        df["orb_quality"] = (
            (df["volume_expansion"] == 1)
            & (df["atr_expanding"] == 1)
            & (df["range_efficiency"] > 0.45)
        ).astype(int)
        df["orb_location"] = (
            (df["close"] > df["ema_21"]) & (df["vwap_dist_pct"] > 0)
        ).astype(int)
        df["ORB"] = (
            (df["orb_breakout"] == 1)
            & (df["orb_quality"] == 1)
            & (df["orb_location"] == 1)
        ).astype(int)

        # ------ Trim warmup rows FIRST --- then fillna(0) ---------------------------------------
        # WARMUP must cover the longest rolling window used:
        #   ROLL_20           --- vol_ma20, bb_width_p33
        #   4 * SWING_N       --- swing detection needs 4*n lookback bars
        #   OBV_WINDOW        --- obv_slope lookback
        #   roll_slope_slow   --- slowest EMA slope window
        #   roll_vol_slow     --- longest volume baseline in low-vol regime
        #
        # VOL_BASELINE (1 session) intentionally NOT in WARMUP --- it uses
        # min_periods=ROLL_20 so it starts producing values after ROLL_20 bars.
        # Including VOL_BASELINE would discard 1 full session as warmup.
        #
        # Real-time cost of WARMUP per TF:
        #   1m : max(60, 20, 30, 30, 120) = 120 bars = 120 min
        #   3m : max(20, 20, 10, 10,  40) = 40  bars = 120 min
        #   5m : max(12, 12,  6,  6,  24) = 24  bars = 120 min
        #  15m : max(10,  8,  2,  6,  20) = 20  bars = 300 min
        WARMUP = max(ROLL_20, 4 * SWING_N, OBV_WINDOW, roll_slope_slow, roll_vol_slow)
        df = df.iloc[WARMUP:].reset_index(drop=True)

        # Now fillna is safe --- only genuine missing values remain
        for c in FEATURE_COLS:
            df[c] = df[c].fillna(0)

        now = datetime.now(timezone.utc)

        # ------ IMPROVEMENT 2: vectorized row building ---------------------------------------------
        # Tag each bar with its TF role --- used by ML pipeline to know
        # which model to train and how to combine signals across TFs
        tf_role = {"1m": "MICRO", "3m": "CONFIRM", "5m": "CONFIRM", "15m": "EXECUTE"}[
            timeframe
        ]
        df["tf_role"] = tf_role
        market_rows = _build_market_rows(df, symbol, exchange, timeframe, now)
        rule_rows = _build_rule_rows(df, symbol, exchange, timeframe, now)

        # ------ IMPROVEMENT 3: chunked inserts ---------------------------------------------------------------------
        MARKET_SQL = """
            INSERT INTO market_context (
                symbol,exchange,timeframe,ts,market_phase,ml_label,tf_role,ema_21_slope,
                vwap_dist_pct,day_high_dist,day_low_dist,orb_dist_pct,gap_pct,minute_of_day,
                volume_expansion,atr_expanding,range_efficiency,vwap_acceptance,
                momentum_decay,candle_overlap,vix,vix_change,vix_regime,
                gap_atr,gap_dir,gap_regime,
                trend_exhaustion,obv_slope,macd_expanding,vol_ratio,
                price_structure,session_type,macro_regime,
                vwap_dist_atr,
                impulse_dir,
                created_at
            ) VALUES %s
            ON CONFLICT (symbol,exchange,timeframe,ts) DO UPDATE SET
                market_phase=EXCLUDED.market_phase,
                ml_label=EXCLUDED.ml_label,
                tf_role=EXCLUDED.tf_role,
                ema_21_slope=EXCLUDED.ema_21_slope,
                vwap_dist_pct=EXCLUDED.vwap_dist_pct,
                gap_atr=EXCLUDED.gap_atr,
                gap_dir=EXCLUDED.gap_dir,
                gap_regime=EXCLUDED.gap_regime,
                trend_exhaustion=EXCLUDED.trend_exhaustion,
                obv_slope=EXCLUDED.obv_slope,
                macd_expanding=EXCLUDED.macd_expanding,
                vol_ratio=EXCLUDED.vol_ratio,
                price_structure=EXCLUDED.price_structure,
                session_type=EXCLUDED.session_type,
                macro_regime=EXCLUDED.macro_regime,
                vwap_dist_atr=EXCLUDED.vwap_dist_atr,
                impulse_dir=EXCLUDED.impulse_dir,
                created_at=EXCLUDED.created_at
        """
        RULE_SQL = """
            INSERT INTO rule_evaluations (
                symbol,exchange,timeframe,ts,strategy_id,
                rule_eligibility,condition_snapshot,market_phase,created_at
            ) VALUES %s
            ON CONFLICT (symbol,exchange,timeframe,ts,strategy_id) DO UPDATE SET
                rule_eligibility=EXCLUDED.rule_eligibility,
                condition_snapshot=EXCLUDED.condition_snapshot,
                market_phase=EXCLUDED.market_phase, created_at=EXCLUDED.created_at
        """

        with get_db_conn() as conn:
            with conn.cursor() as cur:
                _chunk_execute(cur, MARKET_SQL, market_rows)
                _chunk_execute(cur, RULE_SQL, rule_rows)

        elapsed = round(time.time() - t0, 1)
        return jsonify(
            {
                "status": "SUCCESS",
                "market_rows": len(market_rows),
                "rule_rows": len(rule_rows),
                "elapsed_sec": elapsed,
            }
        )

    except Exception:
        traceback.print_exc()
        return jsonify({"error": traceback.format_exc()}), 500


# ------ Phase parameter calibration ------------------------------------------------------------------------------------------------------
# DB migration (run once before using):
#
#   CREATE TABLE IF NOT EXISTS phase_params (
#       id              SERIAL PRIMARY KEY,
#       symbol          TEXT    NOT NULL,
#       exchange        TEXT    NOT NULL DEFAULT 'NSE',
#       timeframe       TEXT    NOT NULL,
#       market_phase    TEXT    NOT NULL,
#       optimal_tp      FLOAT   NOT NULL,
#       optimal_sl      FLOAT   NOT NULL,
#       optimal_lookahead_min INT NOT NULL,
#       samples         INT     NOT NULL,
#       win_rate        FLOAT,
#       avg_mfe_r       FLOAT,
#       avg_mae_r       FLOAT,
#       p25_mfe_r       FLOAT,
#       p50_mfe_r       FLOAT,
#       p75_mfe_r       FLOAT,
#       p25_mae_r       FLOAT,
#       p75_exit_after  INT,
#       computed_at     TIMESTAMPTZ DEFAULT NOW(),
#       UNIQUE (symbol, exchange, timeframe, market_phase)
#   );

_PHASE_PARAMS_CACHE: dict = {}  # (symbol,exchange,tf) --- {phase---params}
_PHASE_PARAMS_CACHE_TS: dict = {}  # (symbol,exchange,tf) --- timestamp of last load
_PHASE_PARAMS_CACHE_TTL = 300  # 5 minutes --- re-query DB after this


def _load_phase_params(symbol: str, exchange: str, timeframe: str, conn) -> dict:
    """
    Load data-derived TP/SL/lookahead from phase_params table.
    Falls back to PHASE_MODEL defaults for phases with insufficient data.
    Result is cached in-process with a 5-minute TTL so repeated calls
    within the same request do not hit the DB again, but stale entries
    are evicted in long-running processes.
    """
    cache_key = (symbol, exchange, timeframe)
    cached_at = _PHASE_PARAMS_CACHE_TS.get(cache_key, 0)
    if (
        cache_key in _PHASE_PARAMS_CACHE
        and (time.time() - cached_at) < _PHASE_PARAMS_CACHE_TTL
    ):
        return _PHASE_PARAMS_CACHE[cache_key]

    try:
        df = read_sql_safe(
            """
            SELECT market_phase, optimal_tp, optimal_sl, optimal_lookahead_min,
                   COALESCE(viable, TRUE) AS viable
            FROM phase_params
            WHERE symbol=%s AND exchange=%s AND timeframe=%s
        """,
            conn,
            params=[symbol, exchange, timeframe],
        )
    except Exception:
        # Table may not exist yet (first run before migration)
        df = pd.DataFrame()

    params = {}
    if not df.empty:
        for _, row in df.iterrows():
            params[row["market_phase"]] = {
                "tp": float(row["optimal_tp"]),
                "sl": float(row["optimal_sl"]),
                "lookahead_min": int(row["optimal_lookahead_min"]),
                # viable=False means the calibrated params failed cost-viability.
                # calc_strategy_outcomes will fall back to PHASE_MODEL defaults
                # rather than using unviable calibrated values.
                "viable": bool(row["viable"]) if "viable" in row.index else True,
            }

    _PHASE_PARAMS_CACHE[cache_key] = params
    _PHASE_PARAMS_CACHE_TS[cache_key] = time.time()
    return params


@strategy_bp.route("/api/offline/calibrate-phase-params", methods=["POST"])
def calibrate_phase_params():
    """
    Compute optimal TP, SL, and lookahead for every phase from historical
    MFE/MAE outcomes already stored in strategy_outcomes.

    HOW IT WORKS
    ---------------------------------------
    For each market_phase with >= MIN_SAMPLES rows:

      optimal_tp = p60(mfe_r)
        The 60th percentile of maximum favourable excursion in R-units.
        60% of historical trades reached this level --- using it as TP gives
        a ~60% TP hit rate which is consistent with profitable trading.
        p50 is too conservative (50% hit rate, low R:R).
        p75 is too greedy (25% hit rate, wins too small to offset losses).

      optimal_sl = abs(p25(mae_r))
        The 25th percentile of maximum adverse excursion (negated, in R-units).
        75% of historical trades never exceeded this drawdown --- so placing the
        stop here avoids stopping out 75% of eventually-profitable trades.
        p10 MAE is too tight --- stops out good trades.
        p40 MAE is too wide --- accepts too much heat.

      optimal_lookahead_min = p75(exit_after_candles) -- tf_min
        75th percentile of actual exit bar counts, converted to minutes.
        75% of trades resolve within this time window.

    CONSTRAINTS applied after derivation (keeps values execution-realistic):
      tp >= max(1.0, sl -- 1.3)     --- R:R at least 1.3 before costs
      sl between [0.5, 2.0]        --- not too tight, not irrationally wide
      lookahead_min between [15, 375] --- minimum 15 min, max 1 session

    BOOTSTRAP:
      First call: no data --- nothing written, returns empty dict.
      After first calc-strategy-outcomes run: data exists --- params computed.
      Second calc-strategy-outcomes run: reads params --- data-driven simulation.
      Self-improving: each run generates better outcomes --- better params.

    POST body: { "symbol": "RELIANCE", "exchange": "NSE", "timeframe": "3m" }
    """
    try:
        data = request.get_json() or {}
        symbol = (data.get("symbol") or "").upper().strip()
        exchange = (data.get("exchange") or "NSE").upper().strip()
        timeframe = (data.get("timeframe") or "").lower().strip()
        if not symbol or not timeframe:
            return jsonify({"error": "symbol and timeframe required"}), 400

        MIN_SAMPLES = int(data.get("min_samples", 30))
        TP_PERCENTILE = float(data.get("tp_percentile", 60))  # p60 of mfe_r
        SL_PERCENTILE = float(data.get("sl_percentile", 25))  # p25 of |mae_r|
        LA_PERCENTILE = float(data.get("la_percentile", 75))  # p75 of exit_after

        TF_MIN_MAP = {"1m": 1, "3m": 3, "5m": 5, "15m": 15}
        tf_min = TF_MIN_MAP.get(timeframe, 1)

        with get_db_conn() as conn:
            # Diagnostic: count total rows first so error message is specific
            total_df = read_sql_safe(
                """
                SELECT COUNT(*) AS total_rows,
                       COUNT(mfe_r) AS has_mfe_r,
                       COUNT(mae_r) AS has_mae_r,
                       COUNT(exit_after_candles) AS has_exit_after
                FROM strategy_outcomes
                WHERE symbol=%s AND exchange=%s AND timeframe=%s
            """,
                conn,
                params=[symbol, exchange, timeframe],
            )

            total_rows = (
                int(total_df.iloc[0]["total_rows"]) if not total_df.empty else 0
            )
            has_mfe = int(total_df.iloc[0]["has_mfe_r"]) if not total_df.empty else 0

            df = read_sql_safe(
                """
                SELECT market_phase,
                       mfe_r, mae_r,
                       exit_after_candles,
                       realized_r,
                       COALESCE(atr_14, 0)    AS atr_14,
                       COALESCE(cost_r,  0)   AS cost_r
                FROM strategy_outcomes
                WHERE symbol=%s AND exchange=%s AND timeframe=%s
                  AND mfe_r IS NOT NULL
                  AND mae_r IS NOT NULL
                  AND exit_after_candles IS NOT NULL
            """,
                conn,
                params=[symbol, exchange, timeframe],
            )

        if df.empty:
            if total_rows == 0:
                msg = (
                    f"No rows in strategy_outcomes for {symbol}/{timeframe}. "
                    "Most likely cause: calc-strategy-outcomes crashed before "
                    "inserting rows (e.g. missing DB column). "
                    "Run migration.sql, then re-run calc-strategy-outcomes."
                )
            elif has_mfe == 0:
                msg = (
                    f"{total_rows} rows exist but mfe_r is NULL in all of them. "
                    "Re-run calc-strategy-outcomes to populate outcome columns."
                )
            else:
                msg = (
                    f"{total_rows} total rows, {has_mfe} have mfe_r populated, "
                    "but none passed the NOT NULL filter. Re-run calc-strategy-outcomes."
                )
            return jsonify(
                {
                    "status": "NO_DATA",
                    "message": msg,
                    "total_rows": total_rows,
                    "phases": {},
                }
            )

        results = {}
        upsert_rows = []
        now = datetime.now(timezone.utc)

        for phase, grp in df.groupby("market_phase"):
            n = len(grp)
            if n < MIN_SAMPLES:
                results[phase] = {
                    "status": "INSUFFICIENT_DATA",
                    "samples": n,
                    "min_required": MIN_SAMPLES,
                    "fallback": "using PHASE_MODEL defaults",
                }
                continue

            # ------ Raw derivation ------------------------------------------------------------------------------------------------------
            mfe_r_vals = grp["mfe_r"].dropna()
            mae_r_vals = (
                grp["mae_r"].dropna().abs()
            )  # MAE is negative, work with magnitude
            exit_vals = grp["exit_after_candles"].dropna()

            p25_mfe = float(np.percentile(mfe_r_vals, 25))
            p50_mfe = float(np.percentile(mfe_r_vals, 50))
            p75_mfe = float(np.percentile(mfe_r_vals, 75))
            raw_tp = float(np.percentile(mfe_r_vals, TP_PERCENTILE))

            p25_mae = float(np.percentile(mae_r_vals, SL_PERCENTILE))
            raw_sl = p25_mae  # p25 of absolute MAE values

            p75_exit = float(np.percentile(exit_vals, LA_PERCENTILE))
            raw_la_min = max(15, int(round(p75_exit * tf_min)))

            win_rate = float((grp["realized_r"] > 0).mean())

            # ------ Apply constraints ---------------------------------------------------------------------------------------------------------------------------------
            # Distribution-derived bounds (data tells us the realistic range).
            #   SL floor = p5 of |mae_r| (never tighter than 5th-percentile adverse move)
            #   SL ceiling = p75 of |mae_r| (never wider than the typical adverse move)
            #   TP floor  = p5 of mfe_r (never less than minimum observed MFE)
            #   TP ceiling = p95 of mfe_r (cap at realistic upside, avoids overfitting)
            # TF-aware hard minimums layered on top (cost viability by timeframe):
            #   1m: tp_min_hard = 1.2  (1m ATR so small that costs dominate below this)
            #   3m: tp_min_hard = 0.9
            #   5m: tp_min_hard = 0.7
            #  15m: tp_min_hard = 0.6
            # RR_MIN = 1.3  (tp must be at least 1.3-- sl --- hard constraint 1)
            # Absolute safety rails: SL --- [0.3, 3.0], TP --- [0.5, 5.0]
            mae_p5 = float(np.percentile(mae_r_vals, 5))
            mae_p75 = float(np.percentile(mae_r_vals, 75))
            mfe_p5 = float(np.percentile(mfe_r_vals, 5))
            mfe_p95 = float(np.percentile(mfe_r_vals, 95))

            sl_floor = float(np.clip(mae_p5, 0.3, 1.0))
            sl_ceiling = float(np.clip(mae_p75, 0.8, 3.0))

            # TF-aware minimum TP --- ensures costs cannot exceed the gross TP move.
            # 1m trades have cost_r --- 1.3---1.5R, so TP < 1.2 is always net-negative.
            # 15m trades have cost_r --- 0.2---0.4R, so TP = 0.6 is still net-positive.
            _tp_min_hard = {"1m": 1.2, "3m": 0.9, "5m": 0.7, "15m": 0.6}.get(
                timeframe, 0.8
            )

            # tp_floor = max(data p5, sl*1.3, TF hard minimum)
            tp_floor = float(
                np.clip(max(mfe_p5, sl_floor * 1.3, _tp_min_hard), 0.5, 2.0)
            )
            tp_ceiling = float(np.clip(mfe_p95, 1.5, 5.0))

            sl = float(np.clip(raw_sl, sl_floor, sl_ceiling))
            # Constraint 1: tp >= max(tp_floor, sl -- 1.3)
            # This enforces minimum TP and minimum R:R simultaneously.
            tp = float(np.clip(max(raw_tp, sl * 1.3, tp_floor), tp_floor, tp_ceiling))

            # Lookahead: clip to [15, 375] minutes
            la_min = int(np.clip(raw_la_min, 15, 375))

            # ------ Constraint 2: Cost-aware viability ---------------------------------------------------------------------------
            # Use actual avg cost_r from outcomes data (available now that SELECT
            # includes cost_r). This is the real round-trip friction per R for
            # trades in this phase on this symbol/TF, not a proxy.
            # If the avg cost_r column is zero (old data, not yet populated),
            # fall back to estimating from avg ATR and entry price.
            avg_cost_r_data = (
                float(grp["cost_r"].mean())
                if "cost_r" in grp.columns and grp["cost_r"].notna().any()
                else 0.0
            )
            avg_atr_data = (
                float(grp["atr_14"].mean())
                if "atr_14" in grp.columns and grp["atr_14"].notna().any()
                else 0.0
            )

            if avg_cost_r_data > 0:
                # Real cost data from outcomes: use directly
                avg_cost_r = avg_cost_r_data
            elif avg_atr_data > 0:
                # Estimate: assume ---130 avg entry (rough mid-cap proxy)
                # cost_r = (entry -- TOTAL_COST_PCT) / (sl -- ATR)
                _est_entry = 130.0
                _est_R = sl * avg_atr_data
                avg_cost_r = (
                    (_est_entry * TOTAL_COST_PCT) / _est_R if _est_R > 0 else 9.99
                )
            else:
                # No data at all --- flag as unverifiable
                avg_cost_r = 0.0  # do not penalise if we cannot compute

            # Gross TP move after slippage (SLIPPAGE_PTS each side in ---, convert to R)
            # In R-units, each slippage tick = SLIPPAGE_PTS / (sl -- avg_ATR)
            slip_r = (
                (2 * SLIPPAGE_PTS / (sl * avg_atr_data)) if avg_atr_data > 0 else 0.0
            )
            net_tp = (
                tp - avg_cost_r - slip_r
            )  # what actually lands in your account at TP

            # ------ Four-part viability assessment ---------------------------------------------------------------------------------------
            # All four must pass for the phase to be considered VIABLE.
            # Informational only --- does NOT block the write to phase_params.
            # calc_strategy_outcomes respects viable=False: falls back to
            # PHASE_MODEL defaults so unviable calibrated params are not used.

            # 1. Minimum R:R (gross) --- tp must be at least RR_MIN -- sl
            rr_ok = (tp / sl) >= 1.3
            # 2. Net TP after costs must be positive --- i.e., TP covers friction
            net_tp_ok = net_tp > 0.0
            # 3. Minimum win rate --- below this, even a perfect R:R cannot save it
            #    Minimum win rate for breakeven: sl / (tp + sl)
            breakeven_wr = sl / (tp + sl)
            wr_ok = (
                win_rate >= breakeven_wr * 0.80
            )  # allow 20% below theoretical breakeven
            # 4. Minimum expectancy --- expected R should not be deeply negative
            #    (allow slightly negative; ML will filter within the phase)
            exp_r = win_rate * tp - (1.0 - win_rate) * sl
            exp_ok = exp_r > -0.5  # deep negative --- useless for training

            viable = rr_ok and net_tp_ok and wr_ok and exp_ok

            # Build human-readable failure reasons for diagnostics
            failure_reasons = []
            if not rr_ok:
                failure_reasons.append(f"R:R={tp/sl:.2f}x < 1.3")
            if not net_tp_ok:
                failure_reasons.append(
                    f"net_tp={net_tp:.3f}R --- 0 (cost={avg_cost_r:.3f}R)"
                )
            if not wr_ok:
                failure_reasons.append(
                    f"win_rate={win_rate:.1%} < breakeven {breakeven_wr:.1%}"
                )
            if not exp_ok:
                failure_reasons.append(f"exp_r={exp_r:.3f}R < -0.5")
            note = "; ".join(failure_reasons) if failure_reasons else ""

            results[phase] = {
                "status": "CALIBRATED",
                "samples": n,
                "optimal_tp": round(tp, 3),
                "optimal_sl": round(sl, 3),
                "optimal_la_min": la_min,
                "gross_rr": round(tp / sl, 2),
                "net_tp_r": round(net_tp, 3),
                "avg_cost_r": round(avg_cost_r, 3),
                "exp_r": round(exp_r, 3),
                "breakeven_wr": round(breakeven_wr, 3),
                "win_rate": round(win_rate, 3),
                "p25_mfe_r": round(p25_mfe, 3),
                "p50_mfe_r": round(p50_mfe, 3),
                "p75_mfe_r": round(p75_mfe, 3),
                "p25_mae_r": round(p25_mae, 3),
                "p75_exit_candles": int(p75_exit),
                "viable": viable,
                "note": note,
            }

            upsert_rows.append(
                (
                    symbol,
                    exchange,
                    timeframe,
                    phase,
                    float(tp),
                    float(sl),
                    int(la_min),
                    int(n),
                    float(win_rate),
                    float(mfe_r_vals.mean()),
                    float(-mae_r_vals.mean()),
                    float(p25_mfe),
                    float(p50_mfe),
                    float(p75_mfe),
                    float(-p25_mae),
                    int(p75_exit),
                    bool(
                        viable
                    ),  # Constraint 2: written to DB so _load_phase_params can filter
                    now,
                )
            )

        # ------ Upsert into phase_params ------------------------------------------------------------------------------------
        if upsert_rows:
            with get_db_conn() as conn:
                with conn.cursor() as cur:
                    _chunk_execute(
                        cur,
                        """
                        INSERT INTO phase_params (
                            symbol,exchange,timeframe,market_phase,
                            optimal_tp,optimal_sl,optimal_lookahead_min,
                            samples,win_rate,avg_mfe_r,avg_mae_r,
                            p25_mfe_r,p50_mfe_r,p75_mfe_r,p25_mae_r,
                            p75_exit_after,viable,computed_at
                        ) VALUES %s
                        ON CONFLICT (symbol,exchange,timeframe,market_phase)
                        DO UPDATE SET
                            optimal_tp=EXCLUDED.optimal_tp,
                            optimal_sl=EXCLUDED.optimal_sl,
                            optimal_lookahead_min=EXCLUDED.optimal_lookahead_min,
                            samples=EXCLUDED.samples,
                            win_rate=EXCLUDED.win_rate,
                            avg_mfe_r=EXCLUDED.avg_mfe_r,
                            avg_mae_r=EXCLUDED.avg_mae_r,
                            p25_mfe_r=EXCLUDED.p25_mfe_r,
                            p50_mfe_r=EXCLUDED.p50_mfe_r,
                            p75_mfe_r=EXCLUDED.p75_mfe_r,
                            p25_mae_r=EXCLUDED.p25_mae_r,
                            p75_exit_after=EXCLUDED.p75_exit_after,
                            viable=EXCLUDED.viable,
                            computed_at=EXCLUDED.computed_at
                    """,
                        upsert_rows,
                    )

        # Invalidate in-process cache so next calc run picks up new values
        _PHASE_PARAMS_CACHE.pop((symbol, exchange, timeframe), None)
        _PHASE_PARAMS_CACHE_TS.pop((symbol, exchange, timeframe), None)

        calibrated = sum(1 for v in results.values() if v.get("status") == "CALIBRATED")
        viable_count = sum(1 for v in results.values() if v.get("viable") is True)
        unviable_count = sum(1 for v in results.values() if v.get("viable") is False)
        skipped = len(results) - calibrated

        return jsonify(
            {
                "status": "SUCCESS",
                "symbol": symbol,
                "timeframe": timeframe,
                "phases_calibrated": calibrated,
                "phases_viable": viable_count,
                "phases_unviable": unviable_count,
                "phases_unviable_note": "unviable phases fall back to PHASE_MODEL defaults in simulation",
                "phases_skipped_insufficient_data": skipped,
                "tp_percentile": TP_PERCENTILE,
                "sl_percentile": SL_PERCENTILE,
                "la_percentile": LA_PERCENTILE,
                "phases": results,
            }
        )

    except Exception:
        traceback.print_exc()
        return jsonify({"error": traceback.format_exc()}), 500


# ------ Strategy outcomes ------------------------------------------------------------------------------------------------------------------------------------
@strategy_bp.route("/api/offline/calc-strategy-outcomes", methods=["POST"])
def calc_strategy_outcomes():
    try:
        t0 = time.time()
        data = request.get_json() or {}
        symbol = (data.get("symbol") or "").upper().strip()
        timeframe = (data.get("timeframe") or "").lower().strip()
        exchange = (data.get("exchange") or "NSE").upper().strip()
        to_dt = pd.to_datetime(
            data.get("to_date") or datetime.now(timezone.utc), utc=True
        )
        # Default from_date: all available data --- NOT hardcoded 180 days.
        # The 180-day default silently dropped older labelled bars from outcome
        # simulation whenever label-market-context had been run on > 6 months.
        # Use from_date explicitly in the request to restrict the window.
        # For ML training you want ALL outcomes, not just the last 6 months.
        from_dt = pd.to_datetime(data.get("from_date") or "2000-01-01", utc=True)

        # cost_r_gate: skip trades where round-trip costs exceed this fraction of R.
        # Default 0.70 --- costs must not exceed 70% of 1R. Pass 1.0 to disable.
        cost_r_gate = float(data.get("cost_r_gate", COST_R_MAX_GATE))

        if not symbol or not timeframe:
            return jsonify({"error": "symbol and timeframe required"}), 400

        with get_db_conn() as conn:
            df = read_sql_safe(
                """
                SELECT i.ts,i.open,i.high,i.low,i.close,i.atr_14,
                       mc.market_phase,mc.minute_of_day,
                       mc.ema_21_slope,mc.vwap_dist_pct,mc.range_efficiency,
                       COALESCE(mc.macro_regime,     'NEUTRAL_MACRO') AS macro_regime,
                       COALESCE(mc.price_structure,  'NEUTRAL')       AS price_structure,
                       COALESCE(mc.trend_exhaustion, 0)               AS trend_exhaustion,
                       COALESCE(mc.gap_atr,          0)               AS gap_atr,
                       COALESCE(mc.minute_of_day,    0)               AS minute_of_day_mc,
                       mc.impulse_dir
                FROM indicators i
                JOIN market_context mc
                  ON i.symbol=mc.symbol AND i.exchange=mc.exchange
                 AND i.timeframe=mc.timeframe AND i.ts=mc.ts
                WHERE i.symbol=%s AND i.exchange=%s AND i.timeframe=%s
                  AND i.ts BETWEEN %s AND %s
                ORDER BY i.ts
            """,
                conn,
                params=[symbol, exchange, timeframe, from_dt, to_dt],
            )

            if df.empty:
                return (
                    jsonify(
                        {"error": "No data found --- run label-market-context first"}
                    ),
                    400,
                )

            df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
            df = df.sort_values("ts").reset_index(drop=True)

            # Query 1: rule eligibility flags only --- no JSON blobs loaded.
            # condition_snapshot is intentionally excluded; orb_quality/orb_location
            # are extracted directly by Query 2 using SQL JSON operators.
            rules_df = read_sql_safe(
                """
                SELECT ts, strategy_id, rule_eligibility
                FROM rule_evaluations
                WHERE symbol=%s AND exchange=%s AND timeframe=%s
                  AND ts BETWEEN %s AND %s
            """,
                conn,
                params=[symbol, exchange, timeframe, from_dt, to_dt],
            )

            # Query 2: extract only the two fields actually used from condition_snapshot.
            # Parsing all JSON blobs in Python caused MemoryError on large datasets
            # (~445k rows -- full JSON dict = OOM). SQL ->> operator streams just the
            # two integer fields needed, avoiding any Python-side JSON parsing.
            orb_snaps_df = read_sql_safe(
                """
                SELECT ts,
                       COALESCE((condition_snapshot->>'orb_quality')::int,  0) AS orb_quality,
                       COALESCE((condition_snapshot->>'orb_location')::int, 0) AS orb_location
                FROM rule_evaluations
                WHERE symbol=%s AND exchange=%s AND timeframe=%s
                  AND ts BETWEEN %s AND %s
                  AND strategy_id = 'ORB'
                  AND condition_snapshot IS NOT NULL
            """,
                conn,
                params=[symbol, exchange, timeframe, from_dt, to_dt],
            )

        # ------ IMPROVEMENT 6: timezone-safe rule_truth lookup ---------------------
        rules_df["ts"] = pd.to_datetime(rules_df["ts"], errors="coerce")
        # Normalise both sides to UTC-naive for reliable dict key matching
        if rules_df["ts"].dt.tz is not None:
            rules_df["ts"] = rules_df["ts"].dt.tz_localize(None)
        if df["ts"].dt.tz is not None:
            df["ts"] = df["ts"].dt.tz_localize(None)

        rules_df["strategy_id"] = rules_df["strategy_id"].str.upper().str.strip()
        rule_truth = (
            rules_df.drop_duplicates(["ts", "strategy_id"], keep="last")
            .set_index(["ts", "strategy_id"])["rule_eligibility"]
            .to_dict()
        )

        # Build snapshots dict from the lightweight ORB-only query.
        # Keys are tz-naive datetimes to match rule_truth lookup convention.
        if not orb_snaps_df.empty:
            orb_snaps_df["ts"] = pd.to_datetime(orb_snaps_df["ts"], errors="coerce")
            if orb_snaps_df["ts"].dt.tz is not None:
                orb_snaps_df["ts"] = orb_snaps_df["ts"].dt.tz_localize(None)
            snapshots = (
                orb_snaps_df.drop_duplicates("ts")
                .set_index("ts")[["orb_quality", "orb_location"]]
                .to_dict("index")
            )
        else:
            snapshots = {}

        # ------ IMPROVEMENT 4: vectorized exit simulation ------------------------------------
        highs = df["high"].to_numpy(dtype=float)
        lows = df["low"].to_numpy(dtype=float)
        closes = df["close"].to_numpy(dtype=float)
        opens = df["open"].to_numpy(dtype=float)  # FIX 3: next-bar entry
        atrs = df["atr_14"].to_numpy(dtype=float)
        phases = df["market_phase"].tolist()
        ts_arr = df["ts"].values
        N = len(df)

        # ------ FIX 7: Context arrays for FOLLOW/FADE/MEAN/BREAKOUT resolution ------
        gap_atr_col = (
            df["gap_atr"].to_numpy(dtype=float)
            if "gap_atr" in df.columns
            else np.zeros(N)
        )
        ema_slope_col = df["ema_21_slope"].to_numpy(dtype=float)
        vwap_dist_col = df["vwap_dist_pct"].to_numpy(dtype=float)
        # impulse_dir: the most recent impulse direction stored by label-market-context
        # Falls back to None-array; resolved inside the loop per bar.
        impulse_dir_col = (
            df["impulse_dir"].tolist() if "impulse_dir" in df.columns else [None] * N
        )

        # ------ FIX 18-20: Market behaviour execution gates ---------------------------------
        # These columns are produced by label-market-context and stored
        # in market_context. They enforce market-context awareness at
        # the simulation layer --- preventing entry in adverse regimes.
        macro_arr = df["macro_regime"].tolist()  # BULL_MACRO/BEAR_MACRO/NEUTRAL_MACRO
        ps_arr = df["price_structure"].tolist()  # BULL/BEAR/TRANSITION/NEUTRAL
        exhaust_arr = df["trend_exhaustion"].to_numpy(dtype=int)  # 0/1
        # BUG 6 FIX: bar_of_day needed to exempt gap phases from confirmation gate
        TF_MIN_BAR = {"1m": 1, "3m": 3, "5m": 5, "15m": 15}
        _tf_min_bar = TF_MIN_BAR.get(timeframe, 1)
        bar_of_day_arr = (
            (df["minute_of_day_mc"] / _tf_min_bar).to_numpy(dtype=int)
            if "minute_of_day_mc" in df.columns
            else np.zeros(N, dtype=int)
        )

        # ------ v28: Intraday EOD gate ------------------------------------------------------------------------------------------------
        # Phases with lookahead_min >= 45 min must not be entered in the
        # last 60 minutes of the session (minute_of_day >= 315 on 15m =
        # after 14:30 IST). Past 14:30, only 1-2 bars remain before close
        # and exits almost always hit TIME_EXIT with unfavourable marks.
        # _EOD_BOD_THRESHOLD: bar_of_day index at which the gate applies.
        #   15m: (375 - 60) / 15 = 21   --- gate fires at bar_of_day >= 21
        #    1m: (375 - 60) /  1 = 315  --- gate fires at bar_of_day >= 315
        _EOD_BOD_THRESHOLD = max(0, (375 - 60) // _tf_min_bar)
        _EOD_LA_MIN_GATE = 45  # only phases needing >= 45 min runway
        n_eod_skipped = 0

        # ------ v28: Minimum rules fired gate ------------------------------------------------------------------------
        # Configurable via request body param "min_rules_fired" (default 0 = off).
        # Set to 2 for a quality filter; set to 5 to restrict to the all-rules
        # combo which had WR=43.8% in the 15m outcome analysis.
        min_rules_fired = int(data.get("min_rules_fired", 0))
        RULE_IDS = (
            "ORB",
            "EMA_TREND",
            "ATR_EXPANSION",
            "VWAP_TREND",
            "VOLUME_EXPANSION",
        )
        n_rules_skipped = 0
        _ts_rule_count: dict = {}
        if min_rules_fired > 0:
            for (_ts_key, _rid), _val in rule_truth.items():
                if _val and _rid in RULE_IDS:
                    _ts_rule_count[_ts_key] = _ts_rule_count.get(_ts_key, 0) + 1

        # ------ TF resolution for lookahead conversion ------------------------------------------------
        TF_MIN_MAP = {"1m": 1, "3m": 3, "5m": 5, "15m": 15}
        tf_min_val = TF_MIN_MAP.get(timeframe, 1)

        # ------ Load data-derived params (if calibrated) ------------------------------------------
        # calibrate-phase-params must have been run at least once to
        # populate phase_params table. If not run yet, or if a phase
        # has < MIN_SAMPLES, falls back to PHASE_MODEL hardcoded values.
        #
        # This implements the self-improving loop:
        #   1st run: PHASE_MODEL defaults --- outcomes written to DB
        #   calibrate-phase-params: derives optimal tp/sl/la from outcomes
        #   2nd run: data-derived params --- better outcome measurement
        #   Repeat: params converge toward true market behaviour
        with get_db_conn() as conn:
            data_params = _load_phase_params(symbol, exchange, timeframe, conn)

        # Pre-compute effective params per phase (data-derived > hardcoded)
        # Also compute lookahead bars (min 2, max 375)
        _la_cache = {}
        _cfg_cache = {}
        for phase_name, default_cfg in PHASE_MODEL.items():
            if phase_name in data_params:
                dp = data_params[phase_name]
                # Respect viable=False --- if calibration determined the params
                # are cost-unviable (net_tp <= 0, or R:R < 1.3, or deeply
                # negative expectancy), fall back to PHASE_MODEL defaults.
                # Calibrated but unviable params are WORSE than hardcoded defaults
                # because they overfit to a single symbol/period's distribution
                # without meeting the minimum edge threshold.
                if not dp.get("viable", True):
                    effective_cfg = dict(default_cfg)
                    effective_cfg["source"] = "default_unviable_fallback"
                else:
                    effective_cfg = {
                        "dir": default_cfg["dir"],  # direction never overridden
                        "tp": dp["tp"],
                        "sl": dp["sl"],
                        "lookahead_min": dp["lookahead_min"],
                        "source": "calibrated",
                    }
            else:
                # No calibrated params --- use PHASE_MODEL defaults
                effective_cfg = dict(default_cfg)
                effective_cfg["source"] = "default"

            la_min = effective_cfg.get("lookahead_min", 30)
            # FIX 8: use ceil not floor. 20 min on 15m --- floor=1 bar (wrong), ceil=2 (correct).
            # Calibrated la_min = p75_exit*tf_min is always divisible so ceil==floor there.
            # Only affects PHASE_MODEL defaults where la_min may not divide evenly by tf_min.
            la_bars = max(2, min(375, math.ceil(la_min / tf_min_val)))
            _la_cache[phase_name] = la_bars
            _cfg_cache[phase_name] = effective_cfg

        rows = []
        now = datetime.now(timezone.utc)
        n_calibrated = sum(
            1 for c in _cfg_cache.values() if c.get("source") == "calibrated"
        )
        n_unviable_fallback = sum(
            1
            for c in _cfg_cache.values()
            if c.get("source") == "default_unviable_fallback"
        )
        n_cost_skipped = 0  # tracks trades skipped by cost_r gate

        for i in range(N):
            cfg = _cfg_cache.get(phases[i])  # data-derived or hardcoded fallback
            if not cfg:
                continue
            la = _la_cache.get(phases[i], 2)
            if i + la + 2 >= N:
                continue
            atr = atrs[i]
            if atr <= 0:
                continue

            # FIX 3: Use open of next bar as entry --- not close of signal bar.
            # Close of bar i is unknowable until bar i closes; a live system
            # can only fill at bar i+1 open. Using closes[i] creates systematic
            # look-ahead bias: every trade has a slightly better entry than live.
            raw_entry = opens[i + 1] if i + 1 < N else closes[i]  # next bar open

            # ------ FIX 7: Resolve abstract direction tokens to LONG/SHORT ------
            # FOLLOW, FADE, MEAN, BREAKOUT, NEUTRAL were silently treated as
            # is_short=False (always LONG). This was wrong --- GAP_TIMEOUT
            # "FOLLOW"s the gap direction (could be SHORT), GAP_CONTINUATION
            # follows the impulse direction, FADE is the OPPOSITE of the
            # last impulse. Using the wrong direction poisons all these outcomes.
            #
            # Resolution logic (uses bar i context --- no lookahead):
            #   FOLLOW    --- follow the gap direction (gap_atr > 0 --- LONG, < 0 --- SHORT)
            #               falls back to EMA slope if gap_atr == 0
            #   FADE      --- opposite of last impulse direction (impulse_dir array)
            #               falls back to opposite of EMA slope
            #   MEAN      --- whichever side price is currently on vs VWAP
            #               (above VWAP --- expect revert --- SHORT; below --- LONG)
            #   BREAKOUT  --- follow EMA slope (momentum direction at bar i)
            #   NEUTRAL   --- skip (no directional bet possible)
            raw_dir = cfg["dir"]
            if raw_dir == "SHORT":
                is_short = True
            elif raw_dir == "LONG":
                is_short = False
            elif raw_dir == "FOLLOW":
                # gap_atr_col: > 0 gap up --- follow up (LONG); < 0 gap down --- follow down (SHORT)
                gap_a = gap_atr_col[i]
                if gap_a > 0:
                    is_short = False
                elif gap_a < 0:
                    is_short = True
                else:
                    # No gap context --- fall back to EMA slope
                    is_short = ema_slope_col[i] < 0
            elif raw_dir == "FADE":
                # FADE = trade opposite to the most recent impulse direction
                last_impl = impulse_dir_col[i]
                if last_impl == "BULL":
                    is_short = True  # fade the bull impulse --- short
                elif last_impl == "BEAR":
                    is_short = False  # fade the bear impulse --- long
                else:
                    # No impulse context --- fade the EMA slope direction
                    is_short = ema_slope_col[i] > 0
            elif raw_dir == "MEAN":
                # Mean-revert: price above VWAP --- expect pull-down --- SHORT
                #              price below VWAP --- expect bounce  --- LONG
                is_short = vwap_dist_col[i] > 0
            elif raw_dir == "BREAKOUT":
                # Follow momentum direction at bar i
                is_short = ema_slope_col[i] < 0
            else:
                # NEUTRAL or unknown --- no directional bet
                continue

            # ------ FIX 18: Macro regime gate ---------------------------------------------------------------------------------------
            # Do not take LONG trades in a structural BEAR_MACRO market,
            # and do not take SHORT trades in a structural BULL_MACRO market.
            # Directionless (NEUTRAL, MEAN, FOLLOW, BREAKOUT, FADE) bypass this gate.
            macro = macro_arr[i]
            if is_short and macro == "BULL_MACRO":
                continue
            if not is_short and cfg["dir"] == "LONG" and macro == "BEAR_MACRO":
                continue

            # ------ FIX 19: Price structure alignment gate ------------------------------------------------
            # For TREND_CONTINUATION and BEAR_TREND_CONTINUATION, the
            # swing structure must agree with the trade direction.
            # A bull trend entry in BEAR or TRANSITION structure means
            # the higher-timeframe swing series disagrees --- skip it.
            ps = ps_arr[i]
            phase_name_i = phases[i]
            if phase_name_i == "TREND_CONTINUATION" and ps in ("BEAR", "TRANSITION"):
                continue
            if phase_name_i == "BEAR_TREND_CONTINUATION" and ps in (
                "BULL",
                "TRANSITION",
            ):
                continue

            # ------ FIX 20: Trend exhaustion gate ---------------------------------------------------------------------------
            # Skip TREND_CONTINUATION / BEAR_TREND_CONTINUATION when trend is
            # exhausted: MACD histogram shrinking for 2+ bars AND RSI extreme.
            # Prevents entering at the tail of an already-tired move.
            if exhaust_arr[i] == 1 and phase_name_i in (
                "TREND_CONTINUATION",
                "BEAR_TREND_CONTINUATION",
            ):
                continue

            # ------ FIX 1: Directional confirmation gate ------------------------------------------------------
            # Require the signal bar itself to close in the trade direction.
            # This is a lightweight entry quality filter --- not a full pullback
            # model --- but it eliminates the most dangerous case: entering a
            # SHORT when the signal bar closed bullish (price ran up into you).
            #
            # The full pullback model (wait for VWAP retest / green candle) needs
            # clean post-SHORT-fix outcome data to calibrate thresholds.
            # This gate is the minimum safe version: bar must close directionally.
            #
            # Applied only to directional phases (LONG/SHORT/FOLLOW/FADE).
            # MEAN/BREAKOUT/NEUTRAL: no directional assumption --- gate skipped.
            #
            # Not applied to GAP phases (bar_of_day==0): gap bars often open
            # against direction before resolving --- filtering them here would
            # eliminate the entire gap auction edge.
            # BUG 6 FIX: skip gate on bar_of_day==0 (gap opening bars)
            # Gap bars often open against direction before resolving ---
            # filtering them here would eliminate the entire gap auction edge.
            if (
                raw_dir in ("LONG", "SHORT", "FOLLOW", "FADE")
                and bar_of_day_arr[i] != 0
            ):
                bar_close = closes[i]
                bar_open = opens[i]
                if is_short and bar_close >= bar_open:
                    continue  # signal bar closed bullish --- adverse for short
                if not is_short and bar_close <= bar_open:
                    continue  # signal bar closed bearish --- adverse for long

            # ------ FIX 4: Cost viability gate ------------------------------------------------------------------------------------
            # Compute cost_r at the raw_entry price before spending time on
            # full exit simulation. If costs consume more than 70% of 1R,
            # the trade has no realistic positive-expectancy path regardless
            # of accuracy. Skip it immediately.
            #
            # cost_r = (entry -- TOTAL_COST_PCT) / R
            # R = sl_multiple -- ATR
            # Threshold 0.7 means: net TP must be at least 0.3R above entry.
            # This naturally eliminates most 1m trades (cost_r --- 1.3---1.5R)
            # while keeping 15m trades (cost_r --- 0.2---0.4R) intact.
            _R_preview = cfg["sl"] * atr
            if _R_preview > 0:
                _cost_r_preview = (raw_entry * TOTAL_COST_PCT) / _R_preview
                if _cost_r_preview > cost_r_gate:
                    n_cost_skipped += 1
                    continue

            # ------ v28: EOD gate ---------------------------------------------------------------------------------------------------------------
            # Skip entries for slow phases (lookahead_min >= _EOD_LA_MIN_GATE)
            # when we are in the last 60 min of the session.
            if (
                _EOD_LA_MIN_GATE > 0
                and bar_of_day_arr[i] >= _EOD_BOD_THRESHOLD
                and effective_cfg.get("lookahead_min", 0) >= _EOD_LA_MIN_GATE
            ):
                n_eod_skipped += 1
                continue

            # ------ v28: Minimum rules fired gate ---------------------------------------------------------------
            if min_rules_fired > 0:
                ts_obj_check = pd.Timestamp(ts_arr[i])
                if ts_obj_check.tz is not None:
                    ts_obj_check = ts_obj_check.tz_localize(None)
                _rc = _ts_rule_count.get(
                    ts_obj_check.to_pydatetime(), _ts_rule_count.get(ts_obj_check, 0)
                )
                if _rc < min_rules_fired:
                    n_rules_skipped += 1
                    continue

            # ------ Slippage-adjusted entry ---------------------------------------------------------------------------------
            # Long : market order fills ABOVE the open (buying pressure)
            # Short: market order fills BELOW the open (selling pressure)
            entry = (
                raw_entry + SLIPPAGE_PTS if not is_short else raw_entry - SLIPPAGE_PTS
            )

            # ------ TP and SL from slippage-adjusted entry ------------------------------------
            # TP exit also has slippage working against you:
            #   Long  exit: you sell slightly BELOW your TP target
            #   Short exit: you buy  slightly ABOVE your TP target
            # SL is assumed to fill exactly at SL price (worst-case market order).
            if is_short:
                tp = (
                    entry - cfg["tp"] * atr + SLIPPAGE_PTS
                )  # sell TP fills higher (worse)
                sl = entry + cfg["sl"] * atr  # buy stop fills at SL
            else:
                tp = (
                    entry + cfg["tp"] * atr - SLIPPAGE_PTS
                )  # sell TP fills lower (worse)
                sl = entry - cfg["sl"] * atr  # stop loss fills at SL

            # Exit simulation starts from bar i+2 (first full bar after entry)
            exit_reason, exit_price, exit_after, mfe, mae = _simulate_exit_vectorized(
                entry,
                tp,
                sl,
                highs[i + 2 : i + 2 + la],
                lows[i + 2 : i + 2 + la],
                closes[i + 2 : i + 2 + la],
                la,
                is_short=is_short,  # FIX 14: direction-aware exit
            )

            ts = ts_arr[i]
            R = abs(entry - sl)  # risk in price points
            if R <= 0:
                continue

            mfe_r = mfe / R
            mae_r = mae / R

            # ------ Gross R (price movement only, no costs) ---------------------------------
            if exit_reason == "TP_HIT":
                # TP is already slippage-adjusted --- use actual distance
                # For LONG: tp > entry --- positive. For SHORT: entry > tp --- positive.
                realized_r_gross = abs(tp - entry) / R
            elif exit_reason == "SL_HIT":
                # SL is exactly -1R by construction for both directions
                realized_r_gross = -1.0
            else:
                # TIME_EXIT: mark-to-market on last bar close
                if is_short:
                    raw_pnl = entry - exit_price  # profit when price falls
                else:
                    raw_pnl = exit_price - entry  # profit when price rises
                realized_r_gross = raw_pnl / R

            # ------ Transaction cost in R-units ---------------------------------------------------------------------
            # Percentage costs scale with entry price (per share).
            # Slippage is already embedded in entry and tp above.
            # cost_r tells ML exactly how much edge is consumed by friction.
            cost_pts = entry * TOTAL_COST_PCT  # --- cost per share, round trip
            cost_r = cost_pts / R  # expressed as fraction of 1R

            # ------ Net R (what lands in your account after all costs) ---
            realized_r_net = realized_r_gross - cost_r

            exit_speed = exit_after / la
            timing = (
                "FAST"
                if exit_speed <= 0.33
                else "NORMAL" if exit_speed <= 0.66 else "LATE"
            )

            # Convert and STRIP timezone so dictionary lookups work perfectly
            ts_obj = pd.Timestamp(ts)
            if ts_obj.tz is not None:
                ts_obj = ts_obj.tz_localize(None)
            ts_py = ts_obj.to_pydatetime()
            ts = ts_obj  # Update original ts variable for the secondary lookup too
            snap = snapshots.get(ts_py, snapshots.get(ts, {}))

            row_mc = df.iloc[i]

            def rt(key):
                return bool(
                    rule_truth.get((ts_py, key), rule_truth.get((ts, key), False))
                )

            rows.append(
                (
                    symbol,
                    exchange,
                    timeframe,
                    ts_py,  # Python datetime
                    str(phases[i]),  # market_phase
                    int(row_mc.minute_of_day),  # Python int
                    rt("ORB"),
                    rt("EMA_TREND"),
                    rt("ATR_EXPANSION"),
                    rt("VWAP_TREND"),
                    rt("VOLUME_EXPANSION"),
                    float(row_mc.ema_21_slope),  # Python float
                    float(row_mc.vwap_dist_pct),
                    float(atr),
                    float(row_mc.range_efficiency),
                    int(snap.get("orb_quality", 0)),
                    int(snap.get("orb_location", 0)),
                    # Per-rule outcomes stored as NET R so rules are evaluated
                    # after realistic friction --- prevents overstating edge.
                    float(realized_r_net) if rt("ORB") else None,
                    float(realized_r_net) if rt("EMA_TREND") else None,
                    float(realized_r_net) if rt("ATR_EXPANSION") else None,
                    float(realized_r_net) if rt("VWAP_TREND") else None,
                    float(realized_r_net) if rt("VOLUME_EXPANSION") else None,
                    str(exit_reason),  # str
                    pd.Timestamp(
                        ts_arr[i + 1 + int(exit_after)]
                    ).to_pydatetime(),  # exit_ts
                    float(mfe),
                    float(mae),
                    int(la),  # Python int
                    now,
                    float(mfe_r),
                    float(mae_r),
                    float(realized_r_net),  # realized_r = NET (after all costs)
                    int(exit_after),  # Python int
                    float(exit_speed),
                    str(timing),  # str
                    float(realized_r_gross),  # gross R before transaction costs
                    float(cost_r),  # cost drag in R-units
                )
            )

        if not rows:
            return (
                jsonify(
                    {"error": "No outcomes generated --- check PHASE_MODEL coverage"}
                ),
                400,
            )

        OUTCOME_SQL = """
            INSERT INTO strategy_outcomes (
                symbol,exchange,timeframe,ts,market_phase,minute_of_day,
                orb_fired,ema_trend_fired,atr_expansion_fired,
                vwap_trend_fired,volume_expansion_fired,
                ema_21_slope,vwap_dist_pct,atr_14,range_efficiency,
                orb_quality,orb_location,
                orb_outcome,ema_trend_outcome,atr_expansion_outcome,
                vwap_trend_outcome,volume_expansion_outcome,
                exit_reason,exit_ts,mfe,mae,lookahead_candles,created_at,
                mfe_r,mae_r,realized_r,exit_after_candles,exit_speed_ratio,outcome_timing,
                realized_r_gross,cost_r
            ) VALUES %s
            ON CONFLICT (symbol,exchange,timeframe,ts) DO UPDATE SET
                market_phase=EXCLUDED.market_phase,
                minute_of_day=EXCLUDED.minute_of_day,
                orb_fired=EXCLUDED.orb_fired,
                ema_trend_fired=EXCLUDED.ema_trend_fired,
                atr_expansion_fired=EXCLUDED.atr_expansion_fired,
                vwap_trend_fired=EXCLUDED.vwap_trend_fired,
                volume_expansion_fired=EXCLUDED.volume_expansion_fired,
                ema_21_slope=EXCLUDED.ema_21_slope,
                vwap_dist_pct=EXCLUDED.vwap_dist_pct,
                atr_14=EXCLUDED.atr_14,
                range_efficiency=EXCLUDED.range_efficiency,
                orb_quality=EXCLUDED.orb_quality,
                orb_location=EXCLUDED.orb_location,
                orb_outcome=EXCLUDED.orb_outcome,
                ema_trend_outcome=EXCLUDED.ema_trend_outcome,
                atr_expansion_outcome=EXCLUDED.atr_expansion_outcome,
                vwap_trend_outcome=EXCLUDED.vwap_trend_outcome,
                volume_expansion_outcome=EXCLUDED.volume_expansion_outcome,
                exit_reason=EXCLUDED.exit_reason,
                exit_ts=EXCLUDED.exit_ts,
                mfe=EXCLUDED.mfe,
                mae=EXCLUDED.mae,
                lookahead_candles=EXCLUDED.lookahead_candles,
                mfe_r=EXCLUDED.mfe_r,
                mae_r=EXCLUDED.mae_r,
                realized_r=EXCLUDED.realized_r,
                exit_after_candles=EXCLUDED.exit_after_candles,
                exit_speed_ratio=EXCLUDED.exit_speed_ratio,
                outcome_timing=EXCLUDED.outcome_timing,
                realized_r_gross=EXCLUDED.realized_r_gross,
                cost_r=EXCLUDED.cost_r,
                created_at=EXCLUDED.created_at
        """

        with get_db_conn() as conn:
            with conn.cursor() as cur:
                _chunk_execute(cur, OUTCOME_SQL, rows)

        elapsed = round(time.time() - t0, 1)
        return jsonify(
            {
                "status": "SUCCESS",
                "rows_written": len(rows),
                "elapsed_sec": elapsed,
                "phases_calibrated": n_calibrated,
                "phases_default": len(_cfg_cache) - n_calibrated - n_unviable_fallback,
                "phases_unviable_fallback": n_unviable_fallback,
                "param_source": "calibrated" if n_calibrated > 0 else "default",
                "cost_r_gate": cost_r_gate,
                "skipped_by_cost": n_cost_skipped,
                "pct_skipped_by_cost": round(n_cost_skipped / max(1, N) * 100, 1),
                # v28 new gate stats
                "skipped_by_eod": n_eod_skipped,
                "skipped_by_min_rules": n_rules_skipped,
                "min_rules_fired": min_rules_fired,
            }
        )

    except Exception:
        traceback.print_exc()
        return jsonify({"error": traceback.format_exc()}), 500


# ------ Rule stats ---------------------------------------------------------------------------------------------------------------------------------------------------------
@strategy_bp.route("/api/market-context/rule-stats", methods=["GET"])
def get_rule_stats():
    symbol = (request.args.get("symbol") or "").upper().strip()
    timeframe = (request.args.get("timeframe") or "").lower().strip()
    if not symbol or not timeframe:
        return jsonify({"error": "symbol and timeframe required"}), 400

    with get_db_conn() as conn:
        df = read_sql_safe(
            """
            SELECT ts, orb_outcome, ema_trend_outcome AS ema_outcome,
                   atr_expansion_outcome AS atr_outcome,
                   vwap_trend_outcome AS vwap_outcome,
                   volume_expansion_outcome AS bb_outcome,
                   exit_reason
            FROM strategy_outcomes
            WHERE symbol=%s AND timeframe=%s
            ORDER BY ts
        """,
            conn,
            params=[symbol, timeframe],
        )

    if df.empty:
        return jsonify(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "test_period": None,
                "months_tested": 0,
                "rules": [],
            }
        )

    df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
    df["year_month"] = df["ts"].dt.to_period("M").astype(str)
    months = sorted(df["year_month"].unique().tolist())

    def stats(col):
        if col not in df.columns:
            return {"samples": 0, "success_rate": 0, "failure_rate": 0, "chop_rate": 0}
        s = df[col].dropna()
        if s.empty:
            return {"samples": 0, "success_rate": 0, "failure_rate": 0, "chop_rate": 0}
        t = len(s)
        return {
            "samples": t,
            "success_rate": round((s > 0).sum() / t, 3),
            "failure_rate": round((s < 0).sum() / t, 3),
            "chop_rate": round((s == 0).sum() / t, 3),
        }

    return jsonify(
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "test_period": {
                "from": df["ts"].min().isoformat(),
                "to": df["ts"].max().isoformat(),
            },
            "months_tested": {"count": len(months), "list": months},
            "rules": [
                {"name": "ORB", **stats("orb_outcome")},
                {"name": "EMA_TREND", **stats("ema_outcome")},
                {"name": "ATR_EXPANSION", **stats("atr_outcome")},
                {"name": "VWAP_TREND", **stats("vwap_outcome")},
                {"name": "VOLUME_EXPANSION", **stats("bb_outcome")},
            ],
        }
    )

