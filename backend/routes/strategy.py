# routes/strategy.py
# ================================================================
#  Strategy Route Handlers Blueprint
# ================================================================
import time, math, traceback
from datetime import datetime, timezone
import pandas as pd
import numpy as np
from flask import Blueprint, request, jsonify

from db import get_db_conn, read_sql_safe, chunk_execute as _chunk_execute
from routes.strategy_logic import (
    COST_R_MAX_GATE,
    TOTAL_COST_PCT,
    SLIPPAGE_PTS,
    PHASE_MODEL,
    _run_state_machine,
    _build_market_rows,
    _build_rule_rows,
    _simulate_exit_vectorized,
    _load_phase_params,
    invalidate_phase_params_cache
)

strategy_bp = Blueprint("strategy", __name__)

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

        # ------ Fetch preceding candles for warming up price structure swing detection ------
        # To avoid a cold start, fetch the preceding 8 * SWING_N candles' high/low values.
        warmup_limit = int(8 * SWING_N)
        warmup_highs = np.array([], dtype=float)
        warmup_lows = np.array([], dtype=float)
        first_ts = df["ts"].iloc[0].to_pydatetime()

        if timeframe == "1d":
            warmup_query = """
                SELECT timestamp, high, low
                FROM daily_candles
                WHERE symbol=%s AND exchange=%s AND timestamp < %s
                ORDER BY timestamp DESC
                LIMIT %s
            """
            warmup_params = (symbol, exchange, first_ts, warmup_limit)
        else:
            warmup_query = """
                SELECT timestamp, high, low
                FROM intraday_candles
                WHERE symbol=%s AND exchange=%s AND timeframe=%s AND timestamp < %s
                ORDER BY timestamp DESC
                LIMIT %s
            """
            warmup_params = (symbol, exchange, timeframe, first_ts, warmup_limit)

        with get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(warmup_query, warmup_params)
                warmup_rows = cur.fetchall()

        if warmup_rows:
            # Reversing DESC order to chronological order
            warmup_rows.reverse()
            warmup_highs = np.array([float(r["high"]) for r in warmup_rows], dtype=float)
            warmup_lows = np.array([float(r["low"]) for r in warmup_rows], dtype=float)

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
            swing_n=SWING_N,
            obv_window=OBV_WINDOW,
            roll_20=ROLL_20,
            absorption_vol_thr=1.1,
            absorption_max_streak=6,
            distribution_max_streak=5,
            pullback_min_bars=2,
            trend_context_decay=20,
            debug=True,
            warmup_highs=warmup_highs,
            warmup_lows=warmup_lows,
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

        # ------ Align market context start directly to indicators start (09:15 AM IST) ------------
        is_915 = (df["ts_ist"].dt.hour == 9) & (df["ts_ist"].dt.minute == 15)
        open_idx = np.flatnonzero(is_915.to_numpy())
        if len(open_idx) > 0:
            df = df.iloc[int(open_idx[0]):].reset_index(drop=True)

        # Now fillna is safe --- only genuine missing values remain
        for c in FEATURE_COLS:
            df[c] = df[c].fillna(0)

        now = datetime.now(timezone.utc)

        # ------ IMPROVEMENT 2: vectorized row building ---------------------------------------------
        tf_role = {"1m": "MICRO", "3m": "CONFIRM", "5m": "CONFIRM", "15m": "EXECUTE"}[
            timeframe
        ]
        df["tf_role"] = tf_role
        market_rows = _build_market_rows(df, symbol, exchange, timeframe, now)
        rule_rows = _build_rule_rows(df, symbol, exchange, timeframe, now)
        label_cutoff_ts = pd.Timestamp(df["ts"].iloc[0]).to_pydatetime()

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
                context_label,
                phase_reason,
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
                context_label=EXCLUDED.context_label,
                phase_reason=EXCLUDED.phase_reason,
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
                cur.execute("ALTER TABLE market_context ADD COLUMN IF NOT EXISTS context_label text;")
                cur.execute("ALTER TABLE market_context ADD COLUMN IF NOT EXISTS phase_reason text;")
                cur.execute("ALTER TABLE strategy_outcomes ADD COLUMN IF NOT EXISTS phase_reason text;")

                # Discard stale warmup-era labels from earlier runs.
                cur.execute(
                    """
                    DELETE FROM market_context
                    WHERE symbol=%s AND exchange=%s AND timeframe=%s AND ts < %s
                    """,
                    (symbol, exchange, timeframe, label_cutoff_ts),
                )
                cur.execute(
                    """
                    DELETE FROM rule_evaluations
                    WHERE symbol=%s AND exchange=%s AND timeframe=%s AND ts < %s
                    """,
                    (symbol, exchange, timeframe, label_cutoff_ts),
                )
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

        # Issue 1: Date filtering for walk-forward calibration
        raw_from = data.get("from_date")
        raw_to = data.get("to_date")
        date_warning = None
        if not raw_from or not raw_to:
            date_warning = (
                "No date range specified; calibrating over full available history. "
                "Specify from_date and to_date for out-of-sample walk-forward calibration."
            )

        from_dt = pd.to_datetime(raw_from or "2000-01-01", utc=True)
        to_dt = pd.to_datetime(raw_to or datetime.now(timezone.utc), utc=True)

        MIN_SAMPLES = int(data.get("min_samples", 30))
        TP_PERCENTILE = float(data.get("tp_percentile", 60))  # p60 of mfe_r
        SL_PERCENTILE = float(data.get("sl_percentile", 25))  # p25 of |mae_r|
        LA_PERCENTILE = float(data.get("la_percentile", 75))  # p75 of exit_after

        TF_MIN_MAP = {"1m": 1, "3m": 3, "5m": 5, "15m": 15}
        tf_min = TF_MIN_MAP.get(timeframe, 1)

        with get_db_conn() as conn:
            # Ensure DB table schema has calibrated_from and calibrated_to columns
            with conn.cursor() as cur:
                cur.execute("""
                    ALTER TABLE phase_params
                    ADD COLUMN IF NOT EXISTS calibrated_from TIMESTAMPTZ,
                    ADD COLUMN IF NOT EXISTS calibrated_to TIMESTAMPTZ;
                """)

            # Diagnostic: count total rows first so error message is specific
            total_df = read_sql_safe(
                """
                SELECT COUNT(*) AS total_rows,
                       COUNT(mfe_r) AS has_mfe_r,
                       COUNT(mae_r) AS has_mae_r,
                       COUNT(exit_after_candles) AS has_exit_after
                FROM strategy_outcomes
                WHERE symbol=%s AND exchange=%s AND timeframe=%s
                  AND ts BETWEEN %s AND %s
            """,
                conn,
                params=[symbol, exchange, timeframe, from_dt, to_dt],
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
                  AND ts BETWEEN %s AND %s
                  AND mfe_r IS NOT NULL
                  AND mae_r IS NOT NULL
                  AND exit_after_candles IS NOT NULL
            """,
                conn,
                params=[symbol, exchange, timeframe, from_dt, to_dt],
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
                    from_dt,
                    to_dt,
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
                            p75_exit_after,viable,computed_at,
                            calibrated_from,calibrated_to
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
                            computed_at=EXCLUDED.computed_at,
                            calibrated_from=EXCLUDED.calibrated_from,
                            calibrated_to=EXCLUDED.calibrated_to
                    """,
                        upsert_rows,
                    )

        # Invalidate in-process cache so next calc run picks up new values
        invalidate_phase_params_cache(symbol, exchange, timeframe)

        calibrated = sum(1 for v in results.values() if v.get("status") == "CALIBRATED")
        viable_count = sum(1 for v in results.values() if v.get("viable") is True)
        unviable_count = sum(1 for v in results.values() if v.get("viable") is False)
        skipped = len(results) - calibrated

        res_payload = {
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
            "calibrated_from": from_dt.isoformat(),
            "calibrated_to": to_dt.isoformat(),
            "phases": results,
        }
        if date_warning:
            res_payload["calibration_warning"] = date_warning

        return jsonify(res_payload)

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

        # Issue 1: Detect calibration window overlap with evaluation request window
        max_calibrated_to = None
        for _pname, pinfo in data_params.items():
            c_to = pinfo.get("calibrated_to")
            if c_to is not None:
                try:
                    c_to_dt = pd.to_datetime(c_to, utc=True)
                    if max_calibrated_to is None or c_to_dt > max_calibrated_to:
                        max_calibrated_to = c_to_dt
                except Exception:
                    pass

        params_overlap_warning = False
        if max_calibrated_to is not None and from_dt <= max_calibrated_to:
            params_overlap_warning = True

        # Issue 2: Precompute session_end_idx to cap trade lookahead at session boundaries (zero overnight leakage)
        # Convert timestamps to IST timezone so session dates correspond strictly to Indian trading days (09:15 to 15:30 IST)
        ts_pd = pd.to_datetime(df["ts"])
        if ts_pd.dt.tz is None:
            ts_pd = ts_pd.dt.tz_localize("UTC")
        session_dates = ts_pd.dt.tz_convert("Asia/Kolkata").dt.date.to_numpy()

        session_end_idx = np.zeros(N, dtype=int)
        last_idx = N - 1
        for idx in range(N - 1, -1, -1):
            if idx == N - 1 or session_dates[idx] != session_dates[idx + 1]:
                last_idx = idx
            session_end_idx[idx] = last_idx

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
            entry_idx = i + 1
            if entry_idx >= N:
                continue

            # Issue 2: Session boundary capping relative to entry bar (entry_idx = i + 1)
            session_end = session_end_idx[entry_idx]
            max_bars_in_session = session_end - entry_idx + 1  # count of bars in session from entry_idx to session_end
            if max_bars_in_session < 1:
                continue  # Skip trade if no bars remain in the current session

            la_capped = min(la, max_bars_in_session)

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

            # Issue 3: Exit simulation includes bar i+1 (the entry bar itself), capped at la_capped (Issue 2)
            exit_reason, exit_price, exit_after, mfe, mae = _simulate_exit_vectorized(
                entry,
                tp,
                sl,
                highs[i + 1 : i + 1 + la_capped],
                lows[i + 1 : i + 1 + la_capped],
                closes[i + 1 : i + 1 + la_capped],
                la_capped,
                is_short=is_short,
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
                        ts_arr[min(N - 1, entry_idx + int(exit_after) - 1)]
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
        res_payload = {
            "status": "SUCCESS",
            "rows_written": len(rows),
            "elapsed_sec": elapsed,
            "phases_calibrated": n_calibrated,
            "phases_default": len(_cfg_cache) - n_calibrated - n_unviable_fallback,
            "phases_unviable_fallback": n_unviable_fallback,
            "param_source": "calibrated" if n_calibrated > 0 else "default",
            "params_overlap_warning": params_overlap_warning,
            "max_calibrated_to": max_calibrated_to.isoformat() if max_calibrated_to else None,
            "cost_r_gate": cost_r_gate,
            "skipped_by_cost": n_cost_skipped,
            "pct_skipped_by_cost": round(n_cost_skipped / max(1, N) * 100, 1),
            "skipped_by_eod": n_eod_skipped,
            "skipped_by_min_rules": n_rules_skipped,
            "min_rules_fired": min_rules_fired,
        }
        if params_overlap_warning:
            res_payload["overlap_warning_details"] = (
                "Evaluation request start date overlaps or precedes the calibration window end date "
                f"({max_calibrated_to.isoformat() if max_calibrated_to else 'N/A'}). "
                "Recommend using a rolling out-of-sample walk-forward split to eliminate in-sample target leakage."
            )
        return jsonify(res_payload)

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


# ------ Debug & Label Reasons Inspection ------------------------------------------------------------------
@strategy_bp.route("/api/market-context/reasons", methods=["GET"])
def get_market_context_reasons():
    """
    Query market phase labels and the exact priority rule/condition reason
    captured during debug-mode labelling.
    """
    symbol = (request.args.get("symbol") or "").upper().strip()
    timeframe = (request.args.get("timeframe") or "").lower().strip()
    limit = int(request.args.get("limit", 200))

    if not symbol or not timeframe:
        return jsonify({"error": "symbol and timeframe required"}), 400

    with get_db_conn() as conn:
        df = read_sql_safe(
            """
            SELECT ts, market_phase, ml_label, price_structure,
                   COALESCE(context_label, '') AS context_label,
                   COALESCE(phase_reason, '')  AS phase_reason
            FROM market_context
            WHERE symbol=%s AND timeframe=%s
            ORDER BY ts DESC
            LIMIT %s
            """,
            conn,
            params=[symbol, timeframe, limit],
        )

    if df.empty:
        return jsonify({"symbol": symbol, "timeframe": timeframe, "total": 0, "bars": [], "reasons_summary": {}})

    df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
    summary = df["phase_reason"].value_counts().to_dict()

    bars = [
        {
            "ts": row["ts"].isoformat() if pd.notnull(row["ts"]) else None,
            "market_phase": row["market_phase"],
            "ml_label": row["ml_label"],
            "price_structure": row["price_structure"],
            "context_label": row["context_label"],
            "phase_reason": row["phase_reason"],
        }
        for _, row in df.iterrows()
    ]

    return jsonify(
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "total": len(bars),
            "reasons_summary": summary,
            "bars": bars,
        }
    )

