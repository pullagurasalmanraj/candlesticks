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
labels, `PHASE_MODEL` values, timestamp conversions, routes and live execution
are unchanged. Calibration now reads horizon excursions as documented below;
no recalibration is performed automatically.

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

Existing ML consumers still read legacy excursion columns and phase features.
Those semantics are preserved. Calibration uses explicit horizon fields only;
the selected research population is intentionally different. Live/ML direction resolution is outside this change;
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

## Safety waterfall audit (diagnostics only)

Add `"diagnostic_mode": true` to the **same request** used for the research run,
including the same symbol, timeframe, date range and parameter overrides:

```json
{
  "symbol": "ITC",
  "exchange": "NSE",
  "timeframe": "5m",
  "diagnostic_mode": true
}
```

This is a read-only simulation: it does not delete, insert, or update any database
rows. It uses the same story policy, parameters, safety gates, order and simulator.
The response has `status: DIAGNOSTIC`, `rows_written: 0`, and `outcomes_generated`
equal to the simulated final trade count. Even zero-trade diagnostic runs return
HTTP 200 with the audit. Normal requests retain their existing write behavior
and HTTP 400 `NO_OUTCOMES` contract. No additional schema migration is required.

`audit_rows` contains **every story-eligible bar**, including rejected setups.
Each row has the current-bar story fields, setup key, intended direction, all
requested safety inputs and pass flags, `final_eligible`, and the actual
`final_skip_reason`. Accepted rows have a null skip reason. `ts` is an ISO UTC
timestamp; stored timestamps and session handling have not changed.

Two views of safety checks are deliberately separate:

- `safety_pass_fail_counts` evaluates each named gate independently for every
  story-eligible bar, even when an earlier gate stopped execution. This exposes
  overlapping failures. Counts are divided into `passed`, `failed`,
  `not_applicable`, and `unavailable`, summing to `story_eligible_bars` per gate.
- `safety_waterfall_counts` records actual visits in the unchanged short-circuit
  loop. Each gate reports those same categories, `reached`, and `not_reached`.
  Entry/session/data prerequisites can stop execution before any named gate.
  The per-row `gates_reached` list records the actual visit order; prerequisite
  and later validation failures remain visible in `final_skip_reason`.

The named order is macro, price structure, exhaustion, signal direction, cost,
EOD, then minimum rules. `independent_failed_gates` on each row shows overlapping
failures; it never controls execution. A bypassed gate (such as signal confirmation
on the opening gap bar) has its `*_applicable` flag false and its `*_pass` flag
true, but is counted as `not_applicable`, not as an evaluated pass. Unavailable
data produces null pass values and null costs rather than zeros or assumed passes.

`cost_r` in the audit is the **gate preview**:

```text
raw next-bar open * TOTAL_COST_PCT / (SL multiple * signal-bar ATR)
```

It uses the actual effective phase parameters, including calibrated parameters
when permitted. `TOTAL_COST_PCT` here is the frozen legacy `0.00150` gate proxy,
not the componentized fees now stored as `cost_r` on successful
`strategy_outcomes` rows. The audit includes `entry_price_raw`,
`risk_points`, `cost_gate_threshold` and `cost_r_unavailable_reason` to make that
distinction explicit. No same-session next entry, invalid ATR/risk, or nonfinite
costs are not silently included as zero-cost observations.

Summary fields:

- `story_eligible_bars` and `final_eligible_trades`.
- `cost_r_statistics`: count, unavailable count, min/max/mean, and p10/p25/p50/p75/p90.
- `cost_r_statistics_by_setup_key`: the same metrics for each setup, including
  those rejected before cost was reached. Quantiles use all finite available
  gate-preview costs, with NumPy's default linear interpolation.
- `safety_rejection_counts_by_setup_key` and
  `safety_rejection_counts_by_direction`: actual first-stop reasons.
- `story_eligible_counts_by_setup_key` and `story_eligible_counts_by_direction`:
  group population sizes for interpreting those counts.
