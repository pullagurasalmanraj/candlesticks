# routes/strategy.py
# ================================================================
#  Strategy blueprint:
#    POST /api/offline/label-market-context
#    POST /api/offline/calc-strategy-outcomes
#    GET  /api/market-context/rule-stats
# ================================================================
import json, traceback
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from flask import Blueprint, request, jsonify
from psycopg2.extras import execute_values

from db         import get_db_conn
from utils.symbol_map import SYMBOL_TO_KEY

# ── Inline helper ────────────────────────────────────────────────
def json_safe(v):
    """Convert NaN/Inf to None so json.dumps doesn't choke."""
    try:
        f = float(v)
        import math
        return None if (math.isnan(f) or math.isinf(f)) else f
    except Exception:
        return None

strategy_bp = Blueprint("strategy", __name__)

# ── Phase → outcome model ────────────────────────────────────────
PHASE_MODEL = {
    "IMPULSE_BULL":        {"dir": "LONG",     "tp": 1.2, "sl": 0.6, "lookahead": 4},
    "IMPULSE_BEAR":        {"dir": "SHORT",    "tp": 1.2, "sl": 0.6, "lookahead": 4},
    "IMPULSE_NEUTRAL":     {"dir": "MEAN",     "tp": 0.8, "sl": 0.6, "lookahead": 3},
    "EXPANSION":           {"dir": "FOLLOW",   "tp": 1.0, "sl": 0.7, "lookahead": 6},
    "DIGESTION":           {"dir": "MEAN",     "tp": 0.6, "sl": 0.6, "lookahead": 6},
    "PULLBACK_FAIL":       {"dir": "FADE",     "tp": 0.6, "sl": 0.5, "lookahead": 5},
    "TREND_CONTINUATION":  {"dir": "LONG",     "tp": 1.2, "sl": 0.8, "lookahead": 12},
    "TREND_ACCEPTANCE":    {"dir": "LONG",     "tp": 1.0, "sl": 0.8, "lookahead": 14},
    "TREND_PAUSE":         {"dir": "LONG",     "tp": 0.8, "sl": 0.7, "lookahead": 10},
    "BALANCE_CHOP":        {"dir": "MEAN",     "tp": 0.5, "sl": 0.5, "lookahead": 6},
    "COMPRESSION":         {"dir": "BREAKOUT", "tp": 0.7, "sl": 0.5, "lookahead": 6},
    "ABSORPTION":          {"dir": "FOLLOW",   "tp": 0.8, "sl": 0.6, "lookahead": 8},
    "DISTRIBUTION":        {"dir": "SHORT",    "tp": 0.8, "sl": 0.6, "lookahead": 8},
}


# ── Helpers ──────────────────────────────────────────────────────
def _simulate_exit(entry, tp, sl, future):
    mfe, mae = 0.0, 0.0
    for idx, r in enumerate(future.itertuples(index=False), start=1):
        mfe = max(mfe, r.high - entry)
        mae = min(mae, r.low  - entry)
        if r.low  <= sl: return "SL_HIT",    sl,       r.ts, idx, mfe, mae
        if r.high >= tp: return "TP_HIT",    tp,       r.ts, idx, mfe, mae
    last = future.iloc[-1]
    return "TIME_EXIT", last.close, last.ts, len(future), mfe, mae


