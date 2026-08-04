# Chapter 5.4 GPT-5.6 Sol replacement manifest

This package replaces every table and figure in thesis Section 5.4 with results
from the frozen 456-attempt GPT-5.6 Sol factorial experiment. Tables 5.2-5.15,
plus supplemental Table 5.9a, are provided as CSV, Markdown, and LaTeX;
Figures 5.2-5.8 are provided as PNG, SVG, and PDF.

## Design-aware replacements

- The old architecture/context presentation is replaced by the frozen 2 x 2 x 2
  factors: grounding, control structure, and visible characterization-test feedback.
- Supplemental Table 5.9a preserves the Minimal/Structural/Relational/Full taxonomy
  and states its correspondence to the Sol binary-grounding factor. Relational and
  Full are explicitly marked not run; no Sol outcomes are imputed for them.
- Tables 5.9 and 5.10 now report characterization-test generation/admission and
  test-ON exposure fidelity; the retired four-level context factor is not fabricated.
- Table 5.12 evaluates ISO/IEC 25010 terminology only for iterative prompts, which
  explicitly elicited explanation and quality-impact prose. The frozen single-shot
  schema elicited only edited source and remediation, so it is not scored as a
  negative on an outcome it did not request.
- Tables 5.13-5.14 and Figure 5.6 use a mechanical, no-LLM post-run remeasurement
  of all 456 archived codebases with the pre-existing Layer 1/Layer 2 instrument.
  Archives were copied to isolated temporary workspaces and never modified.
- Figure 5.5 uses exact CC/WMC values extracted from all 456 frozen final-source
  artifacts. Figure 5.4 remains explicitly illustrative because factorial trajectory
  filenames collided across four iterative conditions.
- Figure 5.8 is added for the confirmatory visible-test main effect.

The canonical strict-success definition remains: final build passed, triggering
detector metric resolved, and private Layer 3 behavioral oracle passed.
