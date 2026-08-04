# Confirmatory-run power sensitivity

Monte Carlo simulations: 10,000 per condition; independent instances: 19; repetitions: 3.
The analysis uses instance-level paired factorial contrasts. A beta-distributed instance baseline supplies exchangeable heterogeneity. The four cell-specific test contrasts use conservative Holm alpha 0.0125; other contrasts use alpha 0.05.

## Central scenario

| Estimand | Alpha | Power at 20 pp | Power at 30 pp |
|---|---:|---:|---:|
| visible test main | 0.0500 | 0.993 | 1.000 |
| cell specific test | 0.0125 | 0.390 | 0.801 |
| two way test interaction | 0.0500 | 0.627 | 0.922 |
| three way interaction | 0.0500 | 0.202 | 0.396 |

## Classification at the frozen 20-point minimum effect

- visible test main: adequately powered; sensitivity power 0.993-0.997.
- cell specific test: underpowered / exploratory; sensitivity power 0.390-0.419.
- two way test interaction: underpowered / exploratory; sensitivity power 0.627-0.703.
- three way interaction: underpowered / exploratory; sensitivity power 0.202-0.248.

This simulation is a design sensitivity analysis for the paired risk-difference estimands, not a claim about eventual observed effects. The mixed-effects logistic model remains the prespecified outcome model; interactions classified as underpowered are reported as exploratory with confidence intervals.