# ── Market context labelling ─────────────────────────────────────
@strategy_bp.route("/api/offline/label-market-context", methods=["POST"])
def offline_label_market_context():
    data      = request.get_json() or {}
    symbol    = (data.get("symbol")    or "").upper().strip()
    exchange  = (data.get("exchange")  or "NSE").upper().strip()
    timeframe = (data.get("timeframe") or "").lower().strip()
    lookahead = int(data.get("lookahead",  20))
    window    = int(data.get("windowSize", 30))

    if not symbol or not timeframe:
        return jsonify({"error": "symbol and timeframe required"}), 400

    with get_db_conn() as conn:
        df = pd.read_sql("""
            SELECT i.*, v.vix
            FROM indicators i
            LEFT JOIN india_vix v
              ON (i.ts AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata')::date = v.trade_date
            WHERE i.symbol=%s AND i.exchange=%s AND i.timeframe=%s
            ORDER BY i.ts ASC
        """, conn, params=[symbol, exchange, timeframe])

    if df.empty or len(df) < lookahead + window:
        return jsonify({"error": "Not enough indicator data"}), 400

    df["ts"] = pd.to_datetime(df["ts"])
    df = df.reset_index(drop=True)

    TF_MINUTES = {"1m":1,"3m":3,"5m":5,"15m":15}
    tf_min = TF_MINUTES.get(timeframe)
    if not tf_min:
        return jsonify({"error": f"Unsupported timeframe {timeframe}"}), 400

    # ── feature engineering (extracted from original) ───────────
    ROLL_5  = max(2, int(5  / tf_min))
    ROLL_10 = max(3, int(10 / tf_min))
    ROLL_20 = max(5, int(20 / tf_min))
    IMPULSE_WINDOW_BARS = int(300 / tf_min)
    VOLUME_MULT = {"1m":1.5,"3m":1.4,"5m":1.3,"15m":1.2}[timeframe]
    GAP_AUCTION_MAX_BARS = int(90 / tf_min)

    df["bar_of_day"] = (df["ts"].dt.hour * 60 + df["ts"].dt.minute - 555) // tf_min
    df["date"] = df["ts"].dt.date

    df["vwap_dist_pct"]  = (df["close"] - df["vwap"]) / df["vwap"]
    df["day_high"]       = df.groupby("date")["high"].cummax()
    df["day_low"]        = df.groupby("date")["low"].cummin()
    df["day_high_dist"]  = (df["day_high"] - df["close"]) / df["day_high"]
    df["day_low_dist"]   = (df["close"] - df["day_low"])  / df["day_low"]
    df["orb_range"]      = (df["orb_high"] - df["orb_low"]).replace(0, np.nan)
    df["orb_mid"]        = (df["orb_high"] + df["orb_low"]) / 2
    df["orb_dist_pct"]   = (df["close"] - df["orb_mid"]) / df["orb_range"]

    daily_close = df.groupby("date")["close"].last().shift(1)
    df["prev_day_close"] = df["date"].map(daily_close)
    df["gap_pct"]        = (df["open"] - df["prev_day_close"]) / df["prev_day_close"]
    df["gap_flag"]       = (df["gap_pct"].abs() > 0.003).astype(int)

    prev_day_atr     = df.groupby("date")["atr_14"].last().shift(1)
    df["prev_day_atr"]= df["date"].map(prev_day_atr)
    df["gap_atr"]    = np.where(df["prev_day_atr"] > 0,
                                (df["open"] - df["prev_day_close"]) / df["prev_day_atr"], 0)
    df["gap_dir"]    = np.select([df["gap_atr"]>0, df["gap_atr"]<0], ["UP","DOWN"], default="NONE")
    df["gap_regime"] = np.select([df["gap_atr"].abs()<0.5, df["gap_atr"].abs()<1.2],
                                  ["NO_GAP","MODERATE_GAP"], default="LARGE_GAP")

    df["ema_21_slope"]   = df["ema_21"].diff().rolling(ROLL_5).mean()
    df["ema_50_slope"]   = df["ema_50"].diff().rolling(ROLL_5).mean()
    df["atr_pct"]        = df["atr_14"] / df["close"]
    df["bb_width"]       = (df["bollinger_upper"] - df["bollinger_lower"]) / df["bollinger_mid"]
    df["range_expansion"]= (df["true_range"] > df["true_range"].rolling(ROLL_5).mean()).astype(int)
    df["volume_z"]       = (df["volume"] - df["volume"].rolling(ROLL_20).mean()) / \
                            df["volume"].rolling(ROLL_20).std()
    df["effort_result"]  = df["volume"] * df["true_range"]
    df["range_efficiency"] = (df["close"] - df["open"]).abs() / df["true_range"].replace(0, np.nan)
    df["volume_expansion"] = (df["volume"] > df["volume"].rolling(ROLL_20).mean() * VOLUME_MULT).astype(int)
    df["atr_expanding"]    = (df["atr_14"] > df["atr_14"].rolling(ROLL_10).mean()).astype(int)
    df["vwap_acceptance"]  = (df["vwap_dist_pct"].abs() < 0.01).astype(int)
    df["momentum_decay"]   = (df["range_efficiency"] < df["range_efficiency"].rolling(ROLL_10).mean()).astype(int)
    df["candle_overlap"]   = (df["high"].rolling(ROLL_5).min() < df["low"].rolling(ROLL_5).max()).astype(int)
    df["minute_of_day"]    = df["bar_of_day"] * tf_min
    df["session_bucket"]   = np.select([df["minute_of_day"]<45, df["minute_of_day"]<300], [0,1], default=2)
    df["expiry_proximity"] = (df["ts"].dt.day >= (df["ts"].dt.days_in_month - 2)).astype(int)

    if "vix" in df.columns:
        df["vix_level"] = df["vix"].ffill()
    else:
        df["vix_level"] = 0.0
    df["vix"]        = df["vix_level"]
    df["vix_change"] = df["vix_level"].diff().fillna(0)
    df["vix_regime"] = np.select([df["vix_level"]<12, df["vix_level"]<18],
                                  ["LOW_VOL","NORMAL_VOL"], default="HIGH_VOL")
    df["news_flag"]  = 0
    if "adx_14" not in df.columns:
        df["adx_14"] = 0

    FEATURE_COLS = [
        "vwap_dist_pct","day_high_dist","day_low_dist","orb_dist_pct","gap_pct","gap_flag",
        "ema_21_slope","ema_50_slope","adx_14","atr_pct","bb_width","range_expansion",
        "volume_z","effort_result","range_efficiency","volume_expansion","atr_expanding",
        "vwap_acceptance","momentum_decay","candle_overlap","minute_of_day",
        "session_bucket","expiry_proximity","vix_level","vix_change","news_flag",
    ]
    for c in FEATURE_COLS:
        df[c] = df[c].replace([np.inf, -np.inf], np.nan).fillna(0)

    # ── phase classification ─────────────────────────────────────
    df["market_phase"]      = "UNCLASSIFIED"
    df["session_context"]   = None
    df["gap_resolved"]      = 0
    df["gap_auction_started"] = 0
    df["gap_auction_active"]  = 0

    df.loc[df["bar_of_day"] == 0, "session_context"] = np.where(
        df.loc[df["bar_of_day"] == 0, "gap_regime"] == "LARGE_GAP", "GAP", "BALANCE"
    )
    df["session_context"] = df.groupby(df["date"])["session_context"].ffill()

    balance_chop     = ((df["range_efficiency"]<0.25)&(df["atr_expanding"]==0)
                        &(df["vwap_dist_pct"].abs()<0.003)&(df["ema_21_slope"].abs()<0.0001))
    trend_acceptance = ((df["ema_21_slope"]>0)&(df["close"]>df["vwap"])
                        &((df["range_efficiency"]>=0.20)|((df["gap_regime"]=="LARGE_GAP")&(df["range_efficiency"]>=0.15)))
                        &(df["atr_expanding"]==0))
    compression      = ((df["atr_pct"]<df["atr_pct"].rolling(ROLL_20).mean()*0.7)
                        &(df["bb_width"]<df["bb_width"].rolling(ROLL_20).mean()*0.7)
                        &(df["range_efficiency"]<0.30))

    df.loc[trend_acceptance & (df["market_phase"]=="UNCLASSIFIED"), "market_phase"] = "TREND_ACCEPTANCE"
    df.loc[compression      & (df["market_phase"]=="UNCLASSIFIED"), "market_phase"] = "COMPRESSION"

    base_impulse = ((df["volume_expansion"]==1)&(df["atr_expanding"]==1)
                    &(df["range_efficiency"]>0.6)&(df["momentum_decay"]==0)
                    &(df["vwap_dist_pct"].abs()>0.004))
    base_impulse &= ((df["bar_of_day"]<IMPULSE_WINDOW_BARS)|(df["volume"]>df["volume"].rolling(ROLL_20).mean()*2))

    bullish_impulse = base_impulse&(df["close"]>df["open"])&(df["close"]>df["ema_21"])&(df["ema_21_slope"]>0)&(df["vwap_dist_pct"]>0)
    bearish_impulse = base_impulse&(df["close"]<df["open"])&(df["close"]<df["ema_21"])&(df["ema_21_slope"]<0)&(df["vwap_dist_pct"]<0)
    neutral_impulse = base_impulse&~bullish_impulse&~bearish_impulse

    df.loc[bullish_impulse&(df["market_phase"]=="UNCLASSIFIED"), "market_phase"] = "IMPULSE_BULL"
    df.loc[bearish_impulse&(df["market_phase"]=="UNCLASSIFIED"), "market_phase"] = "IMPULSE_BEAR"
    df.loc[neutral_impulse&(df["market_phase"]=="UNCLASSIFIED"), "market_phase"] = "IMPULSE_NEUTRAL"

    gap_auction_entry = ((df["session_context"]=="GAP")&(df["gap_resolved"]==0)
                         &(df["candle_overlap"]==1)&(df["range_efficiency"]<0.30)&(df["atr_expanding"]==0))
    gap_auction_resolved = ((df["range_efficiency"]>0.45)&(df["atr_expanding"]==1)&(df["vwap_dist_pct"].abs()>0.004))
    gap_auction_failed   = ((df["range_efficiency"]<0.20)&(df["volume"]<df["volume"].rolling(ROLL_20).mean())&(df["vwap_acceptance"]==1))
    absorption     = ((df["close"]>df["vwap"])&(df["volume"]>df["volume"].rolling(ROLL_20).mean())
                      &(df["atr_expanding"]==0)&(df["range_efficiency"]<0.35)&(df["vwap_acceptance"]==1))
    distribution   = absorption&(df["bb_width"]>df["bb_width"].rolling(ROLL_20).mean())
    trend_valid    = ((df["ema_21_slope"]>0)&(df["close"]>df["vwap"])&(df["range_efficiency"]>0.35))
    trend_pause    = ((df["ema_21_slope"]>0)&(df["close"]>df["ema_21"])&(df["range_efficiency"]>=0.20)&(df["range_efficiency"]<0.35)&(df["volume"]>df["volume"].rolling(ROLL_20).mean()))
    trend_digestion= ((df["range_efficiency"]>=0.15)&(df["range_efficiency"]<0.30)&(df["atr_expanding"]==0)&(df["close"]>df["vwap"])&(df["ema_21_slope"]>0))
    absorption_break    = (df["range_efficiency"]>0.45)|(df["atr_expanding"]==1)
    distribution_break  = (df["close"]>df["vwap"])|(df["range_efficiency"]>0.45)

    df["post_impulse_active"] = 0
    df["post_impulse_story"]  = None
    df["impulse_dir"]         = None
    vol_ma20 = df["volume"].rolling(ROLL_20).mean()

    for i in range(1, len(df)):
        if df.at[i,"session_context"]=="GAP" and df.at[i,"gap_resolved"]==0 \
                and df.at[i,"gap_auction_started"]==0 and gap_auction_entry.iloc[i]:
            df.at[i,"gap_auction_started"] = 1
            df.at[i,"gap_auction_active"]  = 1
            df.at[i,"gap_auction_start_bar"] = df.at[i,"bar_of_day"]
            continue

        if df.at[i-1,"gap_auction_active"]==1 and df.at[i,"gap_resolved"]==0:
            start_bar     = df.at[i-1,"gap_auction_start_bar"] if "gap_auction_start_bar" in df.columns else 0
            bars_elapsed  = df.at[i,"bar_of_day"] - start_bar
            if gap_auction_resolved.iloc[i] or gap_auction_failed.iloc[i] or bars_elapsed >= GAP_AUCTION_MAX_BARS:
                df.at[i,"gap_auction_active"] = 0
                df.at[i,"gap_resolved"]       = 1
                df.at[i,"session_context"]    = "BALANCE"
            else:
                df.at[i,"gap_auction_active"] = 1
            if df.at[i,"gap_auction_active"]==1:
                if bullish_impulse.iloc[i]: df.at[i,"market_phase"] = "AUCTION_IMPULSE_UP"
                elif bearish_impulse.iloc[i]: df.at[i,"market_phase"] = "AUCTION_IMPULSE_DOWN"
                elif neutral_impulse.iloc[i]: df.at[i,"market_phase"] = "AUCTION_IMPULSE_NEUTRAL"
            continue

        if df.at[i-1,"gap_resolved"]==1:
            df.at[i,"gap_resolved"]    = 1
            df.at[i,"session_context"] = "BALANCE"

        impulse_allowed = df.at[i,"gap_auction_active"] == 0

        if impulse_allowed and bullish_impulse.iloc[i-1]:
            df.at[i,"post_impulse_active"] = 1; df.at[i,"impulse_dir"] = "BULL"
        elif impulse_allowed and bearish_impulse.iloc[i-1]:
            df.at[i,"post_impulse_active"] = 1; df.at[i,"impulse_dir"] = "BEAR"
        elif impulse_allowed and neutral_impulse.iloc[i-1]:
            df.at[i,"post_impulse_active"] = 1; df.at[i,"impulse_dir"] = "NEUTRAL"
        else:
            df.at[i,"post_impulse_active"] = df.at[i-1,"post_impulse_active"]
            df.at[i,"impulse_dir"]         = df.at[i-1,"impulse_dir"]

        if df.at[i,"post_impulse_active"]==1:
            idir = df.at[i,"impulse_dir"]
            if (df.at[i,"range_efficiency"]<0.25 and df.at[i,"atr_expanding"]==0 and
                ((idir=="BULL" and df.at[i,"close"]<df.at[i-1,"close"]) or
                 (idir=="BEAR" and df.at[i,"close"]>df.at[i-1,"close"]))):
                df.at[i,"market_phase"]="PULLBACK_FAIL"; df.at[i,"post_impulse_story"]="WEAK_PULLBACK"; continue
            if (df.at[i,"volume"]>vol_ma20.iloc[i] and df.at[i,"atr_expanding"]==0 and df.at[i,"range_efficiency"]<0.35):
                df.at[i,"market_phase"]="ABSORPTION"; df.at[i,"post_impulse_story"]="EFFORT_NO_PROGRESS"; continue
            if ((idir=="BULL" and df.at[i,"close"]<df.at[i-1,"low"]) or
                (idir=="BEAR" and df.at[i,"close"]>df.at[i-1,"high"]) or
                (idir=="NEUTRAL" and df.at[i,"range_efficiency"]<0.20)):
                df.at[i,"market_phase"]="REJECTION"; df.at[i,"post_impulse_story"]="STRUCTURAL_FAILURE"
                df.at[i,"post_impulse_active"]=0; continue
            if (df.at[i,"atr_expanding"]==1 and df.at[i,"range_efficiency"]>0.50 and
                ((idir=="BULL" and df.at[i,"close"]>df.at[i-1,"high"]) or
                 (idir=="BEAR" and df.at[i,"close"]<df.at[i-1,"low"]))):
                df.at[i,"market_phase"]="EXPANSION"; df.at[i,"post_impulse_story"]="CONTINUATION_CONFIRMED"
                df.at[i,"post_impulse_active"]=0; continue
            df.at[i,"market_phase"]="POST_IMPULSE_DIGESTION"
            continue

        prev_phase = df.at[i-1,"market_phase"]
        if prev_phase in ("IMPULSE_BULL","IMPULSE_BEAR","TREND_CONTINUATION"):
            df.at[i,"market_phase"] = ("TREND_CONTINUATION" if trend_valid.iloc[i]
                                       else "TREND_DIGESTION" if trend_digestion.iloc[i]
                                       else "TREND_PAUSE"     if trend_pause.iloc[i]
                                       else "TREND_ACCEPTANCE")
        elif prev_phase=="TREND_DIGESTION":
            df.at[i,"market_phase"] = "TREND_CONTINUATION" if trend_valid.iloc[i] else "TREND_DIGESTION"
        elif prev_phase=="TREND_PAUSE":
            df.at[i,"market_phase"] = "TREND_CONTINUATION" if trend_valid.iloc[i] else "TREND_PAUSE"
        elif prev_phase=="ABSORPTION" and not absorption_break.iloc[i]:
            df.at[i,"market_phase"] = "ABSORPTION"
        elif prev_phase=="DISTRIBUTION" and not distribution_break.iloc[i]:
            df.at[i,"market_phase"] = "DISTRIBUTION"
        elif df.at[i,"market_phase"]=="UNCLASSIFIED":
            df.at[i,"market_phase"] = ("DISTRIBUTION" if distribution.iloc[i]
                                       else "ABSORPTION" if absorption.iloc[i]
                                       else "BALANCE_CHOP")

    # ORB quality
    TF_MIN = tf_min
    df["orb_breakout"] = ((df["close"]>df["orb_high"])&(df["bar_of_day"]<=int(90/TF_MIN))).astype(int)
    df["orb_quality"]  = ((df["volume_expansion"]==1)&(df["atr_expanding"]==1)&(df["range_efficiency"]>0.45)).astype(int)
    df["orb_location"] = ((df["close"]>df["ema_21"])&(df["vwap_dist_pct"]>0)).astype(int)
    df["ORB"] = ((df["orb_breakout"]==1)&(df["orb_quality"]==1)&(df["orb_location"]==1)).astype(int)

    df = df.iloc[window:].reset_index(drop=True)
    now = datetime.utcnow()
    market_rows, rule_rows = [], []

    for _, r in df.iterrows():
        market_rows.append((
            symbol, exchange, timeframe, r["ts"], r["market_phase"],
            r["ema_21_slope"], r["vwap_dist_pct"], r["day_high_dist"], r["day_low_dist"],
            r["orb_dist_pct"], r["gap_pct"], r["minute_of_day"],
            r["volume_expansion"], r["atr_expanding"], r["range_efficiency"],
            r["vwap_acceptance"], r["momentum_decay"], r["candle_overlap"],
            r["vix"], r["vix_change"], r["vix_regime"],
            r["gap_atr"], r["gap_dir"], r["gap_regime"], now,
        ))
        rules = {
            "ORB":              (r["ORB"] == 1),
            "EMA_TREND":        (r["ema_21_slope"]>0 and r["close"]>r["ema_21"]),
            "VWAP_TREND":       (r["vwap_dist_pct"]>0 and r["vwap_acceptance"]==0),
            "ATR_EXPANSION":    (r["atr_expanding"]==1),
            "VOLUME_EXPANSION": (r["volume_expansion"]==1 and r["range_efficiency"]>0.35),
        }
        for name, eligible in rules.items():
            rule_rows.append((
                symbol, exchange, timeframe, r["ts"], name, bool(eligible),
                json.dumps({
                    "orb_high": json_safe(r["orb_high"]), "orb_low": json_safe(r["orb_low"]),
                    "orb_breakout": int(r["orb_breakout"]), "orb_quality": int(r["orb_quality"]),
                    "orb_location": int(r["orb_location"]), "minute_of_day": int(r["minute_of_day"]),
                    "ema_21_slope": json_safe(r["ema_21_slope"]), "vwap_dist_pct": json_safe(r["vwap_dist_pct"]),
                    "atr_expanding": int(r["atr_expanding"]), "volume_expansion": int(r["volume_expansion"]),
                    "range_efficiency": json_safe(r["range_efficiency"]),
                }),
                r["market_phase"], now,
            ))

    with get_db_conn() as conn:
        with conn.cursor() as cur:
            execute_values(cur, """
                INSERT INTO market_context (
                    symbol,exchange,timeframe,ts,market_phase,ema_21_slope,
                    vwap_dist_pct,day_high_dist,day_low_dist,orb_dist_pct,gap_pct,minute_of_day,
                    volume_expansion,atr_expanding,range_efficiency,vwap_acceptance,
                    momentum_decay,candle_overlap,vix,vix_change,vix_regime,
                    gap_atr,gap_dir,gap_regime,created_at
                ) VALUES %s
                ON CONFLICT (symbol,exchange,timeframe,ts) DO UPDATE SET
                    market_phase=EXCLUDED.market_phase, ema_21_slope=EXCLUDED.ema_21_slope,
                    vwap_dist_pct=EXCLUDED.vwap_dist_pct, gap_atr=EXCLUDED.gap_atr,
                    gap_dir=EXCLUDED.gap_dir, gap_regime=EXCLUDED.gap_regime,
                    created_at=EXCLUDED.created_at
            """, market_rows)
            execute_values(cur, """
                INSERT INTO rule_evaluations (
                    symbol,exchange,timeframe,ts,strategy_id,
                    rule_eligibility,condition_snapshot,market_phase,created_at
                ) VALUES %s
                ON CONFLICT (symbol,exchange,timeframe,ts,strategy_id) DO UPDATE SET
                    rule_eligibility=EXCLUDED.rule_eligibility,
                    condition_snapshot=EXCLUDED.condition_snapshot,
                    market_phase=EXCLUDED.market_phase, created_at=EXCLUDED.created_at
            """, rule_rows)

    return jsonify({"status":"SUCCESS","market_rows":len(market_rows),"rule_rows":len(rule_rows)})


