from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from scipy.stats import t as student_t

N_SIM = 10_000
N_INSTANCES = 19
REPETITIONS = 3
SIMULATION_SEED = 20260727
EFFECTS = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40]
SCENARIOS = [
    ("central", 0.50, 0.20),
    ("lower_success", 0.30, 0.20),
    ("higher_success", 0.70, 0.20),
    ("high_heterogeneity", 0.50, 0.50),
]

# Cell order is (grounding, iterative, visible_test), lexicographic in 0/1.
CELLS = [(g, c, v) for g in (0, 1) for c in (0, 1) for v in (0, 1)]

def weights(predicate):
    return np.array([predicate(g, c, v) for g, c, v in CELLS], dtype=float)

CONTRASTS = {
    # Average test-ON minus test-OFF across grounding and control.
    "visible_test_main": (weights(lambda g, c, v: 0.25 if v else -0.25), 0.05),
    # Representative of each of four grounding x control cell-specific test effects.
    "cell_specific_test": (weights(lambda g, c, v: (1.0 if v else -1.0) if (g == 0 and c == 0) else 0.0), 0.0125),
    # Representative test interaction; grounding x test and control x test are symmetric here.
    "two_way_test_interaction": (weights(lambda g, c, v: (0.5 if v else -0.5) * (1.0 if g else -1.0)), 0.05),
    # Difference-in-difference-in-differences.
    "three_way_interaction": (weights(lambda g, c, v: (1.0 if g else -1.0) * (1.0 if c else -1.0) * (1.0 if v else -1.0)), 0.05),
}


def simulate_power(rng, contrast, alpha, effect, baseline_mean, rho):
    # Beta-distributed instance baselines induce exchangeable within-instance correlation.
    concentration = (1.0 / rho) - 1.0
    a = baseline_mean * concentration
    b = (1.0 - baseline_mean) * concentration
    baseline = rng.beta(a, b, size=(N_SIM, N_INSTANCES, 1))

    # Add the requested contrast by the minimum-L2 symmetric perturbation. This makes
    # dot(contrast, p) equal the requested risk difference before boundary clipping.
    perturbation = effect * contrast / float(np.dot(contrast, contrast))
    probabilities = np.clip(baseline + perturbation.reshape(1, 1, 8), 0.01, 0.99)
    observed = rng.binomial(REPETITIONS, probabilities) / REPETITIONS
    instance_contrasts = observed @ contrast
    means = instance_contrasts.mean(axis=1)
    standard_errors = instance_contrasts.std(axis=1, ddof=1) / np.sqrt(N_INSTANCES)
    statistics = np.divide(means, standard_errors, out=np.zeros_like(means), where=standard_errors > 0)
    critical = student_t.ppf(1.0 - alpha / 2.0, N_INSTANCES - 1)
    realized = (probabilities @ contrast).mean(axis=1)
    return float(np.mean(np.abs(statistics) > critical)), float(realized.mean())


def main():
    rng = np.random.default_rng(SIMULATION_SEED)
    rows = []
    for scenario, baseline, rho in SCENARIOS:
        for name, (contrast, alpha) in CONTRASTS.items():
            for effect in EFFECTS:
                power, realized = simulate_power(rng, contrast, alpha, effect, baseline, rho)
                rows.append({
                    "scenario": scenario,
                    "baseline_success": baseline,
                    "instance_icc": rho,
                    "estimand": name,
                    "alpha": alpha,
                    "target_risk_difference": effect,
                    "realized_risk_difference": realized,
                    "power": power,
                    "simulations": N_SIM,
                    "instances": N_INSTANCES,
                    "repetitions": REPETITIONS,
                })

    out = Path(__file__).resolve().parent
    fields = list(rows[0])
    with (out / "power_grid.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    central = [r for r in rows if r["scenario"] == "central" and r["target_risk_difference"] in (0.20, 0.30)]
    minimum = [r for r in rows if r["target_risk_difference"] == 0.20]
    classifications = {}
    for name in CONTRASTS:
        values = [r["power"] for r in minimum if r["estimand"] == name]
        classifications[name] = {
            "minimum_power_across_scenarios_at_20pp": min(values),
            "maximum_power_across_scenarios_at_20pp": max(values),
            "adequate_at_80_percent_in_all_scenarios": min(values) >= 0.80,
        }
    (out / "power_classification.json").write_text(json.dumps({
        "method": "cluster-level paired risk-difference Monte Carlo sensitivity analysis",
        "simulation_seed": SIMULATION_SEED,
        "minimum_meaningful_risk_difference": 0.20,
        "classifications": classifications,
    }, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Confirmatory-run power sensitivity",
        "",
        f"Monte Carlo simulations: {N_SIM:,} per condition; independent instances: {N_INSTANCES}; repetitions: {REPETITIONS}.",
        "The analysis uses instance-level paired factorial contrasts. A beta-distributed instance baseline supplies exchangeable heterogeneity. The four cell-specific test contrasts use conservative Holm alpha 0.0125; other contrasts use alpha 0.05.",
        "",
        "## Central scenario",
        "",
        "| Estimand | Alpha | Power at 20 pp | Power at 30 pp |",
        "|---|---:|---:|---:|",
    ]
    for name in CONTRASTS:
        r20 = next(r for r in central if r["estimand"] == name and r["target_risk_difference"] == 0.20)
        r30 = next(r for r in central if r["estimand"] == name and r["target_risk_difference"] == 0.30)
        lines.append(f"| {name.replace('_', ' ')} | {r20['alpha']:.4f} | {r20['power']:.3f} | {r30['power']:.3f} |")
    lines.extend(["", "## Classification at the frozen 20-point minimum effect", ""])
    for name, c in classifications.items():
        verdict = "adequately powered" if c["adequate_at_80_percent_in_all_scenarios"] else "underpowered / exploratory"
        lines.append(f"- {name.replace('_', ' ')}: {verdict}; sensitivity power {c['minimum_power_across_scenarios_at_20pp']:.3f}-{c['maximum_power_across_scenarios_at_20pp']:.3f}.")
    lines.extend([
        "",
        "This simulation is a design sensitivity analysis for the paired risk-difference estimands, not a claim about eventual observed effects. The mixed-effects logistic model remains the prespecified outcome model; interactions classified as underpowered are reported as exploratory with confidence intervals.",
    ])
    (out / "POWER_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