- `safety_rejection_pct_of_story_eligible`,
  `cost_gate_rejection_pct_of_story_eligible`, and
  `final_eligible_pct_of_story_eligible`: percentages on the full story-eligible
  population. Each independent/waterfall gate also reports its own failure
  percentage on that same denominator.

For 71 first-stop cost rejections among 105 story-eligible bars, the cost rejection
percentage is `67.619048`, and
`cost_gate_rejection_fraction_of_story_eligible` is `71 / 105` (about `0.67619`).
The legacy `pct_skipped_by_cost` still uses total joined input rows for backward
compatibility. Empty populations produce null percentages and quantiles.

For diagnostics, reconcile using `outcomes_generated`, not `rows_written`:

```text
input_rows = outcomes_generated + total_skipped
story_eligible_bars = final_eligible_trades + sum(skipped_by_safety)
```

Summaries are also returned during normal outcome generation, but detailed
`audit_rows` are retained/returned only when diagnostic mode is enabled. Each
story-eligible row has exactly one final disposition. Independent failures can
overlap, so their sum must not be interpreted as the number of rejected setups.
Overlapping failures alone do not establish a gate's profitability or justify
removing it; no rejected setup is simulated as a hypothetical executed trade.

`test_safety_diagnostics.py` includes a synthetic 825-input/105-story-eligible
case matching the 47 bull, 44 bear, 14 gap counts and the 71 cost, 17 structure,
13 signal, 2 macro, 1 exhaustion rejections. It separately verifies cost overlap,
percentiles and grouping, read-only behavior, early prerequisite failures,
unknown data, and agreement between normal and diagnostic simulation.

## Research date windows

Outcome generation, diagnostic mode and phase calibration use the same window
parser. Date-only `YYYY-MM-DD` values describe **IST calendar days**, including
the entire requested end date. All three outcome/rule reads, outcome replacement
cleanup, and both calibration reads use half-open UTC parameters:

```sql
ts >= from_inclusive AND ts < to_exclusive
```

For `from_date: 2025-11-20` and `to_date: 2025-12-10`, the bounds are:

```text
IST: 2025-11-20 00:00:00 inclusive -> 2025-12-11 00:00:00 exclusive
UTC: 2025-11-19 18:30:00 inclusive -> 2025-12-10 18:30:00 exclusive
```

The Dec 10 trading session is included. A row at the following IST midnight is
excluded from both reads and cleanup. The same date for both fields is a valid
one-day window, including leap days and year boundaries.

Explicit ISO timestamps retain their exact instant; their end is also exclusive,
with no extra day added. Supply `Z` or an explicit offset such as `+05:30` to make
timestamp intent clear. Timezone-naive timestamps retain the previous UTC
interpretation. Timestamp precision must fit PostgreSQL's microsecond resolution.
Invalid or reversed/empty windows return HTTP 400 before database access.

An omitted start still means all available history (default Jan 1, 2000 IST).
An omitted end is the current UTC instant, not the end of the current day. The
response's `date_window` reports `calendar_timezone`, `from_inclusive` and
`to_exclusive` so the exact selected range is visible during diagnostics.

`phase_params.calibrated_to` and the existing calibration overlap guard retain
their **inclusive** metadata convention for compatibility with historical rows.
New calibrations store `to_exclusive - 1 microsecond` in that column and return
the exact half-open bounds separately in `date_window`. Thus a calibration ending
at Dec 11 IST midnight excludes that instant, and evaluation starting exactly
there is safely out-of-sample. A legacy inclusive calibration timestamp equal to
the evaluation start still triggers the unchanged overlap protection. No schema
migration, threshold changes or automatic recalibration are needed for this fix.

`test_strategy_date_windows.py` covers complete end-day inclusion, exact midnight
boundaries, matching read/delete parameters, date-only and explicit timestamps,
single-day/leap-day windows, invalid requests, calibration metadata, and adjacent
out-of-sample windows. Database operations in these tests are mocked.

