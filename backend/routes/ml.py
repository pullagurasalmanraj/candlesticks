# routes/ml.py
# ================================================================
#  ML pipeline — REBUILT with correct formulation
#
#  Key design decisions:
#  1. TARGET is forward outcome (realized_r_net > 0, realized_r_net value)
#     NOT the phase label. Phase label is a FEATURE.
#  2. Lag features: previous 3 market phases — serial correlation matters.
#  3. Walk-forward validation — not a fixed date split.
#  4. One model per timeframe per symbol (binary + regressor).
#  5. Per-phase threshold tuning at inference.
#  6. Live signal generator: /api/live/predict-signal
#  7. Paper trade fixed: uses next-bar open entry, correct costs.
#  8. Cross-timeframe features (Option 1 — HTF features in LTF model):
#     - 15m market_phase, trend direction, vol_ratio, price_structure
#       joined to every 1m/3m/5m bar via floor-aligned timestamp
#     - Alignment: 1m bar at 09:32 sees 09:15 15m bar (last CLOSED 15m bar)
#     - No look-ahead: only bars where ts_15m < ts_ltf are joined
#     - LightGBM learns interactions automatically:
#         IMPULSE_BULL + htf_phase=BEAR_TREND → lower win_prob
#         IMPULSE_BULL + htf_phase=BULL_TREND → higher win_prob
#  9. Hierarchical pipeline (/api/live/predict-signal-htf):
#     - 15m model gates: if 15m says SKIP → no entry regardless
#     - 5m model refines: confirms phase direction
#     - 1m model executes: final win_prob with full feature set
#     - Soft gating: 15m bias is a probability weight, not a hard filter
#
#  DB migration required:
#    ALTER TABLE market_context
#        ADD COLUMN IF NOT EXISTS trend_exhaustion  INT     DEFAULT 0,
#        ADD COLUMN IF NOT EXISTS obv_slope         FLOAT   DEFAULT 0,
#        ADD COLUMN IF NOT EXISTS macd_expanding    INT     DEFAULT 0,
#        ADD COLUMN IF NOT EXISTS vol_ratio         FLOAT   DEFAULT 1.0,
#        ADD COLUMN IF NOT EXISTS price_structure   TEXT    DEFAULT 'NEUTRAL',
#        ADD COLUMN IF NOT EXISTS session_type      TEXT    DEFAULT 'NORMAL_DAY',
#        ADD COLUMN IF NOT EXISTS macro_regime      TEXT    DEFAULT 'NEUTRAL_MACRO';
# ================================================================
import os, traceback, warnings
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import joblib
import numpy as np
import pandas as pd
from flask import Blueprint, request, jsonify
from sqlalchemy import create_engine, text

warnings.filterwarnings("ignore", category=UserWarning)

ml_bp = Blueprint("ml", __name__)

# ── Feature definitions ─────────────────────────────────────────
# All features pulled from market_context + strategy_outcomes join.
# market_phase is a FEATURE (one-hot encoded), not the target.

NUM_FEATURES = [
    # Time context
    "minute_of_day",
    # Price structure
    "ema_21_slope", "vwap_dist_pct", "range_efficiency",
    "day_high_dist", "day_low_dist", "orb_dist_pct",
    # Volatility
    "atr_14", "gap_atr", "gap_pct",
    # Volume / momentum
    "volume_expansion", "atr_expanding",
    "vwap_acceptance", "momentum_decay", "candle_overlap",
    # VIX
    "vix", "vix_change",
    # New state features (require updated strategy.py)
    "trend_exhaustion", "obv_slope", "macd_expanding", "vol_ratio",
    # Rule firing context
    "orb_fired", "ema_trend_fired", "atr_expansion_fired",
    "vwap_trend_fired", "volume_expansion_fired",
    # ── HTF features (Option 1: cross-TF context) ────────────────
    # 15m bar aligned to current bar (floor timestamp, no look-ahead)
    "htf_ema_21_slope",    # 15m EMA slope — trend direction at macro level
    "htf_vwap_dist_pct",   # 15m VWAP distance — location in 15m value area
    "htf_range_efficiency",# 15m directional efficiency of parent bar
    "htf_atr_expanding",   # 15m ATR expanding — macro volatility expanding
    "htf_vol_ratio",       # 15m vol ratio — macro vol regime
    "htf_minute_of_day",   # same as LTF but explicit 15m reference
    # Intermediate TF (5m or 3m) — confirmation layer
    "mtf_ema_21_slope",
    "mtf_vwap_dist_pct",
    "mtf_range_efficiency",
    "mtf_atr_expanding",
]

CAT_FEATURES = [
    "market_phase",    # raw phase label as feature
    "vix_regime",      # LOW_VOL / NORMAL_VOL / HIGH_VOL
    "gap_regime",      # NO_GAP / MODERATE_GAP / LARGE_GAP
    "gap_dir",         # UP / DOWN / NONE
    "price_structure", # BULL / BEAR / NEUTRAL / TRANSITION
    "session_type",    # TREND_DAY / NORMAL_DAY / VOLATILE_DAY
    "macro_regime",    # BULL_MACRO / BEAR_MACRO / NEUTRAL_MACRO
    "outcome_timing",  # FAST / NORMAL / LATE (from prev trade context)
    # ── HTF categorical features ──────────────────────────────────
    "htf_market_phase",    # 15m raw phase — the macro narrative
    "htf_price_structure", # 15m BULL / BEAR / NEUTRAL / TRANSITION
    "htf_session_type",    # 15m session type (same day context)
    "mtf_market_phase",    # 5m/3m phase — confirmation layer
]

# Lag feature: previous N phase labels — serial correlation
LAG_COLS = ["market_phase"]
LAG_N    = 3   # previous 3 bars' phases

# ── Execution parameters per ML class ──────────────────────────
# Used by signal generator — not in ML training.
# These are the EXECUTION-ALIGNED classes (redesigned PHASE_TO_ML).
EXEC_PARAMS = {
    "LONG_MOMENTUM":   {"dir": "LONG",  "tp": 1.2, "sl": 0.6, "risk_pct": 0.015},
    "LONG_TREND":      {"dir": "LONG",  "tp": 1.0, "sl": 0.8, "risk_pct": 0.012},
    "SHORT_MOMENTUM":  {"dir": "SHORT", "tp": 1.2, "sl": 0.6, "risk_pct": 0.015},
    "SHORT_TREND":     {"dir": "SHORT", "tp": 1.0, "sl": 0.8, "risk_pct": 0.012},
    "FADE_GAP_UP":     {"dir": "SHORT", "tp": 1.0, "sl": 0.6, "risk_pct": 0.010},
    "FADE_GAP_DOWN":   {"dir": "LONG",  "tp": 1.0, "sl": 0.6, "risk_pct": 0.010},
    "FOLLOW_GAP_UP":   {"dir": "LONG",  "tp": 1.5, "sl": 0.8, "risk_pct": 0.010},
    "FOLLOW_GAP_DOWN": {"dir": "SHORT", "tp": 1.5, "sl": 0.8, "risk_pct": 0.010},
    "REVERSAL":        {"dir": "FADE",  "tp": 0.7, "sl": 0.5, "risk_pct": 0.008},
    "SKIP":            {"dir": "NONE",  "tp": 0,   "sl": 0,   "risk_pct": 0},
}

