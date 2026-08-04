# Four-level grounding supplement

This separately frozen 30-target matched experiment compares Minimal, Structural, Relational, and Full detector context using one GPT-5.6 Sol observation per target-level cell. It supplements and does not alter the completed 2 × 2 × 2 confirmatory factorial.

## Table 5.9b: Four-level grounding effectiveness

| Context | n | Unapplicable | Build failed | Built unresolved | Detector-resolved | Verified rate [95% CI] | Layer 3 pass | Layer 3 regression | Layer 3 not run | Behavior-preserving verified |
|---|---|---|---|---|---|---|---|---|---|---|
| Minimal | 30 | 21 | 0 | 0 | 9 | 30.0% [16.7, 47.9] | 8 | 1 | 0 | 8 |
| Structural | 30 | 22 | 0 | 0 | 8 | 26.7% [14.2, 44.4] | 7 | 1 | 0 | 7 |
| Relational | 30 | 17 | 2 | 0 | 11 | 36.7% [21.9, 54.5] | 8 | 3 | 2 | 8 |
| Full | 30 | 19 | 2 | 0 | 9 | 30.0% [16.7, 47.9] | 7 | 2 | 2 | 7 |

## Matched inference

| Test | Statistic | df | p | Holm p |
|---|---|---|---|---|
| Global Cochran Q | 2.4783 | 3 | 0.479233 | — |
| Structural − Minimal | 1 vs 0 discordant | — | 1 | 1 |
| Relational − Structural | 1 vs 4 discordant | — | 0.375 | 1 |
| Full − Relational | 4 vs 2 discordant | — | 0.6875 | 1 |

## Adjacent paired risk differences

| Contrast | Lower-only | Higher-only | Risk difference (pp) | 95% bootstrap CI (pp) | Exact McNemar p | Holm p |
|---|---|---|---|---|---|---|
| Structural − Minimal | 1 | 0 | -3.3 | [-10.0, +0.0] | 1 | 1 |
| Relational − Structural | 1 | 4 | +10.0 | [-3.3, +23.3] | 0.375 | 1 |
| Full − Relational | 4 | 2 | -6.7 | [-23.3, +10.0] | 0.6875 | 1 |

## Token consumption and nominal Sol cost

| Context | Mean prompt characters | Generation input tokens | Generation output tokens | Applier input tokens | Applier output tokens | Nominal Sol cost (USD) |
|---|---|---|---|---|---|---|
| Minimal | 2247.3 | 20434 | 20266 | 31988 | 6525 | 0.7102 |
| Structural | 2516.7 | 22911 | 21318 | 31755 | 5773 | 0.7541 |
| Relational | 3554.2 | 30601 | 22797 | 32372 | 6599 | 0.8369 |
| Full | 3686.0 | 31531 | 23740 | 32620 | 6897 | 0.8699 |

One repetition per target-level cell prevents estimation of within-cell stochastic variance. Obsolete API private outcomes use a smoke oracle and remain stratified in the source tables. Full differs from Relational through frozen factual project metadata; all targets occupy unique files, so no co-located findings were available.
