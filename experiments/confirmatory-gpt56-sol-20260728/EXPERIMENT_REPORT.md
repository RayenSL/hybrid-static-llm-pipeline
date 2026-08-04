# GPT-5.6 Sol confirmatory factorial experiment

## Integrity and sample

- Frozen 2 x 2 x 2 design: grounding x control structure x visible characterization-test feedback.
- 19 independent Long Method/God Class instances, three repetitions, eight cells: 456 ITT attempts.
- 456/456 repairs completed, built, materialized, and archived as viewable source trees.
- 17/19 visible tests admitted; 204/228 test-ON assignments received an immutable test.
- Private Layer 3 ran only after the post-repair seal: 447 pass, 9 regression, 0 not-run.

## Canonical strict-success results

| Control | Grounding | Tests | Strict success | Rate | Mean tokens |
|---|---|---|---:|---:|---:|
| iterative | off | off | 53/57 | 93.0% | 6043.7 |
| iterative | off | on | 54/57 | 94.7% | 6491.6 |
| iterative | on | off | 54/57 | 94.7% | 8091.4 |
| iterative | on | on | 57/57 | 100.0% | 8323.0 |
| single-shot | off | off | 43/57 | 75.4% | 2658.7 |
| single-shot | off | on | 48/57 | 84.2% | 2807.0 |
| single-shot | on | off | 57/57 | 100.0% | 3686.4 |
| single-shot | on | on | 57/57 | 100.0% | 3796.2 |

Overall strict success was **423/456 (92.8%)**. All 456 final sources built; 432 resolved the detector metric; 447 passed the private behavioral oracle.

All nine private regressions were iterative repairs of one target, `VatResolver.Resolve`: three ungrounded/test-OFF, three ungrounded/test-ON, and three grounded/test-OFF. Grounded iterative/test-ON had no private regression.

## Prespecified paired effects

- Confirmatory visible-test main effect: **+3.95 percentage points** (95% CI -0.57 to +8.46; exact cluster sign-flip p=0.125).
- Planned grounding main effect: **+11.84 percentage points** (95% CI +1.27 to +22.41; p=0.03125).
- Planned iteration main effect: **+5.70 percentage points** (95% CI -2.88 to +14.28; p=0.219).

The visible-test main CI crosses zero, so this experiment does not establish a statistically reliable average strict-success gain. Cell-specific test effects and interactions remain exploratory under the frozen power classification.

## Resource result

Visible tests added **234.4 repair tokens** on average (95% CI +135.1 to +333.8). Test generation plus repair used 2,426,669 tokens over 707 model calls, with nominal model cost **$33.673120** at the supplied rates.

## Mixed-effects sensitivity

The prespecified random-intercept logistic formula was fit. Regularized MAP and VB converged, but random-intercept SD estimates differed (0.746 vs 2.176); a weak-prior fit did not converge. Paired absolute risk differences are the primary interpretation; GLMM coefficients are sensitivity evidence.

## Chapter 5.4 replacement package

The complete Section 5.4 replacement is frozen under `results/chapter5_4/package`.
It contains Tables 5.2–5.15 plus supplemental Table 5.9a as CSV, Markdown,
and LaTeX and Figures 5.2–5.8 as PNG, SVG, and PDF, together with thesis-ready
captions and the canonical source
data used to regenerate them.

The post-run whole-solution remeasurement covered all 456 frozen repairs with no
LLM calls: 456/456 analyzer builds succeeded and 456/456 scans had CodeAnalyzer
data. Across all attempts, detector-smell count changed by -429, the all-rules CA
count by -106, and the enabled-by-default headline CA count by +46. The latter
increase is entirely in the Performance category and is reported separately from
the broader all-rules sensitivity tier. Exact triggering-metric extraction covered
all 456 final-source artifacts. The pristine manipulation check remained 30/30:
10 God Class, 10 Long Method, and 10 Obsolete API Usage detections.

## Thesis figures

The GPT-5.6 Sol figure package is frozen under `results/thesis-figures` and mirrored
to the repository's `output/figures` directory in PNG, SVG, and PDF. Figures 1–11
now have Sol outputs, and the updated Figure 5.1 is the model-independent pipeline
architecture. Figures 4 and 6 were redesigned around the frozen binary-grounding
factor because the earlier four-level context factor was not part of this design.
Figure 9 was redesigned as a repair-outcome profile because whole-solution
`quality_delta` was not persisted. The original GPT-5.4 definitions remain only
in the explicitly labeled `output/figures/legacy-gpt54` directory.
