# Market Story Label Audit

Date: 2026-09-19  
Dataset: TATASTEEL stored `market_context` rows  
Timeframes: 1m, 3m, 5m, 15m

## Verdict

The system has a useful and fully traceable per-bar event classifier, but it has not yet achieved a stable, unified market story.

Every audited row has a phase and a reason. Gap, impulse, compression, and trend-continuation labels follow their defining conditions well. The main weakness is that `market_phase` mixes two different concepts:

1. a persistent market regime, such as bull trend, bear trend, range, or transition; and
2. a short-lived bar event, such as impulse, digestion, pause, absorption, or gap fill.

Because both are stored in one field, the label frequently changes after one candle even when the broader market regime has not changed. This creates a technically populated label stream rather than a clean narrative.

## What the code does correctly

- The state machine is the single phase-assignment authority.
- Previous phase constrains the allowed next states.
- `phase_reason` records which branch assigned each label.
- Rolling gap thresholds use previous observations and do not backfill future information.
- Swing points are read only after their confirmation delay, so the audited path does not use an unconfirmed future swing.
- Warm-up rows are excluded before labels are persisted.
- All stored rows have a phase and a non-empty reason.
- Every audited gap day starts with a valid gap label and later receives a resolution label.
- Impulse and compression labels had no basic semantic-rule violations in the audited data.
- Trend-continuation labels had approximately 0% to 0.10% basic semantic-rule violations.

## Coverage and completeness

| Timeframe | Rows | Unclassified | Missing reason | Distinct phases |
|---|---:|---:|---:|---:|
| 1m | 84,000 | 0 | 0 | 30 |
| 3m | 28,000 | 0 | 0 | 29 |
| 5m | 16,800 | 0 | 0 | 29 |
| 15m | 5,600 | 0 | 0 | 28 |

Coverage is excellent. Coverage alone does not establish that the story is semantically correct or stable.

## Gap-story validation

| Timeframe | Gap days | Valid opening story | Resolved days |
|---|---:|---:|---:|
| 1m | 192 | 192 | 192 |
| 3m | 185 | 185 | 185 |
| 5m | 179 | 179 | 179 |
| 15m | 157 | 157 | 157 |

The gap lifecycle is the strongest part of the current market story: 100% of audited gap days had both a valid opening classification and a later resolution.

## Main bottleneck: story churn

| Timeframe | Phase runs | Average run length | One-bar runs | Average runs per day |
|---|---:|---:|---:|---:|
| 1m | 43,000 | 1.95 bars | 67.78% | 191.96 |
| 3m | 16,954 | 1.65 bars | 71.23% | 75.69 |
| 5m | 10,533 | 1.59 bars | 72.18% | 47.02 |
| 15m | 3,664 | 1.53 bars | 74.29% | 16.36 |

Between 68% and 74% of phase runs last only one bar. The most common changes are repeated switches between continuation and digestion, followed by switches between digestion and balance/chop. These may describe individual candles, but they do not form a stable regime story.

## Digestion and acceptance are semantically overloaded

The simple semantic check treated a bullish trend-context label as contradictory when the stored slope was non-positive or price was below VWAP, and used the mirrored rule for bearish labels. This is a diagnostic rather than final ground truth.

| Timeframe | Bull trend-context contradictions | Bear trend-context contradictions |
|---|---:|---:|
| 1m | 9,894 | 8,349 |
| 3m | 2,112 | 1,916 |
| 5m | 1,248 | 947 |
| 15m | 722 | 507 |

Continuation labels are internally consistent. Most contradictions come from digestion, acceptance, pause, and fallback-context branches. Examples of reasons include:

- `P3a:nml_ema_stack`
- `P3a:nml_slope`
- `P3a:nml_obv_rescue`
- `P5:fallback_bull_context`
- the mirrored bearish branches

On 15m data, 54.62% of bullish digestion rows and 45.26% of bearish digestion rows contradicted at least one current-condition check. This does not mean every row is wrong: digestion can temporarily oppose the broader trend. It shows that the label does not tell the consumer whether it represents the current candle or a retained background regime.

One recent 15m session demonstrates the problem. The sequence correctly began with `MODERATE_GAP_DOWN`, moved to `GAP_FILLED`, and then found a bullish trend. Later, `TREND_DIGESTION` persisted through negative slope and strongly negative VWAP distance because `P5:fallback_bull_context` retained the earlier bullish context. The final transition to `BEAR_TREND_ACCEPTANCE` came only after several contradictory bars.

## Cross-timeframe story agreement

The following comparison aligns the lower-timeframe label with each 15m timestamp.

| Timeframe compared with 15m | Aligned bars | Exact phase agreement | Opposite directional story |
|---|---:|---:|---:|
| 1m | 5,600 | 41.02% | 22.34% |
| 3m | 5,600 | 44.59% | 13.71% |
| 5m | 5,600 | 48.55% | 9.84% |

Some disagreement is expected because 1m, 3m/5m, and 15m have different roles. The current output does not turn these separate views into one story or explicitly flag a conflict. A consumer therefore cannot tell whether the system sees confirmation, a pullback, or an unresolved timeframe disagreement.

## Directional dominance and predictive limitation

