# Story-aware strategy outcomes

## Previous flow and scope

`calc_strategy_outcomes()` joined `indicators` and `market_context` by symbol,
exchange, timeframe and timestamp. It used `market_phase` to select `PHASE_MODEL`
or cached calibrated parameters, including direction. After safety gates it
entered at the next bar's open, applied the existing slippage/cost model, and
called `_simulate_exit_vectorized()`. Its `excursion_n` extended to session close,
so legacy `mfe`, `mae`, `mfe_r`, and `mae_r` were full-session research metrics.
Writes replaced the requested evaluation window in one transaction, using
`chunk_execute` batching. Those conventions remain in place.

Changes are limited to `backend/routes/strategy.py`, reusable helpers in
`backend/routes/strategy_logic.py`, an additive migration, and tests. State-machine
labels, `PHASE_MODEL` values, calibration code, timestamp conversions, routes and
live execution are unchanged. No recalibration is performed.

## New research flow

1. Read the existing story columns from the same current-bar context row.
2. Resolve whether a trade exists, its direction, and an eligibility reason.
3. Apply the existing session, macro, structure, exhaustion, confirmation, cost
   and optional minimum-rule gates. Continuation structure checks use the actual
   resolved side; an opposite legacy phase cannot reverse the trade.
4. Use legacy phase parameters for TP, SL and lookahead only.
5. Keep next-bar entry and the existing conservative, SHORT-aware exit simulator.
6. Calculate three independent direction-aware excursion windows.
7. Batch-write accepted trades with story evidence and a stable setup key.

Trend regimes require `CONTINUATION`, `ACCEPTANCE`, `IMPULSE` or `EXPANSION`.
`TRANSITION`, `RANGE` and context-only events generate no trade rows.
Gap auction events retain the existing continuation/fade direction resolution;
CHOP and other non-gap events cannot bypass the trend policy through a gap regime.

Defaults are centralized in `STORY_TRADE_DEFAULTS`: regime score 0.60, event
score 0.50, signed directional edge 0.25 and regime age 2 bars. The resolver uses
the actual `_derive_market_story()` reason codes `REGIME_EVIDENCE_CONFIRMED` and
`REGIME_CANDIDATE_CONFIRMED`. A pending challenge is not confirmed. Any active
opposing trend candidate is rejected, even before it confirms; active range or
transition candidates also block a retained trend. No new state-machine reasons
or look-ahead confirmation rules were invented.

Optional per-request research settings:

```json
{
  "symbol": "ITC",
  "exchange": "NSE",
  "timeframe": "5m",
  "story_policy": {
    "min_regime_score": 0.60,
    "min_event_score": 0.50,
    "min_directional_edge": 0.25,
    "min_regime_age_bars": 2
  }
}
```

Overrides are validated and echoed in the response. Missing or malformed numeric
JSON evidence defaults to zero and cannot authorize a trade. JSON is parsed in
Python rather than casting untrusted JSON text to float in SQL. The current
schema's actual field is `reason_details jsonb`; `directional_edge`, `bull_score`
and `bear_score` are nested evidence, not separate input columns.

## Excursion definitions and compatibility

| Columns | Window |
| --- | --- |
| `trade_mfe`, `trade_mae`, and their `_r` columns | Entry bar through actual exit bar, inclusive |
| `horizon_mfe`, `horizon_mae`, and their `_r` columns | Entry through configured lookahead, capped at the final available bar of that IST session |
| `session_mfe`, `session_mae`, and their `_r` columns | Entry through the final available bar of that IST session |
| Legacy `mfe`, `mae`, `mfe_r`, `mae_r` | Continue to map to session metrics |

MFE is non-negative; MAE is non-positive. Each normalized metric uses the initial
slippage-adjusted entry-to-stop distance R. Invalid ATR, prices or R do not
produce a trade row. The exit simulator's five-value return contract is unchanged.

OHLC cannot reveal intrabar ordering: trade-life metrics include the complete
exit candle, but never later candles. They are not tick-accurate excursions before
the barrier touch. Same-candle TP/SL ties still resolve to SL first. A truncated
data window has only its available in-session bars; no missing future bars are
invented and no excursion extends into another IST date.

## Deployment and schema assumptions

The checked-in schema dump lacks the story columns, while
`20260919_market_story_v1.sql` and the labeling endpoint already add them to
`market_context`. The outcome endpoint now inspects actual table columns using
the current search path. Missing source/output columns return HTTP 409 with their
names **before replacing any existing outcomes**. There is no legacy-only fallback.

Apply the additive, rerunnable migration on the VM before using the new endpoint:

```bash
cd ~/candlesticks
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -d candleticks < backend/migrations/20261018_story_trade_outcomes.sql
```

Use the real database/user if the VM differs. Apply the existing market-story
migration first only if those source columns have not yet been installed.
Restart/redeploy the backend with the updated code. Relabel the relevant symbol
and timeframe if existing `market_context` rows do not contain current story data.
Then regenerate outcomes. Calibration and ML retraining are later, separate steps.

The migration adds only missing columns and metadata comments. It does not
backfill old rows, delete data, change TP/SL values or recalibrate parameters.
The existing `strategy_outcomes_ist` view keeps its original column contract;
query `strategy_outcomes` directly to inspect the new fields.

Regeneration continues the existing replacement behavior: rows in the requested
symbol/exchange/timeframe/date window are deleted and accepted rows inserted in
the same transaction. An entirely rejected run clears stale outcomes in that
window and returns HTTP 400 `NO_OUTCOMES` with diagnostics. Archive previous runs
before regeneration if historical comparisons are needed. Unrequested windows
are unchanged.

Existing calibration/ML consumers still read legacy excursion columns and phase
features. Those semantics are preserved, but the selected research population is
intentionally different. Live/ML direction resolution is outside this change;
consumers that derive execution direction from legacy phase must be aligned with
`trade_direction` before using these story-directed outcomes for execution.

## Diagnostics and reconciliation

Successful and zero-output responses include:

- `input_rows`: rows in the existing indicator/context inner join and request window.
  This is not the raw candle table count; missing join matches are outside this count.
- `story_eligible_bars`: passed the story resolver, before safety gates.
- `eligible_trades` / `rows_written`: passed all gates and generated outcomes.
- `eligibility_reason_counts`: all resolver decisions, including preliminary `VALID_*`.
- `skipped_by_eligibility`: primary story rejection counts only.
- `skipped_by_safety`: primary downstream rejection counts only.
- `total_skipped` and the applied `story_policy`.

Each joined row has exactly one final disposition:

```text
input_rows = rows_written + total_skipped
total_skipped = sum(skipped_by_eligibility) + sum(skipped_by_safety)
```

The shorter `skipped_transition`, `skipped_range` and
`skipped_context_only_event` fields are aliases; do not add them again when
reconciling. Existing cost/EOD/min-rule response fields are retained. Skipped
context remains in `market_context`, not in fabricated outcome trade rows.

## Validation

Run with the existing backend requirements installed:

```bash
python -m unittest discover -s backend/tests -p 'test_*.py' -v
```

`test_story_outcomes.py` covers bull/bear setups, context-only events, challengers,
confirmation, threshold boundaries, gap direction, malformed JSON, risk edge
cases, both-direction same-bar SL priority, separate excursion windows, next-bar
and session boundaries, legacy direction conflicts, unchanged safety gates,
calibration overlap, batched write tuple alignment, and zero-output diagnostics.
Route tests use mocked database reads/writes; no production database is changed.
