# Thesis figure regeneration manifest

Generated on 2026-07-28 from the frozen GPT-5.6 Sol confirmatory experiment in
`experiments/confirmatory-gpt56-sol-20260728`.

## GPT-5.6 Sol figures

| Figure | Status | Source |
|---|---|---|
| `fig1_h1c_2x2` | Regenerated | Canonical 456-attempt factorial results; strict success by grounding, control structure, and visible-test assignment |
| `fig2_h1c_interaction` | Regenerated | Same canonical factorial results; grounding × control interaction stratified by visible-test assignment |
| `fig3_ladder` | Regenerated | Mutually exclusive final gates: strict success, private regression, unresolved detector metric, or build failure |
| `fig4_grounding_main_effect` / `fig4_h2b_context` | Redesigned Sol replacement | Binary-grounding main effect pooled over control structure and visible-test assignment; the second name is a compatibility alias |
| `fig5_recall` / `agentic_recall` | Regenerated | Canonical final iterative traces; ungrounded agentic target recovery clustered by independent target |
| `fig6_ladder_by_grounding` / `fig6_ladder_by_context` | Redesigned Sol replacement | Strict-success gate composition pooled by binary-grounding assignment; the second name is a compatibility alias |
| `fig7_metric_trajectory_allocationcalculator` | Regenerated, illustrative | One surviving actual Sol trajectory: grounded iterative, visible test OFF, run 1 |
| `fig8_detector_resolution_by_arm` | New valid replacement | Detector-metric resolution by factorial arm |
| `fig9_repair_outcome_profile` / `fig9_quality_impact` | Redesigned Sol replacement | Detector resolution, private behavioral preservation, and strict success by arm; the second name is a compatibility alias |
| `fig10_layer3_behaviour` | Regenerated | Private Layer 3 behavioral preservation by factorial arm |
| `fig11_visible_test_effect` | Regenerated | Paired visible-characterization-test effect with cluster bootstrap interval |
| `fig5_1_e2e_architecture` | Current architecture figure | Model-independent pipeline architecture updated for characterization tests |

Every listed figure is provided as PNG, SVG, and PDF. Supporting source tables are
in `output/tables`.

## Original GPT-5.4 definitions retained for reference

The files under `legacy-gpt54/` preserve the original definitions and must not be
described as GPT-5.6 Sol results. Their top-level Sol replacements deliberately
use different valid outcomes:

- The old Figures 4 and 6 use a four-level context factor; the Sol replacements
  use the frozen binary-grounding factor.
- The old Figure 9 uses whole-solution `quality_delta`; the Sol replacement is
  explicitly titled “Repair outcome profile” because that delta was not persisted.

## Known trajectory limitation

The factorial campaign stored iterative trajectory files using source path and run
number, without the factorial condition in the artifact key. Four conditions
therefore reused each filename, leaving 57 trajectory files for 228 iterative
assignments. Canonical final run records, repair outputs, private-test outcomes,
and archived modified source trees are unaffected. However, full arm-level
per-iteration and exact metric-magnitude plots cannot be reconstructed honestly.
Figure 7 is explicitly illustrative, and Figure 8 reports the fully preserved
detector-resolution outcome instead.
