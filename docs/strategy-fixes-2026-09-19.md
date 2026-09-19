# Strategy logic repairs

Date: 2026-09-19

This change repairs the market-state labels, outcome simulation, parameter
calibration, and ML execution contract used by `strategy.py`.

## Fixed behavior

### Market context and state machine

- Bear post-impulse bars now emit `BEAR_TREND_CONTINUATION` or
  `BEAR_TREND_DIGESTION`; they can no longer receive bull labels.
- Post-impulse state expires after a timeframe-aware number of bars instead of
  remaining latched indefinitely.
- EMA slope thresholds now use slope divided by ATR, so the same rules work
  across instruments with different price scales.
- Rolling gap thresholds use only previously observed session gaps. Removed
  backward filling that allowed later sessions to affect earlier labels.
- Gap-fill progress is measured from the session's opening price instead of
  each candle's open.
- Missing VIX stays unknown and maps to `UNKNOWN_VOL`; it is no longer replaced
  by zero and misclassified as high volatility. VIX is only forward-filled
  within its trading date.
- VIX values are coerced to a numeric series before calculating changes. An
  all-NULL VIX column can no longer crash market-context labelling with
  `NoneType - NoneType`.
- Warm-up is derived from the longest indicator/state window. Incomplete early
  rows are no longer persisted as valid labels.
- Gap-opening debug reasons retain the actual opening classification.
- Auction impulse phases now have explicit phase-model entries.
- `market_context` conflict updates now refresh every derived field, including
  gap, ORB, VIX, volatility, momentum, overlap, and day-range fields.

### Outcome simulation

- A signal can enter only at the next candle's open and only when that candle is
  in the same IST trading session. Last-candle signals no longer enter on the
  next day.
- Lookahead is capped at the current session end. Stored lookahead and exit
  speed use the capped horizon.
- The EOD guard reads the current phase configuration and is active again.
- The macro gate is applied after resolving dynamic directions, so `FOLLOW`,
  `FADE`, `MEAN`, and `BREAKOUT` trades cannot bypass it.
- Long and short exits use a conservative same-bar rule: if TP and SL are both
  touched, the stop wins.
- MFE and MAE are retained through the rest of the trading session. They are no
  longer censored by the old exit or lookahead, which lets calibration evaluate
  new barriers.
- Neutral/context-only phases do not pretend to produce directional outcomes.
- Re-running a date window replaces that window's outcomes, including deletion
  of stale rows that are no longer generated.

### Calibration

- TP/SL calibration now uses raw full-horizon excursions divided by ATR. The
  previous code treated old-stop R multiples as ATR multiples.
- Default TP uses MFE p40, which roughly corresponds to a 60% reach rate.
- Default SL uses absolute MAE p75, which roughly corresponds to 75% of samples
  staying inside the proposed adverse excursion. The earlier percentile
  descriptions had these probabilities reversed.
- Candidate win rate, friction, breakeven rate, and expectancy are recomputed
  for the proposed TP/SL instead of reusing results from the old parameters.
- Samples touching both candidate barriers are counted as losses because their
  intrabar order is unknown.
- Invalid sample counts, percentile values, timeframes, and reversed date
  ranges are rejected.
- A calibration run atomically replaces all phase parameters for its
  symbol/exchange/timeframe, removing stale phases from older windows.
- Parameters are ignored when their calibration window overlaps the requested
  evaluation window. The API reports this in
  `calibrated_params_ignored`/`params_overlap_warning`.
- Legacy parameter rows without a recorded calibration window are ignored until
  they are regenerated, because their out-of-sample safety cannot be checked.
- The phase-parameter loader rolls back a failed schema query before trying its
  compatibility query.

### Strategy/ML contract

- Gap and reversal execution mappings now agree with `PHASE_MODEL`, including
  `LARGE_GAP_UP`, `MODERATE_GAP_DOWN`, both gap-fade phases, and the auction
  impulse phases.
- Dynamic `EXPANSION` and `GAP_CONTINUATION` directions resolve from gap context
  and EMA slope instead of silently becoming long trades.
- Context-only phases such as `PULLBACK_FAIL`, `REJECTION`, `DISTRIBUTION`, and
  `GAP_TIMEOUT` map to `SKIP`.
- ML cost features use cost divided by stop risk. The old feature multiplied ATR
  by a percentage and had the wrong units.
- `outcome_timing` comes only from an earlier trade that had already exited at
  the signal timestamp. The model no longer sees the current or still-open
  trade's future completion speed.
- Phase-lag features now use the immediately preceding market bars in training,
  paper replay, and live prediction. Training previously shifted only between
  sparse outcome rows.
- Walk-forward test folds no longer overlap, and training rows whose exits reach
  into a test fold are purged.
- Per-phase thresholds are derived from out-of-fold predictions rather than the
  final model's in-sample predictions.
- Hierarchical timeframe alignment compares resolved long/short directions.
- Paper replay accepts only outcomes after the selected model's `train_to`, and
  applies stored net R directly to the actual account risk. This prevents
  in-sample replay and mixed stop-unit P&L.

## Data refresh procedure

Existing labels, outcomes, calibrated parameters, and trained model files were
created under the old logic and should not be mixed with the repaired data.
For each symbol and timeframe:

1. Run `POST /api/offline/label-market-context` to regenerate market context.
2. Choose a calibration window ending before the evaluation window.
3. Run `POST /api/offline/calc-strategy-outcomes` for the calibration window.
   Overlapping old calibration is automatically ignored, so defaults produce
   the bootstrap outcomes.
4. Run `POST /api/offline/calibrate-phase-params` with explicit `from_date` and
   `to_date` for that calibration window.
5. Run `POST /api/offline/calc-strategy-outcomes` for a strictly later
   out-of-sample window. The calibrated parameters are used there.
6. Retrain the ML model after all required outcome windows are regenerated.
7. Reserve outcomes later than the new model's `train_to` for paper replay.

No database migration is required by these repairs. Existing columns are reused.

## Regression coverage

`backend/tests/test_strategy_regressions.py` covers:

- full-horizon long and short excursions;
- conservative simultaneous TP/SL handling;
- bear post-impulse labels;
- strategy-to-ML direction mappings;
- dynamic direction and risk-normalized transaction cost;
- non-overlapping walk-forward folds and exit-time purging.