## Horizon-only calibration

`calibrate_phase_params()` reads `horizon_mfe`, `horizon_mae`, `horizon_mfe_r`, and
`horizon_mae_r` exclusively. Counts, sample filters, percentile inputs and stored
descriptive statistics all refer to these configured-horizon excursions. There
is no fallback to legacy/session fields. Old rows with null horizon fields are
excluded; regenerate clean outcomes before explicitly calling calibration.

- `trade_*` describes actual trade life through the exit candle.
- `horizon_*` supplies TP/SL calibration evidence within the configured lookahead.
- `session_*` and the legacy excursion columns remain broader research/ML data.

TP/SL parameters remain ATR multiples, derived from raw horizon excursions divided
by ATR. Descriptive `phase_params` R-statistic columns (`avg_mfe_r`, `avg_mae_r`,
`p25_mfe_r`, etc.) summarize the source `horizon_*_r` observations using their
original initial risk, rather than mixing session metrics or the newly proposed
stop distance into those statistics. Constraints, percentile defaults and the
lookahead calculation are unchanged. The response reports `excursion_source:
"horizon"`. No parameter values are changed until calibration is explicitly run.

## Response-only counterfactual mode

Add `"counterfactual_mode": true` to the existing outcome-generation request.
Use a bounded research window for response-sized runs. All date-range handling
is unchanged. No additional schema migration or research-table creation is needed.

```json
{
  "symbol": "ITC",
  "timeframe": "5m",
  "counterfactual_mode": true
}
```

The endpoint first runs the existing production waterfall without changing any
threshold or gate. After all production decisions are final, a separate research
pass simulates every story-eligible setup, including those rejected by any safety
gate. Both paths use the existing next-bar open, effective phase TP/SL/lookahead,
session boundary cap, slippage, transaction costs, SHORT-aware exit simulator,
SL-first same-bar handling, and three excursion helpers. Research simulation
cannot influence the already finalized eligibility decision.

Counterfactual requests never delete, insert or update database rows, including
the otherwise production-eligible subset. They never append rejected setups to
the production writer's rows. No counterfactual dataset can enter normal SQL
statistics or ML training through this endpoint. No calibration is triggered.
Normal requests and standalone `diagnostic_mode` keep their previous behavior.
Both flags may be combined to return the unchanged `audit_rows` alongside the
separate research results.

Responses include:

- `status: COUNTERFACTUAL`, `counterfactual_mode: true`, and
  `production_rules_unchanged: true`.
- `rows_written: 0`. Existing `outcomes_generated` / `eligible_trades` still count
  the production-eligible population, not the hypothetical executed population.
- `counterfactual_outcomes_generated`: successfully simulated research setups.
- `counterfactual_rows`: one row for every story-eligible setup, including context,
  independent safety flags/applicability, failed gates, actual production
  eligibility/first skip reason, entry/risk/cost data, exit, gross/net R, and all
  three excursion windows.
- `counterfactual_summary`: production eligible/rejected counts, simulated and
  unavailable counts, overall statistics, fixed cost buckets, independent gate
  comparisons, and statistics by setup key, direction and production eligibility.

Missing phase config, invalid ATR/R, absent same-session next entry, or unusable
future prices make simulation impossible. Such a setup still has a response row
with `simulation_status: UNAVAILABLE`, a `simulation_skip_reason`, and null outcome
metrics. It is counted in `total_story_eligible` and the relevant group population,
but never treated as a zero-return trade or included in outcome percentages.

`cost_r` on a counterfactual row aliases `fee_cost_r`: itemized statutory/broker
fees on actual executed turnover divided by initial R. It is exactly the cost
deducted from `realized_r_gross` to obtain `realized_r_net`. `gate_cost_r` retains
the legacy raw-entry preview used by the unchanged cost gate. `cost_r_gate`
records the active request threshold. The two models can differ substantially;
the production gate intentionally continues using the old proxy during research.

