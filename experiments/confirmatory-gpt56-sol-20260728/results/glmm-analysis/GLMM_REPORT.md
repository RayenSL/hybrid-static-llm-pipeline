# Prespecified random-intercept logistic model

Formula: `strict_success ~ grounding * iterative * visible_test + C(anti_pattern_type) + (1 | instance_id)`

The regularized Laplace/MAP model converged, and the same formula also converged under variational Bayes. The estimated random-intercept standard deviation was 0.746 under MAP and 2.176 under VB.

A weak-prior MAP diagnostic did not converge and pushed the random-effect variance to the boundary. With 19 clusters and near-complete success in several cells, the model is weakly identified. Coefficients and approximate intervals are retained in glmm_fixed_effects.csv, but the paired instance-level absolute risk differences remain the primary interpretation.