# ── Strategy outcomes ────────────────────────────────────────────
@strategy_bp.route("/api/offline/calc-strategy-outcomes", methods=["POST"])
def calc_strategy_outcomes():
    try:
        data      = request.get_json() or {}
        symbol    = (data.get("symbol")   or "").upper().strip()
        timeframe = (data.get("timeframe") or "").lower().strip()
        exchange  = (data.get("exchange")  or "NSE").upper().strip()
        to_dt   = pd.to_datetime(data.get("to_date")   or datetime.utcnow(), utc=True)
        from_dt = pd.to_datetime(data.get("from_date") or (to_dt - timedelta(days=180)), utc=True)

        if not symbol or not timeframe:
            return jsonify({"error": "symbol and timeframe required"}), 400

        with get_db_conn() as conn:
            df = pd.read_sql("""
                SELECT i.ts,i.open,i.high,i.low,i.close,i.atr_14,
                       mc.market_phase,mc.minute_of_day,mc.ema_21_slope,mc.vwap_dist_pct,mc.range_efficiency
                FROM indicators i
                JOIN market_context mc ON i.symbol=mc.symbol AND i.exchange=mc.exchange
                    AND i.timeframe=mc.timeframe AND i.ts=mc.ts
                WHERE i.symbol=%s AND i.exchange=%s AND i.timeframe=%s AND i.ts BETWEEN %s AND %s
                ORDER BY i.ts
            """, conn, params=[symbol, exchange, timeframe, from_dt, to_dt])

            if df.empty:
                return jsonify({"error": "No data found"}), 400

            df["ts"] = pd.to_datetime(df["ts"], utc=True)
            df = df.sort_values("ts").reset_index(drop=True)

            rules_df = pd.read_sql("""
                SELECT ts,strategy_id,rule_eligibility,condition_snapshot
                FROM rule_evaluations
                WHERE symbol=%s AND exchange=%s AND timeframe=%s AND ts BETWEEN %s AND %s
            """, conn, params=[symbol, exchange, timeframe, from_dt, to_dt])

        rules_df["ts"]          = pd.to_datetime(rules_df["ts"], utc=True)
        rules_df["strategy_id"] = rules_df["strategy_id"].str.upper().str.strip()
        rule_truth = (rules_df.drop_duplicates(["ts","strategy_id"], keep="last")
                      .set_index(["ts","strategy_id"])["rule_eligibility"].to_dict())
        snapshots  = (rules_df.dropna(subset=["condition_snapshot"]).drop_duplicates("ts")
                      .set_index("ts")["condition_snapshot"]
                      .apply(lambda x: x if isinstance(x, dict) else json.loads(x)).to_dict())

        rows = []
        now  = datetime.utcnow()

        for i in range(len(df)):
            row = df.iloc[i]
            cfg = PHASE_MODEL.get(row.market_phase)
            if not cfg or i + cfg["lookahead"] >= len(df):
                continue
            atr = float(row.atr_14)
            if atr <= 0:
                continue
            entry     = float(row.close)
            direction = cfg["dir"]
            tp = entry - cfg["tp"]*atr if direction=="SHORT" else entry + cfg["tp"]*atr
            sl = entry + cfg["sl"]*atr if direction=="SHORT" else entry - cfg["sl"]*atr
            future    = df.iloc[i+1:i+1+cfg["lookahead"]]
            exit_reason, exit_price, exit_ts, exit_after, mfe, mae = _simulate_exit(entry, tp, sl, future)
            if exit_ts <= row.ts:
                continue
            R          = abs(entry - sl)
            mfe_r      = mfe/R if R>0 else 0
            mae_r      = mae/R if R>0 else 0
            realized_r = ((tp-entry)/R if exit_reason=="TP_HIT"
                          else -1.0    if exit_reason=="SL_HIT"
                          else (exit_price-entry)/R if R>0 else 0)
            exit_speed  = exit_after/cfg["lookahead"]
            timing      = "FAST" if exit_speed<=0.33 else "NORMAL" if exit_speed<=0.66 else "LATE"
            ts   = row.ts
            snap = snapshots.get(ts, {})
            rows.append((
                symbol, exchange, timeframe, ts, row.market_phase, int(row.minute_of_day),
                rule_truth.get((ts,"ORB"),False), rule_truth.get((ts,"EMA_TREND"),False),
                rule_truth.get((ts,"ATR_EXPANSION"),False), rule_truth.get((ts,"VWAP_TREND"),False),
                rule_truth.get((ts,"VOLUME_EXPANSION"),False),
                row.ema_21_slope, row.vwap_dist_pct, atr, row.range_efficiency,
                int(snap.get("orb_quality",0)), int(snap.get("orb_location",0)),
                realized_r if rule_truth.get((ts,"ORB"),False) else None,
                realized_r if rule_truth.get((ts,"EMA_TREND"),False) else None,
                realized_r if rule_truth.get((ts,"ATR_EXPANSION"),False) else None,
                realized_r if rule_truth.get((ts,"VWAP_TREND"),False) else None,
                realized_r if rule_truth.get((ts,"VOLUME_EXPANSION"),False) else None,
                exit_reason, exit_ts, mfe, mae, cfg["lookahead"], now,
                mfe_r, mae_r, realized_r, exit_after, exit_speed, timing,
            ))

        if not rows:
            return jsonify({"error": "No outcomes generated"}), 400

        with get_db_conn() as conn:
            with conn.cursor() as cur:
                execute_values(cur, """
                    INSERT INTO strategy_outcomes (
                        symbol,exchange,timeframe,ts,market_phase,minute_of_day,
                        orb_fired,ema_trend_fired,atr_expansion_fired,vwap_trend_fired,volume_expansion_fired,
                        ema_21_slope,vwap_dist_pct,atr_14,range_efficiency,orb_quality,orb_location,
                        orb_outcome,ema_trend_outcome,atr_expansion_outcome,vwap_trend_outcome,volume_expansion_outcome,
                        exit_reason,exit_ts,mfe,mae,lookahead_candles,created_at,
                        mfe_r,mae_r,realized_r,exit_after_candles,exit_speed_ratio,outcome_timing
                    ) VALUES %s
                    ON CONFLICT (symbol,exchange,timeframe,ts) DO UPDATE SET
                        market_phase=EXCLUDED.market_phase, orb_fired=EXCLUDED.orb_fired,
                        realized_r=EXCLUDED.realized_r, outcome_timing=EXCLUDED.outcome_timing,
                        created_at=EXCLUDED.created_at
                """, rows)

        return jsonify({"status": "SUCCESS", "rows_written": len(rows)})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ── Rule stats ───────────────────────────────────────────────────
