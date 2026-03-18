# routes/ml.py
# ================================================================
#  ML training + paper trading blueprint:
#    POST /api/train-pipeline
#    POST /api/paper-trade/run
#    GET  /api/paper-trade/equity-curve
#    POST /api/paper-trade/compare-thresholds
# ================================================================
import os, traceback
from collections import defaultdict
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
from flask import Blueprint, request, jsonify
from sqlalchemy import create_engine, text

ml_bp = Blueprint("ml", __name__)

NUM_FEATURES  = ["minute_of_day","ema_21_slope","vwap_dist_pct","atr_14","range_efficiency"]
RULE_FEATURES = ["orb_fired","ema_trend_fired","atr_expansion_fired","vwap_trend_fired","volume_expansion_fired"]
CAT_FEATURES  = ["market_phase"]
RULES = {
    "ORB":              "orb_fired",
    "EMA_TREND":        "ema_trend_fired",
    "VWAP_TREND":       "vwap_trend_fired",
    "ATR_EXPANSION":    "atr_expansion_fired",
    "VOLUME_EXPANSION": "volume_expansion_fired",
}
PHASE_RISK      = {"IMPULSE":0.015,"TREND_CONTINUATION":0.012,"TREND_ACCEPTANCE":0.010,"TREND_PAUSE":0.005}
PHASE_RR        = {"IMPULSE":4.0, "TREND_CONTINUATION":3.0,  "TREND_ACCEPTANCE":2.5,  "TREND_PAUSE":1.5}
PHASE_LOOKAHEAD = {"IMPULSE":8,   "TREND_CONTINUATION":30,   "TREND_ACCEPTANCE":20,   "TREND_PAUSE":10}
ALLOWED_PHASES  = set(PHASE_RISK.keys())


def _get_engine():
    return create_engine(
        f"postgresql+psycopg2://{os.getenv('PGUSER')}:{os.getenv('PGPASSWORD')}"
        f"@{os.getenv('PGHOST')}:{os.getenv('PGPORT')}/{os.getenv('PGDATABASE')}"
    )


def _prep_pipeline():
    from sklearn.pipeline import Pipeline
    from sklearn.compose import ColumnTransformer
    from sklearn.preprocessing import OneHotEncoder
    prep = ColumnTransformer([
        ("num", "passthrough", NUM_FEATURES),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CAT_FEATURES),
    ])
    return prep


# ── Train pipeline ───────────────────────────────────────────────
@ml_bp.route("/api/train-pipeline", methods=["POST"])
def train_pipeline():
    data      = request.get_json() or {}
    symbol    = data.get("symbol")
    timeframe = data.get("timeframe")
    if not symbol or not timeframe:
        return jsonify({"error": "symbol and timeframe required"}), 400

    engine  = _get_engine()
    results = {}
    for rule_name, rule_col in RULES.items():
        results[rule_name] = {
            "edge_gate":          _train_edge_gate(symbol, timeframe, rule_name, rule_col, engine),
            "context_expectancy": _train_context_expectancy(symbol, timeframe, rule_name, rule_col, engine),
            "edge_decay":         _train_edge_decay(symbol, timeframe, rule_name, rule_col, engine),
        }
    return jsonify({"status":"SUCCESS","symbol":symbol,"timeframe":timeframe,"rules":results})


def _base_sql(rule_col, target_col, extra_select=""):
    return f"""
        SELECT so.ts, mc.market_phase, mc.minute_of_day,
               so.ema_21_slope, so.vwap_dist_pct, so.atr_14, so.range_efficiency{extra_select}
        FROM strategy_outcomes so
        JOIN market_context mc ON so.symbol=mc.symbol AND so.timeframe=mc.timeframe AND so.ts=mc.ts
        WHERE so.symbol=%(symbol)s AND so.timeframe=%(timeframe)s
          AND so.{rule_col} IS TRUE {target_col}
        ORDER BY so.ts
    """