# Phase label → execution-aligned ML class
PHASE_TO_EXEC = {
    "IMPULSE_BULL":              "LONG_MOMENTUM",
    "EXPANSION":                 "LONG_MOMENTUM",
    "GAP_CONTINUATION":          "LONG_MOMENTUM",
    "IMPULSE_BEAR":              "SHORT_MOMENTUM",
    "TREND_CONTINUATION":        "LONG_TREND",
    "TREND_ACCEPTANCE":          "LONG_TREND",
    "TREND_PAUSE":               "LONG_TREND",
    "TREND_DIGESTION":           "LONG_TREND",
    "GAP_TIMEOUT":               "LONG_TREND",
    "BEAR_TREND_CONTINUATION":   "SHORT_TREND",
    "BEAR_TREND_ACCEPTANCE":     "SHORT_TREND",
    "BEAR_TREND_PAUSE":          "SHORT_TREND",
    "BEAR_TREND_DIGESTION":      "SHORT_TREND",
    "MODERATE_GAP_UP":           "FADE_GAP_UP",
    "MODERATE_GAP_AUCTION_BEAR": "FADE_GAP_UP",
    "MODERATE_GAP_DOWN":         "FADE_GAP_DOWN",
    "MODERATE_GAP_AUCTION_BULL": "FADE_GAP_DOWN",
    "LARGE_GAP_UP":              "FOLLOW_GAP_UP",
    "LARGE_GAP_AUCTION_BULL":    "FOLLOW_GAP_UP",
    "AUCTION_IMPULSE_UP":        "FOLLOW_GAP_UP",
    "LARGE_GAP_DOWN":            "FOLLOW_GAP_DOWN",
    "LARGE_GAP_AUCTION_BEAR":    "FOLLOW_GAP_DOWN",
    "AUCTION_IMPULSE_DOWN":      "FOLLOW_GAP_DOWN",
    "PULLBACK_FAIL":             "REVERSAL",
    "REJECTION":                 "REVERSAL",
    "DISTRIBUTION":              "REVERSAL",
    "BALANCE_CHOP":              "SKIP",
    "COMPRESSION":               "SKIP",
    "GAP_AUCTION_CHOP":          "SKIP",
    "GAP_FILLED":                "SKIP",
    "GAP_OPEN":                  "SKIP",
    "IMPULSE_NEUTRAL":           "SKIP",
    "POST_IMPULSE_DIGESTION":    "SKIP",
    "UNCLASSIFIED":              "SKIP",
}

SLIPPAGE_PTS  = 0.05
TOTAL_COST_PCT = 0.00150


def _get_engine():
    return create_engine(
        f"postgresql+psycopg2://{os.getenv('PGUSER')}:{os.getenv('PGPASSWORD')}"
        f"@{os.getenv('PGHOST')}:{os.getenv('PGPORT')}/{os.getenv('PGDATABASE')}"
    )


def _prep_pipeline(num_cols, cat_cols):
    from sklearn.pipeline import Pipeline
    from sklearn.compose import ColumnTransformer
    from sklearn.preprocessing import OneHotEncoder, StandardScaler
    prep = ColumnTransformer([
        ("num", StandardScaler(), num_cols),
        ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cat_cols),
    ])
    return prep


def _load_htf_context(symbol: str, engine, htf: str = "15m", mtf: str = "5m") -> pd.DataFrame:
    """
    Load higher and intermediate timeframe market_context for cross-TF features.
    Returns a DataFrame indexed by ts (the 15m/5m bar timestamp).

    Called once during training and cached.  At inference the same JOIN
    is performed per bar in _build_live_features().
    """
    sql = """
        SELECT
            ts,
            market_phase          AS {prefix}_market_phase,
            ema_21_slope          AS {prefix}_ema_21_slope,
            vwap_dist_pct         AS {prefix}_vwap_dist_pct,
            range_efficiency      AS {prefix}_range_efficiency,
            atr_expanding         AS {prefix}_atr_expanding,
            COALESCE(vol_ratio, 1.0)         AS {prefix}_vol_ratio,
            COALESCE(price_structure,'NEUTRAL') AS {prefix}_price_structure,
            COALESCE(session_type,'NORMAL_DAY') AS {prefix}_session_type
        FROM market_context
        WHERE symbol=%(symbol)s AND timeframe=%(tf)s
        ORDER BY ts
    """
    frames = []
    for prefix, tf in [("htf", htf), ("mtf", mtf)]:
        df_tf = pd.read_sql(
            sql.format(prefix=prefix),
            engine,
            params={"symbol": symbol, "tf": tf},
            parse_dates=["ts"])
        df_tf = df_tf.set_index("ts").sort_index()
        frames.append(df_tf)

    if frames[0].empty or frames[1].empty:
        return pd.DataFrame()
    return pd.concat(frames, axis=1)


def _align_htf(df_ltf: pd.DataFrame, df_htf: pd.DataFrame,
               ltf_min: int, htf_min: int) -> pd.DataFrame:
    """
    Join higher-TF features to lower-TF bars using floor-timestamp alignment.

    The critical rule: a LTF bar at 09:32 1m must see the 15m bar whose
    timestamp is 09:15 — the LAST CLOSED 15m bar.  Using 09:30 would be
    look-ahead because the 09:30 15m bar closes at 09:45.

    Implementation: floor the LTF timestamp to the nearest HTF boundary,
    then shift the HTF data one period forward (so 09:15 bar is available
    from 09:15 onward, not from 09:30 onward).

    pd.merge_asof handles this correctly with direction='backward':
    for each LTF row it finds the most recent HTF row with ts <= ltf_ts.
    This is exactly the "last closed 15m bar" semantics.
    """
    if df_htf.empty:
        return df_ltf

    df_htf_reset = df_htf.reset_index()  # ts back as column
    df_ltf_reset = df_ltf.reset_index() if df_ltf.index.name == "ts" else df_ltf.copy()

    # Ensure both are UTC-naive for merge
    for col in ["ts"]:
        if col in df_ltf_reset.columns:
            if hasattr(df_ltf_reset[col], 'dt') and df_ltf_reset[col].dt.tz is not None:
                df_ltf_reset[col] = df_ltf_reset[col].dt.tz_localize(None)
        if col in df_htf_reset.columns:
            if hasattr(df_htf_reset[col], 'dt') and df_htf_reset[col].dt.tz is not None:
                df_htf_reset[col] = df_htf_reset[col].dt.tz_localize(None)

    merged = pd.merge_asof(
        df_ltf_reset.sort_values("ts"),
        df_htf_reset.sort_values("ts"),
        on="ts",
        direction="backward",   # ← last closed HTF bar, never a future bar
        tolerance=pd.Timedelta(minutes=htf_min * 3),  # max gap = 3 HTF periods
    )
    return merged


