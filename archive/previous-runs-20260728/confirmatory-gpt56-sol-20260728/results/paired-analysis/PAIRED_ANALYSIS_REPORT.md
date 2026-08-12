# Factorial test-feedback analysis

- ITT attempts: 456
- Independent anti-pattern instances: 19
- Strict successes: 423/456 (92.8%)
- Private behavioral passes: 447/456 (98.0%)
- Private behavioral regressions: 9/456

## Confirmatory primary estimand

Visible-test main effect (test ON minus OFF, averaged over grounding and control): +3.95 percentage points (95% CI -0.57 to +8.46; exact cluster sign-flip p=0.125).

Cell-specific test effects and interactions are retained as exploratory because the frozen power analysis classified them as underpowered. See paired_risk_differences.csv.

## Prespecified mixed-effects model

A model-ready attempt table is emitted, but the GLMM was not fit in this pass because the frozen local runtime contains neither R nor a validated mixed-model Python package. This is recorded explicitly rather than substituting an unvalidated post-hoc optimizer.
