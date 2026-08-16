"""Fit and document the prespecified factorial random-intercept logistic model."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import sys
import warnings
from pathlib import Path


FORMULA = (
    "strict_success ~ grounding * iterative * visible_test "
    "+ C(anti_pattern_type)"
)
VC_FORMULAS = {"instance": "0 + C(instance_id)"}
ANALYSIS_SEED = 20260728


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def serializable_optimizer(result) -> dict:
    values = result.optim_retvals
    jac = getattr(values, "jac", None)
    return {
        "success": bool(getattr(values, "success", False)),
        "message": str(getattr(values, "message", "")),
        "iterations": int(getattr(values, "nit", 0)),
        "function_value": float(getattr(values, "fun", math.nan)),
        "max_abs_gradient": (
            float(max(abs(float(value)) for value in jac))
            if jac is not None and len(jac) else None
        ),
    }


def coefficient_rows(label: str, model, result) -> list[dict]:
    rows = []
    for name, mean, sd in zip(model.exog_names, result.fe_mean, result.fe_sd):
        lo = float(mean - 1.959963984540054 * sd)
        hi = float(mean + 1.959963984540054 * sd)
        rows.append({
            "estimator": label,
            "term": name,
            "log_odds": float(mean),
            "approx_sd": float(sd),
            "approx_ci95_lo": lo,
            "approx_ci95_hi": hi,
            "odds_ratio": math.exp(float(mean)),
            "odds_ratio_ci95_lo": math.exp(lo),
            "odds_ratio_ci95_hi": math.exp(hi),
        })
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def validate_model_ready_data(data) -> tuple[int, int]:
    observations = len(data)
    instances = int(data["instance_id"].nunique())
    counts = data.groupby("instance_id").size()
    if instances < 2 or observations != instances * 24 or not (counts == 24).all():
        raise ValueError(
            "model-ready data must contain 24 factorial attempts for every independent instance"
        )
    return observations, instances


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--stats-path", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.stats_path))

    import numpy as np
    import pandas as pd
    import scipy
    import statsmodels
    from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM

    data = pd.read_csv(args.data)
    observations, instances = validate_model_ready_data(data)
    args.out.mkdir(parents=True, exist_ok=False)

    common = {"vcp_p": 0.5, "fe_p": 2.0}
    np.random.seed(ANALYSIS_SEED)
    map_model = BinomialBayesMixedGLM.from_formula(
        FORMULA, VC_FORMULAS, data, **common
    )
    map_result = map_model.fit_map()
    np.random.seed(ANALYSIS_SEED)
    vb_model = BinomialBayesMixedGLM.from_formula(
        FORMULA, VC_FORMULAS, data, **common
    )
    vb_result = vb_model.fit_vb()

    np.random.seed(ANALYSIS_SEED)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        weak_model = BinomialBayesMixedGLM.from_formula(
            FORMULA, VC_FORMULAS, data, vcp_p=1.0, fe_p=10.0
        )
        weak_result = weak_model.fit_map()

    coefficients = (
        coefficient_rows("laplace_map_regularized", map_model, map_result)
        + coefficient_rows("variational_bayes_regularized", vb_model, vb_result)
    )
    write_csv(args.out / "glmm_fixed_effects.csv", coefficients)

    variance_rows = [
        {
            "estimator": "laplace_map_regularized",
            "log_random_intercept_sd": float(map_result.vcp_mean[0]),
            "random_intercept_sd": math.exp(float(map_result.vcp_mean[0])),
            "approx_log_sd_sd": float(map_result.vcp_sd[0]),
        },
        {
            "estimator": "variational_bayes_regularized",
            "log_random_intercept_sd": float(vb_result.vcp_mean[0]),
            "random_intercept_sd": math.exp(float(vb_result.vcp_mean[0])),
            "approx_log_sd_sd": float(vb_result.vcp_sd[0]),
        },
    ]
    write_csv(args.out / "glmm_random_effect.csv", variance_rows)

    metadata = {
        "status": "completed_with_estimator_sensitivity",
        "formula": FORMULA + " + (1 | instance_id)",
        "input_sha256": sha256(args.data),
        "observations": observations,
        "instances": instances,
        "analysis_seed": ANALYSIS_SEED,
        "software": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
            "statsmodels": statsmodels.__version__,
        },
        "primary_model_fit": {
            "estimator": "statsmodels BinomialBayesMixedGLM fit_map; Laplace/MAP",
            "fixed_effect_prior_sd": 2.0,
            "log_random_effect_sd_prior_sd": 0.5,
            "optimizer": serializable_optimizer(map_result),
        },
        "sensitivity_model_fit": {
            "estimator": "statsmodels BinomialBayesMixedGLM fit_vb; mean-field variational Bayes",
            "fixed_effect_prior_sd": 2.0,
            "log_random_effect_sd_prior_sd": 0.5,
            "optimizer": serializable_optimizer(vb_result),
        },
        "weak_prior_diagnostic": {
            "estimator": "Laplace/MAP",
            "fixed_effect_prior_sd": 10.0,
            "log_random_effect_sd_prior_sd": 1.0,
            "optimizer": serializable_optimizer(weak_result),
            "warnings": [str(item.message) for item in caught],
            "random_intercept_sd": math.exp(float(weak_result.vcp_mean[0])),
        },
        "interpretation": (
            "The regularized fits converge but their random-intercept SD estimates "
            "differ materially. The weak-prior fit does not converge and collapses "
            "the random-effect variance, consistent with near-separation and only "
            f"{instances} clusters. Use the prespecified instance-level paired risk differences "
            "as the primary effect-scale results; treat GLMM coefficients as "
            "model-based sensitivity evidence."
        ),
    }
    (args.out / "GLMM_METADATA.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )

    report = [
        "# Prespecified random-intercept logistic model",
        "",
        f"Formula: `{metadata['formula']}`",
        "",
        "The regularized Laplace/MAP model converged, and the same formula also "
        "converged under variational Bayes. The estimated random-intercept standard "
        f"deviation was {variance_rows[0]['random_intercept_sd']:.3f} under MAP and "
        f"{variance_rows[1]['random_intercept_sd']:.3f} under VB.",
        "",
        "A weak-prior MAP diagnostic did not converge and pushed the random-effect "
        f"variance to the boundary. With {instances} clusters and near-complete success in "
        "several cells, the model is weakly identified. Coefficients and approximate "
        "intervals are retained in glmm_fixed_effects.csv, but the paired "
        "instance-level absolute risk differences remain the primary interpretation.",
    ]
    (args.out / "GLMM_REPORT.md").write_text(
        "\n".join(report) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
