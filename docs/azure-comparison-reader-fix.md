# Azure comparison label retrieval fix

Verified and deployed on 2026-10-18. The deployed Git baseline was `78e0822`;
the reader/diagnostic fix is applied to the VM working tree. Only `backend/db.py`
and `backend/routes/strategy_comparison.py` were deployed. Backend was reloaded;
Nginx and PostgreSQL were not restarted.

## Demonstrated cause

Instrumentation wrapped the deployed `run_entry_geometry_comparison()` and used
the **exact connection it opened**, inside its read-only repeatable-read
transaction. It did not use a local database or a separate pgAdmin connection.

Connection identity:

```json
{
  "database": "candleticks",
  "schema": "public",
  "search_path": "\"$user\", public",
  "host": "postgres",
  "port": 5432,
  "server_address": "172.18.0.2/32",
  "server_port": 5432,
  "transaction_read_only": "on",
  "transaction_isolation": "repeatable read"
}
```

For each symbol, SQL returned 16,725 indicators, 16,650 matching market-context
rows and 16,650 non-null `story_regime` values. Constructing the raw pandas
DataFrame also preserved 16,650 labels. Calling the old `read_sql_safe` then
returned **zero** non-null labels. Loss occurred in retrieval conversion, before
story eligibility or comparison processing.

Azure runs pandas **3.0.6**. Its inferred string dtype uses a floating-point NaN
for missing strings. The leading unmatched-context rows therefore supplied NaN
as the first label value. The reader skipped only `None`, treated this NaN as a
numeric sample, and ran `pd.to_numeric(errors="coerce")` on the entire textual
column. Every valid story/phase/event string was thereby coerced to NaN.

The fix samples the first **non-missing** value via `Series.dropna()` before
deciding whether numeric/Decimal conversion is appropriate. Text labels and JSON
objects remain intact; numeric conversion remains available for numeric fields.
`READ_SQL_SAFE_VERSION` is now `NON_NULL_SAMPLE_V2`.

The pre-fix comparison source SHA256 was
`22734fb73576f9ba319580fc468ca70f800d2f7d114af19e08b5762f0b65208d`.
The pre-fix reader SHA256 was
`f310daa03c66b305e942a49f7ada79bd4d1b309388670b42cd6e527bd7ac9711`.
Before deployment, local baseline and downloaded Azure sources were compared
and their ASTs matched. Original VM files were backed up to
`/home/azureuser/comparison-reader-backup-20261018T173045Z`.

## Permanent API diagnostics

`data_read_diagnostics` now contains connection identity (no user/password),
reader/pandas versions, independent SQL join counts, counts immediately after
`read_sql_safe` returns, and counts after comparison processing. Counts and data
loading share the same join/filter fragment, parameters and database transaction.
The SQL counts are retrieved independently through that connection's cursor.

Stage labels distinguish:

- `NO_INDICATOR_DATA` or `SQL_NO_STORY_LABELS`: loss/absence already at SQL.
- `DATAFRAME_RETRIEVAL_MISMATCH`: SQL labels/rows differ from returned DataFrame.
- `IN_MEMORY_PROCESSING_MISMATCH`: labels differ after comparison processing.
- `CONSISTENT`: labels survive all stages; eligibility remains a separate test.

A retrieval mismatch returns `DATA_READ_MISMATCH` instead of quietly reporting
an empty strategy cohort. No label generation or database repair is performed.

## Actual public HTTPS verification

Both public comparison and counterfactual endpoints were POSTed with the same
fixed window, `2000-01-01` through `2026-10-18`, NSE 5m, default cost model.

| Symbol | Indicators | SQL context matches | SQL labels | DataFrame labels | Processed labels | Eligible signals |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ITC | 16,725 | 16,650 | 16,650 | 16,650 | 16,650 | 3,011 |
| TATASTEEL | 16,725 | 16,650 | 16,650 | 16,650 | 16,650 | 3,072 |

The public comparison status is `SUCCESS`; both diagnostic stages are
`CONSISTENT`. Each symbol correctly has only 75 bars without story labels.

Baseline simulated sample counts matched the existing counterfactual endpoint:

| Symbol | Research samples | Holdout samples |
| --- | ---: | ---: |
| ITC | 2,024 | 966 |
| TATASTEEL | 2,122 | 925 |

All 1,216 tested metric comparisons matched exactly (maximum absolute difference
0.0): sample counts, TP/SL/TIME percentages, mean/median gross/net R, trade MFE/MAE
in points and R, risk and net points, for both periods and every setup-key group.
Counterfactual input rows are 16,650 because that endpoint inner-joins context;
comparison retains all 16,725 price bars. Eligible cohorts and measured baseline
outcomes nevertheless match; missing-context bars do not invent signals.

The compact actual verification report is
[`research-results/azure-comparison-verification.json`](research-results/azure-comparison-verification.json).
Both counterfactual requests reported `rows_written: 0`; the comparison transaction
reported `transaction_read_only: on`. No labels, outcomes, phase parameters or ML
records were written. Production story, safety, TP/SL, lookahead and fee modules
were not edited. The existing instrument sync lock and populated instrument table
were checked before reload to ensure startup did not initiate instrument sync.

## Regression coverage

112 tests pass. New regression cases include 16,725 rows per symbol with 75
leading missing-context rows and 16,650 valid labels, using pandas string inference;
NaN/None/pd.NA handling; JSON and Decimal compatibility; and stage diagnosis.
Endpoint tests verify count queries use the same connection and parameters as
the comparison data load. Existing comparison and counterfactual tests also pass.
