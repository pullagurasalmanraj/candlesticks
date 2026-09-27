BEGIN;

ALTER TABLE market_context
    ADD COLUMN IF NOT EXISTS story_regime text,
    ADD COLUMN IF NOT EXISTS bar_event text,
    ADD COLUMN IF NOT EXISTS regime_rule_score real,
    ADD COLUMN IF NOT EXISTS event_rule_score real,
    ADD COLUMN IF NOT EXISTS regime_age_bars integer DEFAULT 0,
    ADD COLUMN IF NOT EXISTS candidate_regime text,
    ADD COLUMN IF NOT EXISTS candidate_age_bars integer DEFAULT 0,
    ADD COLUMN IF NOT EXISTS candidate_rule_score real,
    ADD COLUMN IF NOT EXISTS regime_reason_code text,
    ADD COLUMN IF NOT EXISTS event_reason_code text,
    ADD COLUMN IF NOT EXISTS reason_details jsonb DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS story_version integer DEFAULT 1;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'market_context_regime_rule_score_check'
    ) THEN
        ALTER TABLE market_context
            ADD CONSTRAINT market_context_regime_rule_score_check
            CHECK (regime_rule_score IS NULL OR regime_rule_score BETWEEN 0 AND 1);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'market_context_event_rule_score_check'
    ) THEN
        ALTER TABLE market_context
            ADD CONSTRAINT market_context_event_rule_score_check
            CHECK (event_rule_score IS NULL OR event_rule_score BETWEEN 0 AND 1);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'market_context_candidate_rule_score_check'
    ) THEN
        ALTER TABLE market_context
            ADD CONSTRAINT market_context_candidate_rule_score_check
            CHECK (candidate_rule_score IS NULL OR candidate_rule_score BETWEEN 0 AND 1);
    END IF;
END $$;

CREATE OR REPLACE VIEW market_context_ist AS
SELECT symbol, exchange, timeframe,
       ts AT TIME ZONE 'Asia/Kolkata' AS ts,
       vwap_dist_pct, day_high_dist, day_low_dist,
       orb_dist_pct, gap_pct, minute_of_day,
       volume_expansion, atr_expanding, range_efficiency,
       vwap_acceptance, momentum_decay, candle_overlap,
       market_phase, context_label,
       created_at AT TIME ZONE 'Asia/Kolkata' AS created_at,
       vix, vix_change, vix_regime, ema_21_slope,
       gap_atr, gap_dir, gap_regime, ml_label, tf_role,
       trend_exhaustion, obv_slope, macd_expanding,
       price_structure, session_type, macro_regime, vol_ratio,
       vwap_dist_atr, impulse_dir, phase_reason,
       story_regime, bar_event, regime_rule_score,
       event_rule_score, regime_age_bars, candidate_regime,
       candidate_age_bars, candidate_rule_score,
       regime_reason_code, event_reason_code, reason_details,
       story_version
FROM market_context;

COMMIT;