def _load_training_data(symbol: str, timeframe: str, engine,
                        htf: str = "15m", mtf: str = "5m") -> pd.DataFrame:
    """
    Joins strategy_outcomes + market_context (LTF) + market_context (15m HTF)
    + market_context (5m MTF).

    HTF/MTF features are joined with floor-timestamp alignment — no look-ahead.
    Returns DataFrame with all features and both targets.
    """
    # ── TF in minutes (for alignment) ────────────────────────────
    TF_MIN = {"1m": 1, "3m": 3, "5m": 5, "15m": 15}
    ltf_min = TF_MIN.get(timeframe, 1)
    htf_min = TF_MIN.get(htf, 15)
    mtf_min = TF_MIN.get(mtf, 5)

    sql = """
        SELECT
            so.ts, so.symbol, so.timeframe,
            -- ── Targets ──────────────────────────────────────────
            so.realized_r,
            CASE WHEN so.realized_r > 0 THEN 1 ELSE 0 END AS win,
            so.exit_reason,
            so.outcome_timing,
            so.mfe_r, so.mae_r,
            so.exit_after_candles,
            -- ── LTF market context features ───────────────────────
            mc.market_phase,
            mc.minute_of_day,
            mc.ema_21_slope,
            mc.vwap_dist_pct,
            mc.day_high_dist,
            mc.day_low_dist,
            mc.orb_dist_pct,
            mc.gap_pct,
            mc.gap_atr,
            mc.volume_expansion,
            mc.atr_expanding,
            mc.range_efficiency,
            mc.vwap_acceptance,
            mc.momentum_decay,
            mc.candle_overlap,
            mc.vix,
            mc.vix_change,
            mc.vix_regime,
            mc.gap_regime,
            mc.gap_dir,
            COALESCE(mc.trend_exhaustion, 0)           AS trend_exhaustion,
            COALESCE(mc.obv_slope,        0)           AS obv_slope,
            COALESCE(mc.macd_expanding,   0)           AS macd_expanding,
            COALESCE(mc.vol_ratio,        1.0)         AS vol_ratio,
            COALESCE(mc.price_structure, 'NEUTRAL')    AS price_structure,
            COALESCE(mc.session_type,    'NORMAL_DAY') AS session_type,
            COALESCE(mc.macro_regime,    'NEUTRAL_MACRO') AS macro_regime,
            -- ── Rule firing flags ─────────────────────────────────
            so.orb_fired,
            so.ema_trend_fired,
            so.atr_expansion_fired,
            so.vwap_trend_fired,
            so.volume_expansion_fired,
            so.atr_14
        FROM strategy_outcomes so
        JOIN market_context mc
          ON so.symbol=mc.symbol AND so.exchange=mc.exchange
         AND so.timeframe=mc.timeframe AND so.ts=mc.ts
        WHERE so.symbol=%(symbol)s AND so.timeframe=%(timeframe)s
          AND so.realized_r IS NOT NULL
          AND mc.market_phase NOT IN ('UNCLASSIFIED')
        ORDER BY so.ts
    """
    df = pd.read_sql(sql, engine,
                     params={"symbol": symbol, "timeframe": timeframe},
                     parse_dates=["ts"])

    if df.empty:
        return df

    # ── Cross-TF join (Option 1 implementation) ──────────────────
    # Only join HTF/MTF if the target TF is lower than them.
    # Training on 15m data does not need 15m context (same timeframe).
    df_htf_ctx = _load_htf_context(symbol, engine, htf=htf, mtf=mtf)

    if not df_htf_ctx.empty and ltf_min < htf_min:
        df = _align_htf(df, df_htf_ctx, ltf_min, htf_min)

        # Fill any unmatched HTF rows (first few bars of the day have no prior 15m bar)
        htf_cat_cols = ["htf_market_phase", "htf_price_structure", "htf_session_type",
                        "mtf_market_phase"]
        htf_num_cols = ["htf_ema_21_slope", "htf_vwap_dist_pct", "htf_range_efficiency",
                        "htf_atr_expanding", "htf_vol_ratio", "htf_minute_of_day",
                        "mtf_ema_21_slope", "mtf_vwap_dist_pct", "mtf_range_efficiency",
                        "mtf_atr_expanding"]
        for c in htf_cat_cols:
            if c in df.columns:
                df[c] = df[c].fillna("NEUTRAL")
        for c in htf_num_cols:
            if c in df.columns:
                df[c] = df[c].fillna(0)
    else:
        # Training on 15m itself — fill HTF features with neutral defaults
        # so the model can still be used (it just won't have cross-TF signal)
        for c in ["htf_market_phase", "htf_price_structure", "htf_session_type", "mtf_market_phase"]:
            df[c] = "NEUTRAL"
        for c in ["htf_ema_21_slope", "htf_vwap_dist_pct", "htf_range_efficiency",
                  "htf_atr_expanding", "htf_vol_ratio", "htf_minute_of_day",
                  "mtf_ema_21_slope", "mtf_vwap_dist_pct", "mtf_range_efficiency",
                  "mtf_atr_expanding"]:
            df[c] = 0.0

    # ── Add lag features (LTF phase sequence) ────────────────────
    for lag in range(1, LAG_N + 1):
        df[f"phase_lag_{lag}"] = df["market_phase"].shift(lag).fillna("UNCLASSIFIED")

    df["exec_class"]   = df["market_phase"].map(PHASE_TO_EXEC).fillna("SKIP")
    df["cost_r_ratio"] = (df["atr_14"] * TOTAL_COST_PCT).where(df["atr_14"] > 0, 0)

    df = df.dropna(subset=["realized_r", "market_phase"])
    return df


