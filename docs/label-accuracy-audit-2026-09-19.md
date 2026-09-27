# Labelling accuracy audit

Date: 2026-09-19

## Scope and definition

The audit compares 134,400 `market_context` labels for TATASTEEL with the
matching raw candles and indicator rows across 1m, 3m, 5m, and 15m. All label
timestamps matched both source tables.

Two separate measurements are used:

1. **Directional label alignment** resolves each phase through the production
   `PHASE_MODEL`, enters at the next candle open, and compares the price at the
   configured lookahead within the same IST session.
2. **Execution outcome accuracy** uses the production TP/SL simulator, including
   next-bar entry, conservative same-bar stops, slippage, transaction costs,
   macro/structure gates, and end-of-session limits.

Market-state labels are descriptive context. They are not automatically valid
trade predictions, so RANGE, NEUTRAL, and unresolved directions are excluded
from directional accuracy.

## Results

| Timeframe | Direction accuracy | Active accuracy* | Simulated trades | Net win rate | Average gross R | Average net R | Average cost R |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1m | 48.70% | 49.17% | 390 | 45.90% | -0.124 | -0.711 | 0.587 |
| 3m | 48.64% | 48.97% | 1,170 | 43.93% | -0.134 | -0.700 | 0.566 |
| 5m | 48.80% | 49.19% | 1,535 | 42.02% | -0.119 | -0.665 | 0.546 |
| 15m | 47.83% | 48.49% | 1,338 | 29.60% | -0.156 | -0.608 | 0.452 |

\* Active accuracy excludes forward moves smaller than 0.25 ATR and is always
paired with coverage in the workbook.

Across all 4,433 simulated outcomes, net win rate is **39.12%**, gross win rate
is **44.03%**, average gross expectancy is **-0.134R**, and average net
expectancy is **-0.661R**. Only **3.30%** of all labelled rows become simulated
outcomes.

The current system does not provide evidence for a 99% accuracy target. The
best timeframe is 45.90%, leaving a 53.10 percentage-point gap. Directional
alignment is close to random across every timeframe, and costs amplify an edge
that is already negative before costs.

## Primary bottlenecks

1. **Direction and phase selection have negative gross expectancy.** Cost
   reduction cannot repair the model by itself.
2. **Validation covers one symbol.** Results from TATASTEEL cannot support a
   market-wide claim.
3. **Executable coverage is only 3.30%.** Accuracy must always be reported with
   coverage and sample size so abstention cannot inflate the headline number.
4. **Lower timeframes pay 0.55R-0.59R average cost.** Small moves are consumed
   by friction.
5. **State labels and prediction targets are mixed.** A market phase, trade
   direction, entry rule, and future outcome need separate versioned fields.
6. **No stored outcomes existed before this audit.** There was no durable
   ground truth for earlier accuracy claims.
7. **Rare phases have inadequate samples.** Phase-specific percentages are
   unreliable without minimum counts and confidence intervals.

## Path toward high precision

1. Freeze a chronological holdout and do not tune against it.
2. Generate labels and outcomes for at least 30 liquid, sector-diverse symbols.
3. Separate state classification from direction, horizon, entry, and abstain
   targets.
4. Disable phases that fail to produce positive net expectancy on unseen data.
5. Train and calibrate a probability model, then publish a precision-versus-
   coverage curve rather than accuracy alone.
6. Require positive net expectancy, profit factor above 1.1, adequate sample
   counts, and symbol-held-out stability before enabling a phase.
7. Monitor monthly drift, coverage, cost, and confidence intervals.

Reaching 99% precision may only be possible with extremely low coverage. Any
such result must state how many opportunities were rejected and must survive a
locked, multi-symbol holdout without leakage.