Research cost buckets use actual `cost_r`: `<=0.70`, `(0.70,1.00]`, `(1.00,1.25]`,
and `>1.25`. These are reporting bins, not production threshold changes. A cost
gate threshold of `1.0` still rejects costs above `1.0R`; it does not disable the gate.
`fee_cost_r_buckets` and `total_friction_r_buckets` additionally report each
measure separately in these same bins; `cost_buckets` aliases the fee buckets.

Every outcome statistics group reports:

- `N`: successfully simulated observations; `story_eligible_N`: all members;
  `unavailable_N`: members without a valid simulated outcome.
- TP/SL/time-exit percentages using `N` as denominator.
- Mean and median gross/net R.
- Trade-life MFE-R and MAE-R p25/p50/p75.

Gate comparisons have mutually exclusive `pass`, `fail`, `not_applicable`, and
`unavailable` cohorts, preserving opening-gap and other bypass semantics. Each
cohort has the same outcome statistics, so an inactive gate is not silently
counted as a successfully evaluated filter. Empty groups return null percentages
and metrics. Research results measure hypothetical outcomes; they do not loosen
production eligibility or authorize execution.

`test_horizon_calibration.py` verifies horizon-only SQL/statistics, resistance to
large changes in legacy/session excursions, and no legacy fallback.
`test_counterfactual_research.py` covers all safety rejections, parity with real
production outcomes, independent eligibility, SHORT and same-bar semantics,
session boundaries, unavailable data, exact bucket edges/group statistics, and
the absence of research database writes.

## Componentized equity-intraday fees (V1)

The outcome endpoint returns `cost_model_version: EQUITY_INTRADAY_COMPONENT_V1`
and `cost_model` containing every applied rate, sizing input, GST base and
assumption. The shared implementation is `routes/strategy_costs.py`; both
production outcomes and counterfactual simulations use it after the unchanged
production eligibility decision. Existing `diagnostic_mode` still simulates
only accepted trades. Their `audit_rows` now include actual fee breakdowns;
rejected diagnostic rows have null fee fields and `fee_breakdown_status:
NOT_SIMULATED`. Use counterfactual mode to measure rejected trades' exit fees.

The fixed default schedule is NSE cash equity intraday, using the published
March 2026 exchange schedule and statutory cash-intraday rates:

| Component | Rate (percentage of executed turnover) | Leg |
| --- | --- | --- |
| Brokerage, configurable | 0.03% | Buy and sell separately |
| STT | 0.025% | Sell only |
| NSE transaction | 0.0030699% | Buy and sell separately |
| NSE IPFT | 0.0000001% | Buy and sell separately |
| SEBI turnover | 0.0001% (Rs10/crore) | Buy and sell separately |
| Stamp duty | 0.003% | Buy only |
| GST | 18% of brokerage + NSE transaction/IPFT + SEBI charges | Taxable fees only |

