# Entry timing and TP/SL geometry research

`POST /api/offline/compare-entry-geometry` runs one fixed experiment for ITC and
TATASTEEL, NSE, 5m. It returns aggregate JSON, never signal/trade audit arrays.
The standalone runner is `backend/scripts/compare_entry_geometry.py`.

An empty JSON request uses all available historical data and a chronological
70% research / 30% holdout split. For a reproducible run, specify dates and fix
the split before inspecting holdout results:

```json
{
  "from_date": "2025-10-23",
  "to_date": "2026-09-18",
  "holdout_from_date": "2026-06-15"
}
```

These dates illustrate the request format, not a recommended training window.
In Postman choose **Body → raw → JSON**. Only `from_date`, `to_date`,
`holdout_from_date`, `cost_model`, `symbols`, `timeframe`, and `exchange` are
accepted. Use `symbols: ["ITC", "TATASTEEL"]`, not the singular `symbol` field
from the outcome-generation endpoint. Omit `diagnostic_mode`,
`counterfactual_mode`, story/safety overrides, and TP/SL settings here: the
research-only comparisons are predefined. Unsupported fields are listed by name
in validation errors.

Date-only bounds cover complete IST days. An omitted end means the current
instant, so the current session may be incomplete. Missing/incomplete sessions
are flagged. The default split uses the first `floor(0.70 * trading_days)` days
(at least one) for research and the remainder (at least one) for holdout. The
boundary uses the union of available dates across both symbols. No label can
cross it because it is an IST midnight and every exit is session-capped.

## Fixed variants

| Variant | Extra waiting bars | TP scale | SL scale |
| --- | ---: | ---: | ---: |
| baseline | 0 | 1.0 | 1.0 |
| delay_1 | 1 | 1.0 | 1.0 |
| delay_2 | 2 | 1.0 | 1.0 |
| tp_0_8x | 0 | 0.8 | 1.0 |
| tp_1_2x | 0 | 1.2 | 1.0 |
| sl_0_8x | 0 | 1.0 | 0.8 |
| sl_1_2x | 0 | 1.0 | 1.2 |

Scales are relative to frozen baseline phase parameters. There is no request
grid, ranking, automatic winner, writeback, or joint delay × geometry search.
Timing and geometry are separate comparisons; their interaction is not tested.

Baseline uses the existing next-bar entry, phase TP/SL and configured lookahead.
Eligible calibrated parameters are frozen once for both periods. Existing
protection against calibration overlapping the evaluation start is preserved:
overlapping calibrations are ignored, and PHASE_MODEL defaults are used. Unknown
calibration dates cannot establish out-of-sample parameters. Defaults' historical
fitting provenance is not available, and the report explicitly says so. This is
a frozen-configuration diagnostic, not proof of a previously unseen live strategy.
No calibration runs and no production parameter cache is updated.

## Causal cohort and execution

The existing story normalization, eligibility and gap-direction functions, with
unchanged default story thresholds, establish one cohort. Every variant uses
the same signal direction, setup key and **signal-bar ATR**. No future or delayed
story/ATR decides eligibility. Stored story labels are neither rerun nor relabeled.

All story-eligible signals are measured, including ones production safety gates
could reject. Production gates are untouched. Results are not production-filtered
P&L. SQL reads indicator OHLCV with a LEFT JOIN to stored story context: an
unlabeled bar can supply an entry/exit price but cannot create an eligible signal.

Entry is at observed bar `signal_index + 1 + delay`. Waiting one full bar enters
one bar after baseline, and waiting two enters two bars after baseline. The
schedule never searches for favorable prices and never enters the next session.
Missing five-minute intervals are flagged, not filled. Delays count observed
bars, so wall-clock waits can exceed 5/10 minutes when data has gaps.

Configured lookahead is unchanged and begins at each variant's actual entry.
Waiting shifts its horizon forward, subject to the same session cap; it does not
shorten it to an original signal-relative deadline. TP/SL offsets use the signal's
frozen ATR and the variant's execution entry. The shared simulator preserves
SHORT handling, conservative SL-first same-bar ties, entry and TP-exit slippage,
exact SL fills and time-exit closes. MFE/MAE include complete exit candles and do
not establish tick ordering before an intrabar barrier touch.