def _save_model_run(engine, symbol, timeframe, model_type, train_df, test_df, rows, extra={}):
    os.makedirs("models", exist_ok=True)
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO ml_model_runs
            (symbol,timeframe,model_type,trained_at,train_from,train_to,test_from,test_to,rows_used,model_path)
            VALUES (:symbol,:tf,:model_type,:trained_at,:train_from,:train_to,:test_from,:test_to,:rows,:path)
        """), {"symbol":symbol,"tf":timeframe,"model_type":model_type,
               "trained_at":datetime.utcnow(),
               "train_from":train_df.ts.min(),"train_to":train_df.ts.max(),
               "test_from":test_df.ts.min(),"test_to":test_df.ts.max(),
               "rows":rows, **extra})


def _train_edge_gate(symbol, timeframe, rule_name, rule_col, engine):
    try:
        import lightgbm as lgb
        from sklearn.pipeline import Pipeline
        from sklearn.metrics import roc_auc_score
        sql = _base_sql(rule_col,
            "AND so.exit_reason IN ('TP_HIT','SL_HIT')",
            ", CASE WHEN so.realized_r > 0 THEN 1 ELSE 0 END AS label")
        df = pd.read_sql(sql, engine, params={"symbol":symbol,"timeframe":timeframe}, parse_dates=["ts"])
        if len(df) < 500: return {"status":"FAILED","reason":"Insufficient data"}
        train_df = df[df.ts < "2025-12-01"]; test_df = df[df.ts >= "2025-12-01"]
        X_train, y_train = train_df.drop(columns=["ts","label"]), train_df["label"]
        X_test,  y_test  = test_df.drop( columns=["ts","label"]), test_df["label"]
        pipe = Pipeline([("prep", _prep_pipeline()), ("model", lgb.LGBMClassifier(n_estimators=300, learning_rate=0.04, random_state=42))])
        pipe.fit(X_train, y_train)
        auc  = roc_auc_score(y_test, pipe.predict_proba(X_test)[:,1])
        path = f"models/edge_gate_{rule_name}_{symbol}_{timeframe}_{datetime.utcnow():%Y%m%d_%H%M}.pkl"
        joblib.dump(pipe, path)
        _save_model_run(engine, symbol, timeframe, f"edge_gate:{rule_name}", train_df, test_df, len(df),
                        {"path":path, "auc":auc})
        return {"status":"SUCCESS","rule":rule_name,"auc":round(auc,4),"model_path":path}
    except Exception as e:
        traceback.print_exc(); return {"status":"FAILED","reason":str(e)}


def _train_context_expectancy(symbol, timeframe, rule_name, rule_col, engine):
    try:
        import lightgbm as lgb
        from sklearn.pipeline import Pipeline
        from sklearn.metrics import root_mean_squared_error
        sql = _base_sql(rule_col, "AND so.realized_r IS NOT NULL", ", so.realized_r")
        df  = pd.read_sql(sql, engine, params={"symbol":symbol,"timeframe":timeframe}, parse_dates=["ts"])
        if len(df)<500: return {"status":"FAILED","reason":"Insufficient data"}
        train_df = df[df.ts<"2025-12-01"]; test_df = df[df.ts>="2025-12-01"]
        pipe = Pipeline([("prep",_prep_pipeline()),("model",lgb.LGBMRegressor(n_estimators=600,learning_rate=0.02,random_state=42))])
        pipe.fit(train_df.drop(columns=["ts","realized_r"]), train_df["realized_r"])
        rmse = root_mean_squared_error(test_df["realized_r"], pipe.predict(test_df.drop(columns=["ts","realized_r"])))
        path = f"models/context_expectancy_{rule_name}_{symbol}_{timeframe}_{datetime.utcnow():%Y%m%d_%H%M}.pkl"
        joblib.dump(pipe, path)
        _save_model_run(engine, symbol, timeframe, f"context_expectancy:{rule_name}", train_df, test_df, len(df), {"path":path})
        return {"status":"SUCCESS","rmse":round(rmse,4),"model_path":path}
    except Exception as e:
        traceback.print_exc(); return {"status":"FAILED","reason":str(e)}


def _train_edge_decay(symbol, timeframe, rule_name, rule_col, engine):
    try:
        import lightgbm as lgb
        from sklearn.pipeline import Pipeline
        from sklearn.metrics import root_mean_squared_error
        sql = f"""
            SELECT so.ts, mc.market_phase, mc.minute_of_day,
                   so.ema_21_slope, so.vwap_dist_pct, so.atr_14, so.range_efficiency,
                   (AVG(so.realized_r) OVER (ORDER BY so.ts ROWS BETWEEN 3 PRECEDING AND CURRENT ROW)
                  - AVG(so.realized_r) OVER (ORDER BY so.ts ROWS BETWEEN 6 PRECEDING AND 4 PRECEDING)) AS edge_velocity
            FROM strategy_outcomes so
            JOIN market_context mc ON so.symbol=mc.symbol AND so.timeframe=mc.timeframe AND so.ts=mc.ts
            WHERE so.symbol=%(symbol)s AND so.timeframe=%(timeframe)s
              AND so.{rule_col} IS TRUE AND so.realized_r IS NOT NULL ORDER BY so.ts
        """
        df = pd.read_sql(sql, engine, params={"symbol":symbol,"timeframe":timeframe}, parse_dates=["ts"]).dropna()
        if len(df)<500: return {"status":"FAILED","reason":"Insufficient data"}
        train_df = df[df.ts<"2025-12-01"]; test_df = df[df.ts>="2025-12-01"]
        pipe = Pipeline([("prep",_prep_pipeline()),("model",lgb.LGBMRegressor(n_estimators=500,learning_rate=0.02,random_state=42))])
        pipe.fit(train_df.drop(columns=["ts","edge_velocity"]), train_df["edge_velocity"])
        rmse = root_mean_squared_error(test_df["edge_velocity"], pipe.predict(test_df.drop(columns=["ts","edge_velocity"])))
        path = f"models/edge_decay_{rule_name}_{symbol}_{timeframe}_{datetime.utcnow():%Y%m%d_%H%M}.pkl"
        joblib.dump(pipe, path)
        _save_model_run(engine, symbol, timeframe, f"edge_decay:{rule_name}", train_df, test_df, len(df), {"path":path})
        return {"status":"SUCCESS","rmse":round(rmse,4),"model_path":path}
    except Exception as e:
        traceback.print_exc(); return {"status":"FAILED","reason":str(e)}


# ── Paper trading ────────────────────────────────────────────────
@ml_bp.route("/api/paper-trade/run", methods=["POST"])
def run_paper_trade():
    data = request.get_json() or {}
    for k in ["model_run_id","symbol","timeframe","margin_per_share"]:
        if k not in data:
            return jsonify({"error": f"{k} is required"}), 400

    model_run_id      = int(data["model_run_id"])
    symbol            = data["symbol"]
    timeframe         = data["timeframe"]
    margin_per_share  = float(data["margin_per_share"])
    threshold         = float(data.get("threshold", 0.6))
    starting_capital  = float(data.get("starting_capital", 10000))
    if margin_per_share <= 0:
        return jsonify({"error": "margin_per_share must be > 0"}), 400

    CAPITAL_STOP       = 7000
    MAX_TRADES_PER_DAY = 5
    engine             = _get_engine()

    row = pd.read_sql("SELECT model_path FROM ml_model_runs WHERE id=%(id)s",
                      engine, params={"id": model_run_id})
    if row.empty:
        return jsonify({"error": "Invalid model_run_id"}), 400

    model = joblib.load(row.iloc[0]["model_path"])

    df = pd.read_sql("""
        SELECT r.ts, r.strategy_id AS rule_type, r.market_phase,
               i.close, i.high, i.low, i.atr_14,
               i.ema_21, (i.ema_21-i.ema_50) AS ema_trend_strength,
               i.volume_ratio, (i.close-i.vwap)/NULLIF(i.vwap,0) AS vwap_dist_pct,
               i.obv, i.orb_breakout::int, i.rsi_14, i.macd_hist,
               CASE WHEN i.supertrend_signal='UP' THEN 1
                    WHEN i.supertrend_signal='DOWN' THEN -1 ELSE 0 END AS supertrend_signal
        FROM rule_evaluations r
        JOIN indicators i USING (symbol,exchange,timeframe,ts)
        WHERE r.rule_eligibility=true AND r.symbol=%(symbol)s AND r.timeframe=%(tf)s
        ORDER BY r.ts
    """, engine, params={"symbol":symbol,"tf":timeframe}, parse_dates=["ts"])

    if df.empty:
        return jsonify({"error": "No eligible trades found"}), 400

    df["prob"] = model.predict_proba(df)[:,1]

    capital = starting_capital; peak = capital; max_dd = 0.0
    trades  = []; wins = losses = 0
    daily_trades = defaultdict(int)

    for i in range(len(df)-1):
        if capital <= CAPITAL_STOP: break
        row       = df.iloc[i]
        phase     = row["market_phase"]
        trade_date= row["ts"].date()
        if phase not in ALLOWED_PHASES or daily_trades[trade_date] >= MAX_TRADES_PER_DAY: continue
        if row["prob"] < threshold: continue
        atr = float(row["atr_14"])
        if atr <= 0: continue
        risk_amount = capital * PHASE_RISK[phase]
        entry = float(row["close"])
        sl    = entry - atr
        tp    = entry + PHASE_RR[phase] * atr
        qty   = min(int(risk_amount/atr), int(capital/margin_per_share))
        if qty <= 0: continue
        lookahead = PHASE_LOOKAHEAD[phase]
        future    = df.iloc[i+1:i+1+lookahead]
        future    = future[future["ts"].dt.date == trade_date]
        exit_price, exit_reason = entry, "TIME_EXIT"
        for _, f in future.iterrows():
            if f["low"]<=sl:  exit_price=sl;  exit_reason="SL_HIT";  break
            if f["high"]>=tp: exit_price=tp;  exit_reason="TP_HIT";  break
        pnl     = (exit_price - entry) * qty
        capital = max(capital + pnl, 0)
        peak    = max(peak, capital)
        max_dd  = max(max_dd, (peak-capital)/peak if peak>0 else 0)
        wins   += pnl>0; losses += pnl<=0
        daily_trades[trade_date] += 1
        trades.append({"paper_trade_run_id":None,"model_run_id":model_run_id,
                        "symbol":symbol,"timeframe":timeframe,"trade_ts":row["ts"],
                        "trade_date":trade_date,"rule_type":row["rule_type"],"market_phase":phase,
                        "probability":float(row["prob"]),"threshold":threshold,
                        "result":"WIN" if pnl>0 else "LOSS",
                        "entry_price":entry,"exit_price":exit_price,"qty":qty,
                        "margin_used":qty*margin_per_share,"pnl":pnl,
                        "exit_reason":exit_reason,"capital_after":capital})

    total_trades = wins + losses
    win_rate     = wins / max(total_trades, 1)
    expectancy   = win_rate - (1 - win_rate)

    with engine.begin() as conn:
        run_id = conn.execute(text("""
            INSERT INTO paper_trade_runs (
                model_run_id,symbol,timeframe,threshold,starting_capital,final_capital,
                total_trades,wins,losses,win_rate,expectancy,max_drawdown_pct
            ) VALUES (:mr,:sym,:tf,:th,:start,:final,:tt,:w,:l,:wr,:exp,:dd) RETURNING id
        """), {"mr":model_run_id,"sym":symbol,"tf":timeframe,"th":threshold,
               "start":starting_capital,"final":capital,"tt":total_trades,
               "w":wins,"l":losses,"wr":win_rate,"exp":expectancy,"dd":max_dd*100}).scalar()

    if trades:
        for t in trades: t["paper_trade_run_id"] = run_id
        pd.DataFrame(trades).to_sql("paper_trades", engine, if_exists="append", index=False)

    return jsonify({"status":"SUCCESS","paper_trade_run_id":run_id,
                    "final_capital":round(capital,2),"net_pnl":round(capital-starting_capital,2),
                    "total_trades":total_trades,"win_rate":round(win_rate,4),
                    "max_drawdown_pct":round(max_dd*100,2)})


@ml_bp.route("/api/paper-trade/equity-curve", methods=["GET"])
def paper_equity_curve():
    run_id = request.args.get("run_id", type=int)
    if not run_id:
        return jsonify({"error": "run_id is required"}), 400
    engine = _get_engine()
    df = pd.read_sql("SELECT trade_ts AS time, capital_after AS capital FROM paper_trades "
                     "WHERE paper_trade_run_id=%(id)s ORDER BY trade_ts",
                     engine, params={"id": run_id})
    return jsonify({"run_id": run_id, "curve": df.to_dict(orient="records")})


@ml_bp.route("/api/paper-trade/compare-thresholds", methods=["POST"])
def compare_thresholds():
    data    = request.get_json() or {}
    results = {}
    for t in data.get("thresholds", []):
        data["threshold"] = t
        with ml_bp.open_resource("") if False else __import__("contextlib").nullcontext():
            resp = run_paper_trade().get_json()
        results[str(t)] = {k: resp.get(k) for k in
                           ["final_capital","net_pnl","total_trades","win_rate","max_drawdown_pct"]}
    return jsonify(results)