NSE transaction + IPFT total 0.00307% per side (Rs307/crore). The tiny IPFT
component is explicit and included once in `exchange_cost_pts`. GST excludes
STT, stamp duty and slippage. Sources: [NSE levies](https://www.nseindia.com/static/invest/first-time-investor-sebi-turnover-fees-stt-other-levies),
[NSE circular effective March 1, 2026](https://nsearchives.nseindia.com/content/circulars/FA73061.pdf),
and [broker's published GST base and fees](https://zerodha.com/charges).

This is a fixed research schedule, not automatic historical tariff selection.
For an older or different broker schedule, override individual rates explicitly.
All API rates are **fractions**, e.g. `0.0003` means `0.03%`, and `0.18` means
18% GST. These are unrounded per-share estimates, not contract-note tax rounding
or daily aggregation. Special dealer/auto-square-off fees are not assumed.

Example request (add your normal symbol, timeframe and bounded research dates):

```json
{
  "symbol": "ITC",
  "timeframe": "5m",
  "counterfactual_mode": true,
  "cost_model": {
    "brokerage_rate": 0.0003,
    "brokerage_cap_per_order": 20,
    "quantity": 1000
  }
}
```

All `cost_model` options are optional. Defaults never assume a brokerage cap.
If an explicit cap is provided, apply `min(rate * leg_turnover, cap)` to each
of the two orders only when size is known. The same quantity is bought and sold.
`quantity` fixes shares per setup. Alternatively, `order_notional` is the executed
**entry** order notional; quantity is derived as `order_notional / entry_price`
for that setup (a fractional sizing estimate, without share rounding). These
two sizing options are mutually exclusive; the other leg's turnover uses that
same derived quantity and its own execution price.

Without either sizing input, brokerage stays percentage based even if a cap was
specified. The row reports `brokerage_mode: PERCENTAGE_FALLBACK_NO_SIZE`; it
does not assume one share for cap purposes or silently apply Rs20. Known-size
results report `CAPPED_PER_ORDER` and separate buy/sell `brokerage_cap_applied_*`
flags, including when one leg reaches the cap but the other does not.

The supported configuration keys are `brokerage_rate`, `brokerage_cap_per_order`,
`nse_transaction_rate`, `nse_ipft_rate`, `stt_sell_rate`, `sebi_turnover_rate`,
`stamp_duty_buy_rate`, `gst_rate`, `quantity`, and `order_notional`. Invalid,
nonfinite or unknown options return HTTP 400 before database access.

Counterfactual rows and simulated diagnostic audit rows expose costs in points
(rupees per share), including buy/sell brokerage, STT sell, NSE transaction/IPFT
buy/sell, SEBI buy/sell, stamp buy and GST taxable base. Requested totals are:

```text
brokerage_cost_pts, stt_cost_pts, exchange_cost_pts, sebi_cost_pts,
stamp_cost_pts, gst_cost_pts, total_fee_cost_pts,
entry_slippage_pts, exit_slippage_pts, total_friction_pts,
fee_cost_r, slippage_r, total_friction_r
```

Accounting identities, asserted and tested:

```text
fee_cost_r       = total_fee_cost_pts / initial R
slippage_r       = (entry_slippage_pts + exit_slippage_pts) / initial R
total_friction_r = fee_cost_r + slippage_r
realized_r_net   = realized_r_gross - fee_cost_r
```

`realized_r_gross` preserves the existing executed-price simulation: adverse
entry tick and TP-exit tick, exact SL fill, and time-exit close. The slippage
diagnostics report these existing adjustments; they do not rerun a hypothetical
no-slippage exit path. SL/TIME have zero extra exit slippage under the current
simulator. **Do not subtract `total_friction_r` from gross:** its slippage is
already reflected in execution prices. Fees are charged on those execution
prices, and slippage is never an extra percentage fee or GST taxable component.

Every counterfactual summary group additionally reports mean and p10/p25/p50/
p75/p90 for fee R, slippage R and total friction R. Separate fee/friction buckets
carry the same trade outcome statistics as existing cost buckets.

The production cost gate remains `raw_entry * 0.00150 / (SL * ATR)` compared with
the existing request/default threshold; `COST_R_MAX_GATE` remains `0.70`.
Responses identify this as `cost_gate_model_version: LEGACY_FIXED_0_00150` and
`cost_gate_estimate_pct: 0.00150`. Neither fee configuration nor realized exit
turnover feeds the gate. The compatibility `TOTAL_COST_PCT` alias and explicit
calibration calculations also retain the legacy proxy pending research review.
No story, TP/SL, lookahead, safety predicates, date logic or phase parameters are
changed, and no calibration is triggered.

No new database migration is required. Normal generation stores the corrected
fee-only `cost_r` and net `realized_r` in existing columns. Existing historical
rows are not rewritten automatically; the response identifies the applied V1
configuration, so keep it with research exports and compare regenerated windows
consistently. Counterfactual/diagnostic requests remain response-only and cannot
write research rows into normal outcomes or ML datasets.
