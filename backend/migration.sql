-- ================================================================
--  DB MIGRATION — strategy.py + ml.py full upgrade
--  Run this ONCE in your PostgreSQL DB before calling any endpoint.
--  All statements are idempotent (safe to re-run).
-- ================================================================

-- ── 1. strategy_outcomes — add cost columns ────────────────────
ALTER TABLE strategy_outcomes
    ADD COLUMN IF NOT EXISTS realized_r_gross FLOAT,
    ADD COLUMN IF NOT EXISTS cost_r           FLOAT;

-- ── 2. market_context — add new state columns ──────────────────
ALTER TABLE market_context
    ADD COLUMN IF NOT EXISTS trend_exhaustion  INT     DEFAULT 0,
    ADD COLUMN IF NOT EXISTS obv_slope         FLOAT   DEFAULT 0,
    ADD COLUMN IF NOT EXISTS macd_expanding    INT     DEFAULT 0,
    ADD COLUMN IF NOT EXISTS vol_ratio         FLOAT   DEFAULT 1.0,
    ADD COLUMN IF NOT EXISTS price_structure   TEXT    DEFAULT 'NEUTRAL',
    ADD COLUMN IF NOT EXISTS session_type      TEXT    DEFAULT 'NORMAL_DAY',
    ADD COLUMN IF NOT EXISTS macro_regime      TEXT    DEFAULT 'NEUTRAL_MACRO';

-- ── 3. phase_params — new table (calibrate-phase-params) ───────
CREATE TABLE IF NOT EXISTS phase_params (
    id                    SERIAL PRIMARY KEY,
    symbol                TEXT        NOT NULL,
    exchange              TEXT        NOT NULL DEFAULT 'NSE',
    timeframe             TEXT        NOT NULL,
    market_phase          TEXT        NOT NULL,
    optimal_tp            FLOAT       NOT NULL,
    optimal_sl            FLOAT       NOT NULL,
    optimal_lookahead_min INT         NOT NULL,
    samples               INT         NOT NULL,
    win_rate              FLOAT,
    avg_mfe_r             FLOAT,
    avg_mae_r             FLOAT,
    p25_mfe_r             FLOAT,
    p50_mfe_r             FLOAT,
    p75_mfe_r             FLOAT,
    p25_mae_r             FLOAT,
    p75_exit_after        INT,
    computed_at           TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (symbol, exchange, timeframe, market_phase)
);

-- ── 4. ml_model_runs — new table (train-pipeline) ──────────────
CREATE TABLE IF NOT EXISTS ml_model_runs (
    id           SERIAL PRIMARY KEY,
    symbol       TEXT        NOT NULL,
    timeframe    TEXT        NOT NULL,
    model_type   TEXT,
    trained_at   TIMESTAMPTZ DEFAULT NOW(),
    train_from   TIMESTAMPTZ,
    train_to     TIMESTAMPTZ,
    test_from    TIMESTAMPTZ,
    test_to      TIMESTAMPTZ,
    rows_used    INT,
    model_path   TEXT
);

-- ── 5. paper_trade_runs — new table (paper-trade/run) ──────────
CREATE TABLE IF NOT EXISTS paper_trade_runs (
    id               SERIAL PRIMARY KEY,
    model_run_id     INT REFERENCES ml_model_runs(id),
    symbol           TEXT,
    timeframe        TEXT,
    threshold        FLOAT,
    starting_capital FLOAT,
    final_capital    FLOAT,
    total_trades     INT,
    wins             INT,
    losses           INT,
    win_rate         FLOAT,
    expectancy       FLOAT,
    max_drawdown_pct FLOAT,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- ── 6. paper_trades — new table (individual trade rows) ────────
CREATE TABLE IF NOT EXISTS paper_trades (
    id                 SERIAL PRIMARY KEY,
    paper_trade_run_id INT REFERENCES paper_trade_runs(id),
    ts                 TIMESTAMPTZ,
    market_phase       TEXT,
    exec_class         TEXT,
    direction          TEXT,
    win_prob           FLOAT,
    threshold          FLOAT,
    realized_r         FLOAT,
    pnl                FLOAT,
    qty                INT,
    capital_after      FLOAT,
    result             TEXT,
    created_at         TIMESTAMPTZ DEFAULT NOW()
);

-- ── Verification query — run after migration ───────────────────
SELECT check_name, exists FROM (
    SELECT 'strategy_outcomes.realized_r_gross' AS check_name,
           COUNT(*) > 0 AS exists
    FROM information_schema.columns
    WHERE table_name='strategy_outcomes' AND column_name='realized_r_gross'
    UNION ALL
    SELECT 'strategy_outcomes.cost_r',
           COUNT(*) > 0
    FROM information_schema.columns
    WHERE table_name='strategy_outcomes' AND column_name='cost_r'
    UNION ALL
    SELECT 'market_context.trend_exhaustion',
           COUNT(*) > 0
    FROM information_schema.columns
    WHERE table_name='market_context' AND column_name='trend_exhaustion'
    UNION ALL
    SELECT 'market_context.obv_slope',
           COUNT(*) > 0
    FROM information_schema.columns
    WHERE table_name='market_context' AND column_name='obv_slope'
    UNION ALL
    SELECT 'market_context.macd_expanding',
           COUNT(*) > 0
    FROM information_schema.columns
    WHERE table_name='market_context' AND column_name='macd_expanding'
    UNION ALL
    SELECT 'market_context.vol_ratio',
           COUNT(*) > 0
    FROM information_schema.columns
    WHERE table_name='market_context' AND column_name='vol_ratio'
    UNION ALL
    SELECT 'market_context.price_structure',
           COUNT(*) > 0
    FROM information_schema.columns
    WHERE table_name='market_context' AND column_name='price_structure'
    UNION ALL
    SELECT 'market_context.session_type',
           COUNT(*) > 0
    FROM information_schema.columns
    WHERE table_name='market_context' AND column_name='session_type'
    UNION ALL
    SELECT 'market_context.macro_regime',
           COUNT(*) > 0
    FROM information_schema.columns
    WHERE table_name='market_context' AND column_name='macro_regime'
    UNION ALL
    SELECT 'TABLE phase_params',
           COUNT(*) > 0
    FROM information_schema.tables
    WHERE table_name='phase_params'
    UNION ALL
    SELECT 'TABLE ml_model_runs',
           COUNT(*) > 0
    FROM information_schema.tables
    WHERE table_name='ml_model_runs'
    UNION ALL
    SELECT 'TABLE paper_trade_runs',
           COUNT(*) > 0
    FROM information_schema.tables
    WHERE table_name='paper_trade_runs'
    UNION ALL
    SELECT 'TABLE paper_trades',
           COUNT(*) > 0
    FROM information_schema.tables
    WHERE table_name='paper_trades'
) t ORDER BY check_name;
-- All rows should show: exists = true