| Timeframe | Trend labels | Chop labels | Impulse labels | Gap labels |
|---|---:|---:|---:|---:|
| 1m | 77.73% | 13.68% | 4.74% | 2.17% |
| 3m | 67.51% | 18.55% | 8.81% | 3.11% |
| 5m | 64.01% | 19.35% | 10.20% | 4.05% |
| 15m | 63.20% | 19.89% | 6.84% | 7.14% |

Trend-context labels dominate, especially on 1m. In the separate future-outcome audit, directional alignment was only about 48% to 49%. A label can correctly describe current context without predicting the next move, but the combination of high trend-label frequency and weak forward alignment shows that trend context should not be presented as a trade forecast.

## Required model change

Replace the single overloaded phase with two first-class outputs:

### 1. Persistent regime

`story_regime` should use a small stable vocabulary:

- `BULL_TREND`
- `BEAR_TREND`
- `RANGE`
- `GAP_AUCTION`
- `TRANSITION`

Require two or three consecutive confirmations before changing regime. Route an opposite-direction change through `TRANSITION` or `RANGE` unless a separately defined reversal event has unusually high confidence.

### 2. Current bar event

`bar_event` can retain the detailed vocabulary:

- `IMPULSE`
- `CONTINUATION`
- `DIGESTION`
- `PAUSE`
- `ABSORPTION`
- `DISTRIBUTION`
- `GAP_FILL`
- other existing short-lived events

This allows a sequence such as `BULL_TREND + DIGESTION`, `BULL_TREND + CONTINUATION`, and `BULL_TREND + PAUSE` without falsely presenting three regime changes.

## Logic changes needed

1. Tighten bullish digestion so it retains at least two of these three conditions: positive slope, price above VWAP or EMA21, and bullish EMA stack. Mirror the rule for bearish digestion. Otherwise emit `TRANSITION`.
2. Limit `P5:fallback_bull_context` and its bearish mirror when both slope and VWAP relationship contradict the retained direction.
3. Use one acceptance definition in every branch. Some fallback branches currently emit acceptance without the core acceptance conditions.
4. Add `regime_confidence`, `event_confidence`, and `regime_invalidation_reason`.
5. Store stable `phase_reason_code` values and put numeric evidence in structured `reason_details`. The current numeric reason strings create 1,129 distinct reason values and make aggregation harder.
6. Produce `micro_story`, `confirm_story`, `execution_story`, `story_conflict`, and `composite_story` so the multi-timeframe result is explicit.

## How to measure actual market-story accuracy

There is no independent ground-truth story label in the database, so a defensible overall accuracy percentage cannot yet be calculated. Rule compliance and continuity can be measured automatically, but true semantic accuracy needs an expert-labelled benchmark.

Create a review set of at least 30 to 50 sessions across several symbols and market conditions. For every meaningful segment, record the expert regime, bar event, transition point, and supporting evidence. Then report:

- regime confusion matrix;
- event confusion matrix;
- expert agreement and Cohen's kappa;
- median regime duration and one-bar regime rate;
- illegal transition rate;
- cross-timeframe conflict rate;
- precision and recall for reversals, gaps, impulses, and range states.

The immediate target should be a one-bar **regime** rate below 5%, zero direct low-confidence bull-to-bear flips, and strong expert agreement. A 99% goal is realistic for data completeness and deterministic rule execution; it should not be claimed for subjective market interpretation or future-price prediction without a representative expert-labelled test set.

## RULE_V1 implementation result

The first shadow-mode implementation was added on 2026-09-19. It preserves `market_phase` and existing ML/execution behavior while adding:

- `story_regime` and `bar_event`;
- deterministic `regime_rule_score` and `event_rule_score` values;
- candidate regime, candidate age, candidate score, and confirmed-regime age;
- stable regime and event reason codes;
- structured JSON evidence and a story version;
- three-candle confirmation and mandatory `TRANSITION` routing for directional reversals.

All four TATASTEEL histories were re-labelled after the implementation.

| Timeframe | Legacy average run | RULE_V1 average regime run | Legacy one-bar runs | RULE_V1 one-bar runs | RULE_V1 non-gap one-bar runs | Direct bull/bear flips | Missing story rows |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1m | 1.95 | 12.92 | 67.78% | 3.06% | 0.69% | 0 | 0 |
| 3m | 1.65 | 10.56 | 71.23% | 6.60% | 1.71% | 0 | 0 |
| 5m | 1.59 | 8.81 | 72.18% | 9.91% | 2.78% | 0 | 0 |
| 15m | 1.53 | 5.93 | 74.29% | 13.97% | 3.94% | 0 | 0 |

The first implementation meets the automated stability target for non-gap regimes on every timeframe. Gap auctions account for most remaining one-bar regimes because some gaps fill or resolve during the opening candle.

`TRANSITION` currently represents 26.02% of 1m bars, 25.08% of 3m bars, 32.04% of 5m bars, and 46.00% of 15m bars. This is safer than retaining a contradicted trend, but the 15m share needs expert review. The next calibration should compare transition segments with human-labelled sessions and decide whether weak directional conflict should be classified as `RANGE` or remain `TRANSITION`.