@strategy_bp.route("/api/market-context/rule-stats", methods=["GET"])
def get_rule_stats():
    symbol    = (request.args.get("symbol")    or "").upper().strip()
    timeframe = (request.args.get("timeframe") or "").lower().strip()
    if not symbol or not timeframe:
        return jsonify({"error": "symbol and timeframe required"}), 400

    with get_db_conn() as conn:
        df = pd.read_sql("""
            SELECT ts,orb_outcome,ema_outcome,atr_outcome,vwap_outcome,bb_outcome,exit_reason
            FROM strategy_outcomes WHERE symbol=%s AND timeframe=%s ORDER BY ts
        """, conn, params=[symbol, timeframe])

    if df.empty:
        return jsonify({"symbol":symbol,"timeframe":timeframe,"test_period":None,"months_tested":0,"rules":[]})

    df["ts"] = pd.to_datetime(df["ts"])
    df["year_month"] = df["ts"].dt.to_period("M").astype(str)
    months = sorted(df["year_month"].unique().tolist())

    def stats(col):
        s = df[col].dropna()
        if s.empty: return {"samples":0,"success_rate":0,"failure_rate":0,"chop_rate":0}
        t = len(s)
        return {"samples":t,
                "success_rate": round((s==1).sum()/t, 3),
                "failure_rate": round((s==-1).sum()/t, 3),
                "chop_rate":    round((s==0).sum()/t, 3)}

    return jsonify({
        "symbol": symbol, "timeframe": timeframe,
        "test_period": {"from": df["ts"].min().isoformat(), "to": df["ts"].max().isoformat()},
        "months_tested": {"count": len(months), "list": months},
        "rules": [
            {"name":"ORB",           **stats("orb_outcome")},
            {"name":"EMA_TREND",     **stats("ema_outcome")},
            {"name":"ATR_EXPANSION", **stats("atr_outcome")},
            {"name":"VWAP_TREND",    **stats("vwap_outcome")},
            {"name":"BB_EXPANSION",  **stats("bb_outcome")},
        ],
    })