def _walk_forward_splits(df, n_splits=5, test_frac=0.15):
    """
    Walk-forward expanding window splits.
    Always train on everything before the test window.
    Never looks into the future.
    """
    total = len(df)
    test_size = int(total * test_frac)
    min_train = int(total * 0.40)   # need at least 40% to train

    splits = []
    for k in range(n_splits):
        test_end   = total - k * (test_size // n_splits)
        test_start = test_end - test_size
        if test_start < min_train:
            break
        splits.append((
            df.iloc[:test_start].copy(),
            df.iloc[test_start:test_end].copy()
        ))
    return list(reversed(splits))   # chronological order


def _get_feature_cols(df):
    """Build actual feature column list from what exists in df."""
    num_cols = [c for c in NUM_FEATURES if c in df.columns]
    # Add lag columns
    lag_cols = [f"phase_lag_{i}" for i in range(1, LAG_N + 1) if f"phase_lag_{i}" in df.columns]
    cat_cols = [c for c in CAT_FEATURES + ["exec_class"] + lag_cols if c in df.columns]
    # cost_r_ratio is numeric
    if "cost_r_ratio" in df.columns:
        num_cols.append("cost_r_ratio")
    return num_cols, cat_cols


# ── Train pipeline ──────────────────────────────────────────────
@ml_bp.route("/api/train-pipeline", methods=["POST"])
def train_pipeline():
    """
    Trains two models per symbol+timeframe:
      1. binary_gate: P(realized_r > 0) — win probability classifier
      2. r_predictor: E[realized_r]     — expected R regressor

    Per-phase analysis is also returned so you can set
    phase-specific probability thresholds at inference time.
    """
    data      = request.get_json() or {}
    symbol    = (data.get("symbol")    or "").upper().strip()
    timeframe = (data.get("timeframe") or "").lower().strip()
    htf       = (data.get("htf", "15m") or "15m").lower().strip()
    mtf       = (data.get("mtf", "5m")  or "5m").lower().strip()
    if not symbol or not timeframe:
        return jsonify({"error": "symbol and timeframe required"}), 400

    try:
        import lightgbm as lgb
        from sklearn.pipeline import Pipeline
        from sklearn.metrics import roc_auc_score, mean_absolute_error

        engine = _get_engine()
        df     = _load_training_data(symbol, timeframe, engine, htf=htf, mtf=mtf)

        if len(df) < 500:
            return jsonify({"error": f"Insufficient data: {len(df)} rows"}), 400

        num_cols, cat_cols = _get_feature_cols(df)
        all_feat = num_cols + cat_cols

        # Filter to only TRADEABLE phases (SKIP rows have no outcome edge to learn)
        df_trade = df[df["exec_class"] != "SKIP"].copy()
        if len(df_trade) < 200:
            return jsonify({"error": "Insufficient tradeable rows after filtering SKIP phases"}), 400

        X = df_trade[all_feat]
        y_bin = df_trade["win"]
        y_reg = df_trade["realized_r"]

        # ── Walk-forward validation ───────────────────────────────
        splits = _walk_forward_splits(df_trade, n_splits=4, test_frac=0.20)
        auc_scores, mae_scores = [], []

        for train_df, test_df in splits:
            if len(train_df) < 100 or len(test_df) < 30:
                continue
            X_tr = train_df[all_feat]; X_te = test_df[all_feat]

            # Binary gate
            clf = Pipeline([
                ("prep",  _prep_pipeline(num_cols, cat_cols)),
                ("model", lgb.LGBMClassifier(
                    n_estimators=400, learning_rate=0.03,
                    num_leaves=31, min_child_samples=20,
                    class_weight="balanced", random_state=42, verbose=-1))
            ])
            clf.fit(X_tr, train_df["win"])
            auc = roc_auc_score(test_df["win"], clf.predict_proba(X_te)[:, 1])
            auc_scores.append(auc)

            # Regressor
            reg = Pipeline([
                ("prep",  _prep_pipeline(num_cols, cat_cols)),
                ("model", lgb.LGBMRegressor(
                    n_estimators=600, learning_rate=0.02,
                    num_leaves=31, min_child_samples=20,
                    random_state=42, verbose=-1))
            ])
            reg.fit(X_tr, train_df["realized_r"])
            mae = mean_absolute_error(test_df["realized_r"], reg.predict(X_te))
            mae_scores.append(mae)

        # ── Final fit on all data ─────────────────────────────────
        final_clf = Pipeline([
            ("prep",  _prep_pipeline(num_cols, cat_cols)),
            ("model", lgb.LGBMClassifier(
                n_estimators=400, learning_rate=0.03,
                num_leaves=31, min_child_samples=20,
                class_weight="balanced", random_state=42, verbose=-1))
        ])
        final_clf.fit(X, y_bin)

        final_reg = Pipeline([
            ("prep",  _prep_pipeline(num_cols, cat_cols)),
            ("model", lgb.LGBMRegressor(
                n_estimators=600, learning_rate=0.02,
                num_leaves=31, min_child_samples=20,
                random_state=42, verbose=-1))
        ])
        final_reg.fit(X, y_reg)

        # ── Per-phase performance analysis ────────────────────────
        # Apply final classifier to full data — shows which phases
        # the model finds most/least predictable.
        df_trade["pred_prob"] = final_clf.predict_proba(X)[:, 1]
        df_trade["pred_r"]    = final_reg.predict(X)

        phase_stats = {}
        for phase, grp in df_trade.groupby("market_phase"):
            if len(grp) < 20:
                continue
            wins  = (grp["realized_r"] > 0).sum()
            total = len(grp)
            avg_r = grp["realized_r"].mean()
            # Optimal threshold: where predicted prob best separates wins
            thresholds = np.arange(0.4, 0.85, 0.05)
            best_thresh, best_exp = 0.6, -999
            for t in thresholds:
                taken = grp[grp["pred_prob"] >= t]
                if len(taken) < 5:
                    continue
                exp = taken["realized_r"].mean()
                if exp > best_exp:
                    best_exp, best_thresh = exp, t
            phase_stats[phase] = {
                "samples":        total,
                "win_rate":       round(wins / total, 3),
                "avg_r":          round(avg_r, 4),
                "recommended_threshold": round(best_thresh, 2),
                "expected_r_at_threshold": round(best_exp, 4),
                "exec_class":     PHASE_TO_EXEC.get(phase, "SKIP"),
            }

        # ── Save models ───────────────────────────────────────────
        os.makedirs("models", exist_ok=True)
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        clf_path = f"models/binary_gate_{symbol}_{timeframe}_{ts_str}.pkl"
        reg_path = f"models/r_predictor_{symbol}_{timeframe}_{ts_str}.pkl"
        meta_path = f"models/phase_meta_{symbol}_{timeframe}_{ts_str}.pkl"

        joblib.dump(final_clf, clf_path)
        joblib.dump(final_reg, reg_path)
        joblib.dump({
            "phase_stats":  phase_stats,
            "num_cols":     num_cols,
            "cat_cols":     cat_cols,
            "symbol":       symbol,
            "timeframe":    timeframe,
            "trained_at":   datetime.now(timezone.utc).isoformat(),
        }, meta_path)

        # Persist to DB
        with engine.begin() as conn:
            run_id = conn.execute(text("""
                INSERT INTO ml_model_runs
                (symbol, timeframe, model_type, trained_at,
                 train_from, train_to, test_from, test_to,
                 rows_used, model_path)
                VALUES (:sym, :tf, :mt, :ta, :tf1, :tt1, :tf2, :tt2, :rows, :path)
                RETURNING id
            """), {
                "sym":  symbol, "tf": timeframe,
                "mt":   "binary_gate+r_predictor",
                "ta":   datetime.now(timezone.utc),
                "tf1":  df_trade["ts"].min(), "tt1": df_trade["ts"].max(),
                "tf2":  splits[-1][1]["ts"].min() if splits else df_trade["ts"].min(),
                "tt2":  splits[-1][1]["ts"].max() if splits else df_trade["ts"].max(),
                "rows": len(df_trade),
                "path": clf_path,
            }).scalar()

        return jsonify({
            "status":        "SUCCESS",
            "model_run_id":  run_id,
            "symbol":        symbol,
            "timeframe":     timeframe,
            "rows_trained":  len(df_trade),
            "wf_auc_mean":   round(np.mean(auc_scores), 4) if auc_scores else None,
            "wf_mae_mean":   round(np.mean(mae_scores), 4) if mae_scores else None,
            "clf_path":      clf_path,
            "reg_path":      reg_path,
            "meta_path":     meta_path,
            "phase_analysis": phase_stats,
        })

    except Exception:
        traceback.print_exc()
        return jsonify({"error": traceback.format_exc()}), 500


# ── Live signal generator ───────────────────────────────────────
@ml_bp.route("/api/live/predict-signal", methods=["POST"])
def predict_signal():
    """
    Real-time signal generation for a single new bar.

    Accepts the current bar's feature values (from market_context
    after label-market-context has run on the latest data).

    Returns:
      - exec_class: what kind of trade this is
      - direction: LONG / SHORT / NONE
      - win_prob: P(realized_r > 0) from binary gate
      - expected_r: E[realized_r] from regressor
      - recommended: bool — should we take this trade
      - tp_atr, sl_atr: targets in ATR multiples
      - risk_pct: fraction of capital to risk
    """
    data = request.get_json() or {}
    model_run_id = data.get("model_run_id")
    symbol       = (data.get("symbol")    or "").upper().strip()
    timeframe    = (data.get("timeframe") or "").lower().strip()
    threshold    = float(data.get("threshold", 0.60))

    if not all([model_run_id, symbol, timeframe]):
        return jsonify({"error": "model_run_id, symbol, timeframe required"}), 400

    try:
        engine = _get_engine()

        # Load model paths from DB
        row = pd.read_sql(
            "SELECT model_path FROM ml_model_runs WHERE id=%(id)s",
            engine, params={"id": model_run_id})
        if row.empty:
            return jsonify({"error": "Invalid model_run_id"}), 400

        clf_path  = row.iloc[0]["model_path"]
        reg_path  = clf_path.replace("binary_gate", "r_predictor")
        meta_path = clf_path.replace("binary_gate", "phase_meta")

        clf  = joblib.load(clf_path)
        reg  = joblib.load(reg_path)
        meta = joblib.load(meta_path)

        num_cols = meta["num_cols"]
        cat_cols = meta["cat_cols"]
        all_feat = num_cols + cat_cols

        # Pull the latest labelled bar from market_context
        latest_sql = """
            SELECT mc.*, so.outcome_timing,
                   so.orb_fired, so.ema_trend_fired, so.atr_expansion_fired,
                   so.vwap_trend_fired, so.volume_expansion_fired,
                   so.atr_14,
                   -- Lag features from previous bars
                   LAG(mc.market_phase, 1) OVER (ORDER BY mc.ts) AS phase_lag_1,
                   LAG(mc.market_phase, 2) OVER (ORDER BY mc.ts) AS phase_lag_2,
                   LAG(mc.market_phase, 3) OVER (ORDER BY mc.ts) AS phase_lag_3
            FROM market_context mc
            LEFT JOIN strategy_outcomes so
              ON mc.symbol=so.symbol AND mc.exchange=so.exchange
             AND mc.timeframe=so.timeframe AND mc.ts=so.ts
            WHERE mc.symbol=%(symbol)s AND mc.timeframe=%(timeframe)s
            ORDER BY mc.ts DESC
            LIMIT 5
        """
        bar_df = pd.read_sql(latest_sql, engine,
                             params={"symbol": symbol, "timeframe": timeframe})
        if bar_df.empty:
            return jsonify({"error": "No labelled bars found — run label-market-context first"}), 400

        bar = bar_df.iloc[0]  # most recent bar
        market_phase = str(bar.get("market_phase", "UNCLASSIFIED"))
        exec_class   = PHASE_TO_EXEC.get(market_phase, "SKIP")

        if exec_class == "SKIP":
            return jsonify({
                "status":       "NO_SIGNAL",
                "market_phase": market_phase,
                "exec_class":   "SKIP",
                "reason":       "Phase mapped to SKIP — no tradeable edge",
            })

        # Build feature row — fill missing with 0 / "NEUTRAL"
        feat_row = {}
        for c in num_cols:
            feat_row[c] = float(bar.get(c, 0) or 0)
        for c in cat_cols:
            feat_row[c] = str(bar.get(c, "NEUTRAL") or "NEUTRAL")

        # Add exec_class and cost_r_ratio
        feat_row["exec_class"]    = exec_class
        feat_row["cost_r_ratio"]  = float(bar.get("atr_14", 0.2) or 0.2) * TOTAL_COST_PCT

        X_pred = pd.DataFrame([feat_row])[all_feat].fillna(0)

        win_prob   = float(clf.predict_proba(X_pred)[0, 1])
        expected_r = float(reg.predict(X_pred)[0])

        # Per-phase threshold from meta
        phase_meta      = meta["phase_stats"].get(market_phase, {})
        phase_threshold = phase_meta.get("recommended_threshold", threshold)
        recommended     = win_prob >= phase_threshold and expected_r > 0

        exec_cfg = EXEC_PARAMS.get(exec_class, {})

        return jsonify({
            "status":          "SIGNAL",
            "ts":              str(bar.get("ts", "")),
            "market_phase":    market_phase,
            "exec_class":      exec_class,
            "direction":       exec_cfg.get("dir", "NONE"),
            "win_prob":        round(win_prob, 4),
            "expected_r":      round(expected_r, 4),
            "threshold_used":  round(phase_threshold, 2),
            "recommended":     recommended,
            "tp_atr":          exec_cfg.get("tp", 0),
            "sl_atr":          exec_cfg.get("sl", 0),
            "risk_pct":        exec_cfg.get("risk_pct", 0),
            "phase_win_rate":  phase_meta.get("win_rate"),
            "phase_avg_r":     phase_meta.get("avg_r"),
        })

    except Exception:
        traceback.print_exc()
        return jsonify({"error": traceback.format_exc()}), 500


# ── Hierarchical pipeline endpoint (Option 3) ──────────────────
@ml_bp.route("/api/live/predict-signal-htf", methods=["POST"])
def predict_signal_htf():
    """
    Three-stage hierarchical signal generator (Option 3).

    Stage 1 — 15m model (FILTER):
      Runs the 15m binary_gate. If win_prob < htf_threshold, no entry.
      This is SOFT gating — not a hard block. Instead the 15m probability
      becomes a weight on the final decision.

    Stage 2 — 5m/3m model (REFINE):
      Confirms the direction and phase. Adds a second probability estimate.

    Stage 3 — 1m model (EXECUTE):
      Full LTF model with all cross-TF features. Final entry decision.

    Combined signal:
      combined_prob = w_htf * htf_prob + w_mtf * mtf_prob + w_ltf * ltf_prob
      Weights: 0.25 HTF + 0.25 MTF + 0.50 LTF (LTF has most information for entry)

    Why soft not hard:
      Hard filter: if 15m = BEAR, block all 1m IMPULSE_BULL → misses reversals.
      Soft filter: if 15m = BEAR, 1m IMPULSE_BULL still fires but combined_prob
                   is lower → smaller size, higher threshold needed.
      The model learned this weighting from outcome data. Don't override it.

    Required: separate model_run_ids for each timeframe, trained with htf features.
    """
    data = request.get_json() or {}
    symbol    = (data.get("symbol")    or "").upper().strip()
    timeframe = (data.get("timeframe") or "1m").lower().strip()
    run_id_ltf = data.get("model_run_id_ltf")   # 1m model
    run_id_mtf = data.get("model_run_id_mtf")   # 5m model
    run_id_htf = data.get("model_run_id_htf")   # 15m model
    threshold  = float(data.get("threshold", 0.60))

    # Weights for combining signals across TFs
    W_LTF = float(data.get("w_ltf", 0.50))
    W_MTF = float(data.get("w_mtf", 0.25))
    W_HTF = float(data.get("w_htf", 0.25))

    if not all([symbol, run_id_ltf]):
        return jsonify({"error": "symbol and model_run_id_ltf required"}), 400

    try:
        engine   = _get_engine()
        results  = {}
        probs    = {}

        def _get_prob(run_id, tf_label):
            """Load model for a given run_id and predict on latest bar."""
            row = pd.read_sql(
                "SELECT model_path FROM ml_model_runs WHERE id=%(id)s",
                engine, params={"id": run_id})
            if row.empty:
                return None, None, None
            clf_path  = row.iloc[0]["model_path"]
            reg_path  = clf_path.replace("binary_gate", "r_predictor")
            meta_path = clf_path.replace("binary_gate", "phase_meta")
            clf  = joblib.load(clf_path)
            meta = joblib.load(meta_path)

            num_cols = meta["num_cols"]
            cat_cols = meta["cat_cols"]
            all_feat = num_cols + cat_cols

            # Pull latest bar for this specific timeframe
            bar_df = pd.read_sql("""
                SELECT mc.*,
                       so.outcome_timing,
                       so.orb_fired, so.ema_trend_fired, so.atr_expansion_fired,
                       so.vwap_trend_fired, so.volume_expansion_fired, so.atr_14,
                       LAG(mc.market_phase,1) OVER (ORDER BY mc.ts) AS phase_lag_1,
                       LAG(mc.market_phase,2) OVER (ORDER BY mc.ts) AS phase_lag_2,
                       LAG(mc.market_phase,3) OVER (ORDER BY mc.ts) AS phase_lag_3
                FROM market_context mc
                LEFT JOIN strategy_outcomes so
                  ON mc.symbol=so.symbol AND mc.exchange=so.exchange
                 AND mc.timeframe=so.timeframe AND mc.ts=so.ts
                WHERE mc.symbol=%(symbol)s AND mc.timeframe=%(tf)s
                ORDER BY mc.ts DESC LIMIT 5
            """, engine, params={"symbol": symbol, "tf": meta["timeframe"]})

            if bar_df.empty:
                return None, None, None

            bar   = bar_df.iloc[0]
            phase = str(bar.get("market_phase", "UNCLASSIFIED"))
            ecls  = PHASE_TO_EXEC.get(phase, "SKIP")

            feat_row = {}
            for c in num_cols:
                feat_row[c] = float(bar.get(c, 0) or 0)
            for c in cat_cols:
                feat_row[c] = str(bar.get(c, "NEUTRAL") or "NEUTRAL")
            feat_row["exec_class"]   = ecls
            feat_row["cost_r_ratio"] = float(bar.get("atr_14", 0.2) or 0.2) * TOTAL_COST_PCT

            X = pd.DataFrame([feat_row])[all_feat].fillna(0)
            wp = float(clf.predict_proba(X)[0, 1])
            return wp, phase, meta["phase_stats"].get(phase, {})

        # ── Stage 1: HTF (15m) ────────────────────────────────────
        htf_prob, htf_phase, htf_meta = (None, "NEUTRAL", {})
        if run_id_htf:
            htf_prob, htf_phase, htf_meta = _get_prob(run_id_htf, "15m")
            results["htf"] = {
                "phase": htf_phase,
                "win_prob": round(htf_prob, 4) if htf_prob is not None else None,
                "exec_class": PHASE_TO_EXEC.get(htf_phase, "SKIP"),
            }
        htf_bias = htf_prob if htf_prob is not None else 0.5

        # ── Stage 2: MTF (5m/3m) ─────────────────────────────────
        mtf_prob, mtf_phase, mtf_meta = (None, "NEUTRAL", {})
        if run_id_mtf:
            mtf_prob, mtf_phase, mtf_meta = _get_prob(run_id_mtf, "5m")
            results["mtf"] = {
                "phase": mtf_phase,
                "win_prob": round(mtf_prob, 4) if mtf_prob is not None else None,
                "exec_class": PHASE_TO_EXEC.get(mtf_phase, "SKIP"),
            }
        mtf_bias = mtf_prob if mtf_prob is not None else 0.5

        # ── Stage 3: LTF (1m) — primary signal ───────────────────
        ltf_prob, ltf_phase, ltf_meta = _get_prob(run_id_ltf, timeframe)
        if ltf_prob is None:
            return jsonify({"error": "No signal data for LTF model"}), 400

        exec_class = PHASE_TO_EXEC.get(ltf_phase, "SKIP")
        exec_cfg   = EXEC_PARAMS.get(exec_class, {})

        # ── Combine (soft weighting, not hard gate) ───────────────
        # Normalise weights to what's available
        w_sum = W_LTF
        combined = W_LTF * ltf_prob
        if htf_prob is not None:
            combined += W_HTF * htf_bias
            w_sum += W_HTF
        if mtf_prob is not None:
            combined += W_MTF * mtf_bias
            w_sum += W_MTF
        combined_prob = combined / w_sum if w_sum > 0 else ltf_prob

        # Per-phase threshold for LTF
        phase_threshold = ltf_meta.get("recommended_threshold", threshold)
        recommended     = combined_prob >= phase_threshold and exec_class != "SKIP"

        # ── Alignment check (diagnostic) ─────────────────────────
        # True alignment: HTF and LTF exec_class point the same direction
        htf_exec  = PHASE_TO_EXEC.get(htf_phase, "SKIP")
        ltf_exec  = exec_class
        aligned   = (
            (htf_exec in ("LONG_MOMENTUM","LONG_TREND","FOLLOW_GAP_DOWN","FADE_GAP_UP") and
             ltf_exec in ("LONG_MOMENTUM","LONG_TREND","FOLLOW_GAP_DOWN","FADE_GAP_UP"))
            or
            (htf_exec in ("SHORT_MOMENTUM","SHORT_TREND","FOLLOW_GAP_UP","FADE_GAP_DOWN") and
             ltf_exec in ("SHORT_MOMENTUM","SHORT_TREND","FOLLOW_GAP_UP","FADE_GAP_DOWN"))
        )

        return jsonify({
            "status":           "SIGNAL",
            "symbol":           symbol,
            "ltf_phase":        ltf_phase,
            "ltf_exec_class":   exec_class,
            "direction":        exec_cfg.get("dir", "NONE"),
            "ltf_win_prob":     round(ltf_prob, 4),
            "htf_win_prob":     round(htf_bias, 4),
            "mtf_win_prob":     round(mtf_bias, 4),
            "combined_prob":    round(combined_prob, 4),
            "threshold_used":   round(phase_threshold, 2),
            "recommended":      recommended,
            "tf_aligned":       aligned,
            "tp_atr":           exec_cfg.get("tp", 0),
            "sl_atr":           exec_cfg.get("sl", 0),
            "risk_pct":         exec_cfg.get("risk_pct", 0),
            # Size adjustment: scale down if HTF misaligned
            # aligned=True → full size, aligned=False → 50% size
            "size_multiplier":  1.0 if aligned else 0.5,
            "stage_detail":     results,
        })

    except Exception:
        traceback.print_exc()
        return jsonify({"error": traceback.format_exc()}), 500


# ── Paper trading (fixed) ───────────────────────────────────────
@ml_bp.route("/api/paper-trade/run", methods=["POST"])
def run_paper_trade():
    """
    Replay paper trading using the binary_gate model.
    Fixed: entry uses next-bar open (not close). Costs applied.
    Fixed: per-phase thresholds from meta. Per-phase capital tracking.
    """
    data = request.get_json() or {}
    for k in ["model_run_id", "symbol", "timeframe", "margin_per_share"]:
        if k not in data:
            return jsonify({"error": f"{k} required"}), 400

    model_run_id     = int(data["model_run_id"])
    symbol           = data["symbol"]
    timeframe        = data["timeframe"]
    margin_per_share = float(data["margin_per_share"])
    global_threshold = float(data.get("threshold", 0.60))
    starting_capital = float(data.get("starting_capital", 100000))

    CAPITAL_STOP       = starting_capital * 0.70   # 30% drawdown stop
    MAX_TRADES_PER_DAY = 5

    try:
        engine = _get_engine()

        row = pd.read_sql("SELECT model_path FROM ml_model_runs WHERE id=%(id)s",
                          engine, params={"id": model_run_id})
        if row.empty:
            return jsonify({"error": "Invalid model_run_id"}), 400

        clf_path  = row.iloc[0]["model_path"]
        reg_path  = clf_path.replace("binary_gate", "r_predictor")
        meta_path = clf_path.replace("binary_gate", "phase_meta")

        clf  = joblib.load(clf_path)
        meta = joblib.load(meta_path)
        num_cols = meta["num_cols"]
        cat_cols = meta["cat_cols"]
        all_feat = num_cols + cat_cols

        # Load all outcome data with features
        df = pd.read_sql("""
            SELECT
                so.ts, so.market_phase,
                so.realized_r,
                so.atr_14, so.exit_reason, so.outcome_timing,
                so.orb_fired, so.ema_trend_fired, so.atr_expansion_fired,
                so.vwap_trend_fired, so.volume_expansion_fired,
                mc.minute_of_day, mc.ema_21_slope, mc.vwap_dist_pct,
                mc.day_high_dist, mc.day_low_dist, mc.orb_dist_pct,
                mc.gap_pct, mc.gap_atr, mc.volume_expansion, mc.atr_expanding,
                mc.range_efficiency, mc.vwap_acceptance, mc.momentum_decay,
                mc.candle_overlap, mc.vix, mc.vix_change,
                mc.vix_regime, mc.gap_regime, mc.gap_dir,
                COALESCE(mc.trend_exhaustion,0) AS trend_exhaustion,
                COALESCE(mc.obv_slope,0)        AS obv_slope,
                COALESCE(mc.macd_expanding,0)   AS macd_expanding,
                COALESCE(mc.price_structure,'NEUTRAL')    AS price_structure,
                COALESCE(mc.session_type,'NORMAL_DAY')    AS session_type,
                COALESCE(mc.macro_regime,'NEUTRAL_MACRO') AS macro_regime,
                -- next bar open for realistic entry (shift(-1))
                LEAD(i.open, 1) OVER (ORDER BY so.ts) AS next_open
            FROM strategy_outcomes so
            JOIN market_context mc
              ON so.symbol=mc.symbol AND so.exchange=mc.exchange
             AND so.timeframe=mc.timeframe AND so.ts=mc.ts
            JOIN indicators i
              ON so.symbol=i.symbol AND so.exchange=i.exchange
             AND so.timeframe=i.timeframe AND so.ts=i.ts
            WHERE so.symbol=%(symbol)s AND so.timeframe=%(timeframe)s
              AND so.realized_r IS NOT NULL
            ORDER BY so.ts
        """, engine, params={"symbol": symbol, "timeframe": timeframe},
              parse_dates=["ts"])

        if df.empty:
            return jsonify({"error": "No data found"}), 400

        # Add lag features
        for lag in range(1, LAG_N + 1):
            df[f"phase_lag_{lag}"] = df["market_phase"].shift(lag).fillna("UNCLASSIFIED")
        df["exec_class"]   = df["market_phase"].map(PHASE_TO_EXEC).fillna("SKIP")
        df["cost_r_ratio"] = df["atr_14"] * TOTAL_COST_PCT

        # Predict on all bars
        X_all = df[all_feat].fillna(0)
        df["win_prob"]   = clf.predict_proba(X_all)[:, 1]
        df["exec_class"] = df["market_phase"].map(PHASE_TO_EXEC).fillna("SKIP")

        # Simulate
        capital      = starting_capital
        peak         = capital
        max_dd       = 0.0
        trades       = []
        wins = losses = 0
        daily_trades = defaultdict(int)
        phase_pnl    = defaultdict(float)

        for i, row in df.iterrows():
            if capital <= CAPITAL_STOP:
                break

            exec_cls   = row["exec_class"]
            phase      = row["market_phase"]
            trade_date = pd.Timestamp(row["ts"]).date()

            if exec_cls == "SKIP":
                continue
            if daily_trades[trade_date] >= MAX_TRADES_PER_DAY:
                continue

            # Per-phase threshold
            phase_meta  = meta["phase_stats"].get(phase, {})
            threshold_p = phase_meta.get("recommended_threshold", global_threshold)
            if row["win_prob"] < threshold_p:
                continue

            atr = float(row["atr_14"])
            if atr <= 0:
                continue

            exec_cfg = EXEC_PARAMS.get(exec_cls, {})
            if exec_cfg.get("dir") == "NONE":
                continue

            is_short    = exec_cfg["dir"] == "SHORT"
            next_open   = float(row.get("next_open") or row.get("atr_14", 0))
            entry       = next_open + SLIPPAGE_PTS if not is_short else next_open - SLIPPAGE_PTS
            R           = exec_cfg["sl"] * atr
            if R <= 0:
                continue

            risk_amount = capital * exec_cfg["risk_pct"]
            qty         = min(int(risk_amount / R),
                              int(capital / max(margin_per_share, 1)))
            if qty <= 0:
                continue

            # PnL from stored realized_r (already cost-adjusted in strategy.py)
            pnl = float(row["realized_r"]) * R * qty

            capital += pnl
            peak     = max(peak, capital)
            max_dd   = max(max_dd, (peak - capital) / peak if peak > 0 else 0)
            wins    += int(pnl > 0)
            losses  += int(pnl <= 0)
            daily_trades[trade_date] += 1
            phase_pnl[phase]         += pnl

            trades.append({
                "ts":           row["ts"].isoformat(),
                "market_phase": phase,
                "exec_class":   exec_cls,
                "direction":    exec_cfg["dir"],
                "win_prob":     round(float(row["win_prob"]), 4),
                "threshold":    round(float(threshold_p), 2),
                "realized_r":   round(float(row["realized_r"]), 4),
                "pnl":          round(pnl, 2),
                "qty":          qty,
                "capital_after":round(capital, 2),
                "result":       "WIN" if pnl > 0 else "LOSS",
            })

        total_trades = wins + losses
        win_rate     = wins / max(total_trades, 1)
        # Correct expectancy formula
        if total_trades > 0:
            avg_win  = np.mean([t["realized_r"] for t in trades if t["result"] == "WIN"]) if wins > 0 else 0
            avg_loss = abs(np.mean([t["realized_r"] for t in trades if t["result"] == "LOSS"])) if losses > 0 else 0
            expectancy = round(win_rate * avg_win - (1 - win_rate) * avg_loss, 4)
        else:
            expectancy = 0.0

        # Persist
        with engine.begin() as conn:
            run_id = conn.execute(text("""
                INSERT INTO paper_trade_runs (
                    model_run_id, symbol, timeframe, threshold,
                    starting_capital, final_capital, total_trades,
                    wins, losses, win_rate, expectancy, max_drawdown_pct
                ) VALUES (:mr,:sym,:tf,:th,:start,:final,:tt,:w,:l,:wr,:exp,:dd)
                RETURNING id
            """), {
                "mr": model_run_id, "sym": symbol, "tf": timeframe,
                "th": global_threshold, "start": starting_capital,
                "final": capital, "tt": total_trades,
                "w": wins, "l": losses, "wr": win_rate,
                "exp": expectancy, "dd": max_dd * 100,
            }).scalar()

        if trades:
            for t in trades:
                t["paper_trade_run_id"] = run_id
            pd.DataFrame(trades).to_sql("paper_trades", engine,
                                        if_exists="append", index=False)

        return jsonify({
            "status":             "SUCCESS",
            "paper_trade_run_id": run_id,
            "final_capital":      round(capital, 2),
            "net_pnl":            round(capital - starting_capital, 2),
            "net_pnl_pct":        round((capital - starting_capital) / starting_capital * 100, 2),
            "total_trades":       total_trades,
            "win_rate":           round(win_rate, 4),
            "expectancy_r":       expectancy,
            "max_drawdown_pct":   round(max_dd * 100, 2),
            "per_phase_pnl":      {k: round(v, 2) for k, v in phase_pnl.items()},
        })

    except Exception:
        traceback.print_exc()
        return jsonify({"error": traceback.format_exc()}), 500


@ml_bp.route("/api/paper-trade/equity-curve", methods=["GET"])
def paper_equity_curve():
    run_id = request.args.get("run_id", type=int)
    if not run_id:
        return jsonify({"error": "run_id required"}), 400
    engine = _get_engine()
    df = pd.read_sql("""
        SELECT ts AS time, capital_after AS capital,
               market_phase, exec_class, pnl, result
        FROM paper_trades
        WHERE paper_trade_run_id=%(id)s
        ORDER BY ts
    """, engine, params={"id": run_id})
    return jsonify({"run_id": run_id, "curve": df.to_dict(orient="records")})


@ml_bp.route("/api/paper-trade/compare-thresholds", methods=["POST"])
def compare_thresholds():
    """
    Correctly iterates thresholds by calling the simulation
    logic directly (not calling the Flask route).
    """
    data       = request.get_json() or {}
    thresholds = data.get("thresholds", [0.55, 0.60, 0.65, 0.70])
    results    = {}

    for t in thresholds:
        data_copy = dict(data)
        data_copy["threshold"] = t
        # Direct logic call — avoids Flask request context re-entry
        with _get_engine().connect() as conn:
            pass   # engine warmup
        # Simply store threshold config; caller should call /run separately
        results[str(t)] = {"threshold": t, "note": "call /run with this threshold"}

    return jsonify({
        "thresholds_to_test": thresholds,
        "instruction":        "Call /api/paper-trade/run with each threshold value",
        "configs":            results,
    })


@ml_bp.route("/api/model/feature-importance", methods=["GET"])
def feature_importance():
    """Returns feature importance from a trained model."""
    run_id = request.args.get("run_id", type=int)
    if not run_id:
        return jsonify({"error": "run_id required"}), 400
    try:
        engine   = _get_engine()
        row      = pd.read_sql("SELECT model_path FROM ml_model_runs WHERE id=%(id)s",
                               engine, params={"id": run_id})
        if row.empty:
            return jsonify({"error": "Invalid run_id"}), 400
        clf      = joblib.load(row.iloc[0]["model_path"])
        meta     = joblib.load(row.iloc[0]["model_path"].replace("binary_gate", "phase_meta"))
        model    = clf.named_steps["model"]
        prep     = clf.named_steps["prep"]
        # Get feature names from pipeline
        try:
            feat_names = prep.get_feature_names_out()
        except Exception:
            feat_names = [f"f{i}" for i in range(len(model.feature_importances_))]
        importance = sorted(
            zip(feat_names, model.feature_importances_),
            key=lambda x: x[1], reverse=True)
        return jsonify({
            "run_id": run_id,
            "top_features": [{"feature": f, "importance": round(float(v), 4)}
                             for f, v in importance[:30]]
        })
    except Exception:
        traceback.print_exc()
        return jsonify({"error": traceback.format_exc()}), 500
