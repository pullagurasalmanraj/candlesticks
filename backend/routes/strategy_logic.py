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

from db import get_db_conn, read_sql_safe, chunk_execute as _chunk_execute


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




def invalidate_phase_params_cache(symbol: str, exchange: str, timeframe: str):
    """Evict entry from in-process cache (e.g. after new calibration)."""
    cache_key = (symbol.upper().strip(), exchange.upper().strip(), timeframe.lower().strip())
    _PHASE_PARAMS_CACHE.pop(cache_key, None)
    _PHASE_PARAMS_CACHE_TS.pop(cache_key, None)
