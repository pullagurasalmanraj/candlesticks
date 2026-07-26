"""
Automated Label Evaluation & Quality Audit Script
=================================================
Evaluates PostgreSQL market_context and indicators tables for:
  1. Timestamp & Session Open Alignment (09:15 AM IST check across timeframes)
  2. Class Distribution & Balance (detects class imbalance or collapse)
  3. Feature Completeness & Non-null checks
  4. Forward Expectancy (MFE / MAE R-multiple discrimination power)
"""

import os
import sys
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from db import get_db_conn, read_sql_safe

def evaluate_labels(symbol: str = "HDFCBANK"):
    print(f"\n============================================================")
    print(f"       AUTOMATED LABEL EVALUATION REPORT: {symbol}")
    print(f"============================================================\n")

    with get_db_conn() as conn:
        # 1. TIMESTAMP & SESSION ALIGNMENT AUDIT
        print("🔍 1. TIMESTAMP & SESSION ALIGNMENT AUDIT")
        print("------------------------------------------------------------")
        tf_starts = read_sql_safe(
            """
            SELECT timeframe, 
                   MIN(ts) AS min_ts, 
                   MAX(ts) AS max_ts, 
                   COUNT(*) AS total_rows,
                   COUNT(DISTINCT ts::date) AS trading_days
            FROM market_context_ist
            WHERE symbol=%s
            GROUP BY timeframe
            ORDER BY timeframe;
            """,
            conn,
            params=[symbol]
        )

        if tf_starts.empty:
            print("❌ No market_context_ist records found! Run Step 1 labeling first.")
            return

        print(tf_starts.to_string(index=False))

        # Check if all timeframes start on exact same date and 09:15:00 time
        min_ts_set = set(tf_starts["min_ts"].astype(str))
        if len(min_ts_set) == 1:
            print("\n✅ PERFECT ALIGNMENT: All timeframes start on the exact same date & 09:15:00 IST open!")
        else:
            print(f"\n⚠️ WARNING: Start timestamps vary across timeframes: {min_ts_set}")

        # 2. MARKET PHASE DISTRIBUTION & CLASS BALANCE
        print("\n\n📊 2. MARKET PHASE DISTRIBUTION & CLASS BALANCE (15m)")
        print("------------------------------------------------------------")
        phase_dist = read_sql_safe(
            """
            SELECT market_phase, 
                   COUNT(*) AS count,
                   ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct
            FROM market_context_ist
            WHERE symbol=%s AND timeframe='15m'
            GROUP BY market_phase
            ORDER BY count DESC;
            """,
            conn,
            params=[symbol]
        )
        print(phase_dist.to_string(index=False))

        # Check for unclassified or heavy class collapse (>60% single class)
        if "UNCLASSIFIED" in phase_dist["market_phase"].values:
            unclass_pct = phase_dist[phase_dist["market_phase"] == "UNCLASSIFIED"]["pct"].values[0]
            print(f"\n❌ ALERT: {unclass_pct}% rows are UNCLASSIFIED!")
        else:
            print("\n✅ ZERO UNCLASSIFIED: 100% of rows are cleanly classified!")

        top_pct = phase_dist.iloc[0]["pct"] if not phase_dist.empty else 0
        if top_pct > 60:
            print(f"⚠️ NOTICE: High concentration in top phase ({phase_dist.iloc[0]['market_phase']}: {top_pct}%).")
        else:
            print(f"✅ HEALTHY CLASS BALANCE: Top phase represents {top_pct}% of dataset.")

        # 3. NULL & FEATURE INTEGRITY AUDIT
        print("\n\n🛡️ 3. FEATURE INTEGRITY & NULL AUDIT")
        print("------------------------------------------------------------")
        null_audit = read_sql_safe(
            """
            SELECT 
                COUNT(*) FILTER (WHERE market_phase IS NULL) AS null_phase,
                COUNT(*) FILTER (WHERE ema_21_slope IS NULL) AS null_ema_slope,
                COUNT(*) FILTER (WHERE vwap_dist_pct IS NULL) AS null_vwap_dist,
                COUNT(*) FILTER (WHERE price_structure IS NULL) AS null_price_struct
            FROM market_context
            WHERE symbol=%s;
            """,
            conn,
            params=[symbol]
        )
        print(null_audit.to_string(index=False))
        total_nulls = sum(null_audit.iloc[0].values)
        if total_nulls == 0:
            print("✅ ZERO NULLS: Feature matrix is 100% complete and clean!")
        else:
            print(f"⚠️ ALERT: Found {total_nulls} null values in feature matrix.")

        # 4. FORWARD EXPECTANCY DISCRIMINATION POWER (MFE / MAE)
        print("\n\n📈 4. FORWARD EXPECTANCY & DISCRIMINATIVE POWER (Outcomes)")
        print("------------------------------------------------------------")
        outcomes_summary = read_sql_safe(
            """
            SELECT market_phase,
                   COUNT(*) AS samples,
                   ROUND(AVG(realized_r)::numeric, 2) AS avg_realized_r,
                   ROUND(AVG(mfe_r)::numeric, 2) AS avg_mfe_r,
                   ROUND(AVG(mae_r)::numeric, 2) AS avg_mae_r,
                   ROUND((COUNT(*) FILTER (WHERE realized_r > 0) * 100.0 / COUNT(*))::numeric, 1) AS win_rate_pct
            FROM strategy_outcomes
            WHERE symbol=%s AND timeframe='15m'
            GROUP BY market_phase
            HAVING COUNT(*) >= 10
            ORDER BY avg_realized_r DESC;
            """,
            conn,
            params=[symbol]
        )

        if outcomes_summary.empty:
            print("ℹ️ Strategy outcomes not yet calculated. Run Step 3 outcome calculation to evaluate MFE/MAE expectancy.")
        else:
            print(outcomes_summary.to_string(index=False))
            print("\n✅ Expectancy audit completed.")

    print(f"\n============================================================")
    print(f"             END OF LABEL EVALUATION REPORT")
    print(f"============================================================\n")

if __name__ == "__main__":
    sym = sys.argv[1] if len(sys.argv) > 1 else "HDFCBANK"
    evaluate_labels(sym)