The same componentized fee model and optional `cost_model` configuration apply
to every variant. Fees use its own executed turnover. Gross R already reflects
execution slippage; net R subtracts fees once. Unfillable entries count as missed;
entered trades whose future outcomes cannot be measured count as unavailable,
never as zero-return trades.

## Overlap and interpreting summaries

Each symbol/period/variant reports both `raw_signals` and `non_overlapping`.
Raw results include overlapping trades. The non-overlapping approximation uses
chronological first-signal-wins, with one pending order/position per symbol.
Delayed orders reserve the slot while waiting. Later signals cannot replace an
earlier order using future profitability. A missing delayed entry reserves until
session close; a future unmeasurable outcome conservatively blocks the remainder
of that session. Slots release at exit-bar close, allowing signals on that close
to schedule a next-bar entry, with no same-bar re-entry assumption.

This is per symbol, not a shared-capital two-symbol portfolio. It does not model
cash constraints, liquidity impact or order rejection. `overlap_flags` reports
all trades in overlapping groups, maximum concurrent raw trades and signals
arriving while earlier signals are pending/active. The execution summary also
counts signals skipped specifically while a delayed order is pending.

Each summary and setup-key group reports signal/sample counts, missed-entry and
unavailable-outcome counts/reasons, overlap skips, TP/SL/TIME percentages, mean/
median gross R, net R, trade-life MFE/MAE in points and R, initial risk, and net
points per share. TP/SL/TIME denominators are measured samples. Counts reconcile:

```text
story_signal_count = samples + missed_entry_count
                  + unavailable_outcome_count + overlap_skipped_count
```

`paired_vs_baseline` compares matching successfully measured signal IDs, with
average/median changes plus baseline-only/variant-only sample counts. Thus a
variant cannot silently hide missed entries or a changed execution cohort.
Geometry changes the definition of 1R: compare **net points** as well as R before
attributing improvement to better geometry. Raw results can overweight dense
clusters; also inspect non-overlapping and setup-key summaries.

Research and holdout are separate for every predefined variant. No holdout
ranking or selection is performed. Inspect research paired changes by family
first, then inspect holdout as a separate check. Small samples, unmatched cohorts
and missing data do not support a dominant-weakness conclusion. Changing variants
or the split after examining holdout requires a genuinely new holdout.

## Running without the web app

Inside the existing backend environment, write only an optional JSON artifact:

```bash
python scripts/compare_entry_geometry.py \
  --from-date 2025-10-23 --to-date 2026-09-18 \
  --holdout-from-date 2026-06-15 \
  --output /tmp/entry-geometry.json
```

Alternatively, with a running backend container:

```bash
docker compose exec -T backend python scripts/compare_entry_geometry.py
```

Without `--output`, compact JSON goes to stdout. `--cost-model-file` reads the
same JSON cost-model object as the API. The runner uses the existing database
environment and a **read-only REPEATABLE READ** snapshot. It does not start the
web application/live feeds. Only indicators, stored market context and phase
parameters are read; outcome, rule, calibration and ML tables receive no writes.
No migrations are needed. CLI exit status 2 means a partial/insufficient/error
report; inspect its JSON instead of treating it as a successful backtest.

## Local data availability check

`research-results/entry-geometry-local.json` is a real read-only check of the
local Docker database on 2026-10-18. It reports:

- ITC: no 5m indicator rows.
- TATASTEEL: 16,875 5m bars, 2025-10-23 through 2026-09-18, all lacking stored
  story context; zero eligible signals in either period.

Its status is `PARTIAL_DATA`; TATASTEEL is `NO_STORY_ELIGIBLE_SIGNALS`. Null
statistics are intentional. This database cannot establish the dominant weakness.
The runner does not fetch missing ITC data, regenerate labels or invent results.

Tests cover baseline parity, timing and frozen ATR/direction, geometry, session/
split boundaries, holdout isolation, pending reservations, overlap counting,
count reconciliation, compactness, read-only SQL and missing-data/error responses.
