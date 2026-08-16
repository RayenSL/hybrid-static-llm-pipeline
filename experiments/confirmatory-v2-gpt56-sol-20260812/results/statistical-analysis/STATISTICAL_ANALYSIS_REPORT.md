# Confirmatory statistical analysis

## Analysis population and estimands

The analysis retains all 624 randomised assignments across 26 independent anti-pattern targets, eight factorial cells and three repeated model generations per cell. The failed StatementBuilder assignment remains in the intention-to-treat population as an unsuccessful repair. Its token count and post-repair quality measurements are unavailable, so analyses of those outcomes use the available observations and state the resulting denominator.

The primary estimand is the absolute change in strict-success probability associated with visible-test exposure, averaged over grounding and control structure. Repetitions were first averaged within target and factorial cell. Confidence intervals use the paired target-level Student interval with 25 degrees of freedom. Hypothesis tests use an exact two-sided sign-flip distribution over the 26 target-level contrasts, evaluated by discrete dynamic programming. Holm adjustment is applied within the prespecified families of simple effects and interactions.

## Primary result

Visible-test exposure increased strict success by 2.56 percentage points (95% CI -1.09 to 6.22; exact p = 0.3125). The estimate is positive, but the interval includes both no effect and a small adverse effect. The experiment therefore provides no statistically persuasive evidence that the five-case visible behavioural suite improved strict success under the tested conditions.

## Planned secondary effects

Binary grounding increased strict success by 7.69 percentage points when averaged over control structure and visible-test exposure (95% CI 1.60 to 13.78; exact p = 0.015625). This is the clearest planned secondary effect. The simple grounding contrasts did not remain below 0.05 after Holm adjustment, so the result supports an average grounding benefit rather than a claim about any single factorial cell.

Iterative control increased strict success by 2.56 percentage points on average (95% CI -3.95 to 9.07; exact p = 0.5625). There is no clear evidence of an iteration main effect. The grounding-by-test, control-by-test and three-way interactions all had Holm-adjusted p-values of 0.75. None of the four cell-specific visible-test effects was significant after adjustment; their adjusted p-values ranged from 0.50 to 1.00.

## Token cost

Visible-test exposure added an estimated 1,611.83 repair tokens per assignment (95% CI 1,361.87 to 1,861.79; exact p = 1.19e-7). This paired analysis contains 25 targets because the failed StatementBuilder assignment has no token count. The increase is expected because the generated test suite is included in the model input, but it is a material cost: the experiment found a clear token overhead without detecting a corresponding strict-success benefit.

## Behavioural and structural outcomes

The campaign produced 586 strict successes out of 624 assignments (93.9%). Private Layer 3 evaluation observed 612 behavioural passes and 11 regressions among 623 materialised repairs; one assignment was unavailable following the API failure. All 11 regressions occurred for VatResolver.

Layer 2 scored all 623 materialised repairs. The targeted smell count fell by one in 587 cases, was unchanged in 29, and increased by one in seven. The mean change in all compiler-analyser findings was -0.289. These figures are descriptive structural outcomes. They must not be treated as substitutes for behavioural preservation: each of the 11 private regressions nevertheless reduced the targeted smell count.

## Mixed-effects sensitivity analysis

The prespecified random-intercept logistic model was fitted as a sensitivity analysis. Regularised Laplace/MAP and variational-Bayes fits both converged, but their estimated random-intercept standard deviations differed sharply (0.002 and 2.027). A weak-prior MAP diagnostic did not converge and collapsed the variance estimate to the boundary. This estimator sensitivity is consistent with a high overall success rate, near-complete success in several cells and only 26 clusters. The paired absolute risk differences therefore remain the primary results; mixed-model coefficients should not be presented as more stable or definitive estimates.

## Interpretation

The strongest supported conclusion is that grounding improved strict success on average. The five-case visible-test intervention imposed a substantial token cost but did not show a reliable improvement in strict success. Iteration and the tested interactions were not clearly distinguishable from zero. The ceiling in several factorial cells limits precision, particularly for cell-specific effects, and the single unavailable assignment prevents a completely balanced analysis of token and quality outcomes.
