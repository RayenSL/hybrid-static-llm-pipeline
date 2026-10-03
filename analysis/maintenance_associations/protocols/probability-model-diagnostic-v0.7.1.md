# Probability-model diagnostic — 22 September 2026

After fitting the fixed v0.7 models, the linear probability models produced fitted probabilities outside [0,1] for approximately 2–21% of observations, depending on the contrast. This is a concrete specification diagnostic. Retain the original models and add a binomial-logit sensitivity with the identical comparison rows, spline basis and year effects.

Report the mean fitted probability difference when setting the flag to one versus zero over those comparison rows. Use delta-method uncertainty with the same two-way clustered covariance and calendar degrees of freedom. Verify that rebuilding the design reproduces the original linear probability coefficient. Record any non-convergence or invalid covariance. Apply Holm adjustment separately to this diagnostic family if showing significance decisions.

This addition follows inspection of the main results and must be labelled a model-form sensitivity, not a pre-specified primary model. Do not replace the original result with whichever model is more favourable. The standardised contrast is an adjusted association; the observational data and missing confounders do not justify an intervention effect.
