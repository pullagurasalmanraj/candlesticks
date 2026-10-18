BEGIN;

-- Additive and rerunnable. Existing outcomes are not backfilled or recalibrated.
-- Apply 20260919_market_story_v1.sql first if market_context is not yet migrated.
ALTER TABLE strategy_outcomes
    ADD COLUMN IF NOT EXISTS phase_reason text,
    ADD COLUMN IF NOT EXISTS story_regime text,
    ADD COLUMN IF NOT EXISTS bar_event text,
    ADD COLUMN IF NOT EXISTS regime_rule_score double precision,
    ADD COLUMN IF NOT EXISTS event_rule_score double precision,
    ADD COLUMN IF NOT EXISTS regime_age_bars integer,
    ADD COLUMN IF NOT EXISTS candidate_regime text,
    ADD COLUMN IF NOT EXISTS candidate_age_bars integer,
    ADD COLUMN IF NOT EXISTS candidate_rule_score double precision,
    ADD COLUMN IF NOT EXISTS regime_reason_code text,
    ADD COLUMN IF NOT EXISTS event_reason_code text,
    ADD COLUMN IF NOT EXISTS story_version integer,
    ADD COLUMN IF NOT EXISTS reason_details jsonb,
    ADD COLUMN IF NOT EXISTS directional_edge double precision,
    ADD COLUMN IF NOT EXISTS bull_score double precision,
    ADD COLUMN IF NOT EXISTS bear_score double precision,
    ADD COLUMN IF NOT EXISTS trade_direction text,
    ADD COLUMN IF NOT EXISTS setup_key text,
    ADD COLUMN IF NOT EXISTS eligibility_reason text,
    ADD COLUMN IF NOT EXISTS trade_mfe double precision,
    ADD COLUMN IF NOT EXISTS trade_mae double precision,
    ADD COLUMN IF NOT EXISTS trade_mfe_r double precision,
    ADD COLUMN IF NOT EXISTS trade_mae_r double precision,
    ADD COLUMN IF NOT EXISTS horizon_mfe double precision,
    ADD COLUMN IF NOT EXISTS horizon_mae double precision,
    ADD COLUMN IF NOT EXISTS horizon_mfe_r double precision,
    ADD COLUMN IF NOT EXISTS horizon_mae_r double precision,
    ADD COLUMN IF NOT EXISTS session_mfe double precision,
    ADD COLUMN IF NOT EXISTS session_mae double precision,
    ADD COLUMN IF NOT EXISTS session_mfe_r double precision,
    ADD COLUMN IF NOT EXISTS session_mae_r double precision;

COMMENT ON COLUMN strategy_outcomes.mfe IS
    'Legacy full-session favorable excursion, preserved for calibration/ML compatibility. See trade_mfe and horizon_mfe.';
COMMENT ON COLUMN strategy_outcomes.mae IS
    'Legacy full-session adverse excursion (non-positive). See trade_mae and horizon_mae.';
COMMENT ON COLUMN strategy_outcomes.mfe_r IS
    'Legacy session_mfe divided by initial risk R, preserved for existing consumers.';
COMMENT ON COLUMN strategy_outcomes.mae_r IS
    'Legacy session_mae divided by initial risk R, preserved for existing consumers.';
COMMENT ON COLUMN strategy_outcomes.trade_mfe IS
    'Entry-to-exit-bar favorable OHLC excursion. Intrabar order within the exit bar is unknown.';
COMMENT ON COLUMN strategy_outcomes.trade_mae IS
    'Entry-to-exit-bar adverse OHLC excursion (non-positive); excludes all later bars.';
COMMENT ON COLUMN strategy_outcomes.horizon_mfe IS
    'Favorable excursion through configured lookahead, capped at session close, independent of early trade exit.';
COMMENT ON COLUMN strategy_outcomes.session_mfe IS
    'Favorable excursion from entry through the final available bar of the same IST session.';

COMMIT;
