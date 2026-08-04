#!/usr/bin/env python3
"""Build the paste-ready Chapter 1, 4, and 5 thesis change set."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "thesis_restructure"
SEMANTIC_DIFF = OUT / "THESIS_CHAPTERS_1_4_5_SEMANTIC.diff"
RESULTS_SOURCE = OUT / "SECTION_5_4_RESTRUCTURED.md"
CHANGESET = OUT / "THESIS_CHAPTERS_1_4_5_PASTE_READY_CHANGESET.md"
VALIDATION = OUT / "THESIS_CHAPTERS_1_4_5_PASTE_READY_VALIDATION.json"


def normalise(text: str) -> str:
    text = text.strip()
    text = text.replace("**", "")
    text = text.replace(chr(96), "")
    text = text.replace("\u2014", "-").replace("\u2013", "-").replace("\u2011", "-")
    return text


def plus_hunk(source: str, start: str, end: str) -> str:
    chunk = source[source.index(start) : source.index(end)]
    lines = []
    in_editorial = False
    for line in chunk.splitlines()[1:]:
        if line.startswith("+["):
            in_editorial = True
            if line.rstrip().endswith("]"):
                in_editorial = False
            continue
        if in_editorial:
            if line.startswith("+") and line.rstrip().endswith("]"):
                in_editorial = False
            continue
        if line.startswith("+") and not line.startswith("+++"):
            lines.append(line[1:])
    return normalise("\n".join(lines))



def exact_edit(title: str, label: str, fallback: str) -> str:
    body_replacements = {
        "1.2 Problem Statement": ("1.2 Problem Statement", "1.3 Research Questions", None),
        "1.3 Research Questions": ("1.3 Research Questions", "1.4 Approach", None),
        "1.4 Approach": ("1.4 Approach", "1.5 Contributions", None),
        "1.5 Contributions": ("1.5 Contributions", "1.6 Outline", None),
        "1.6 Outline": ("1.6 Outline", "Chapter 2", None),
        "4.1 Research Design": ("4.1 Research Design", "4.2 Artefact Design", None),
        "4.2.2 Context Extraction": ("4.2.2 Context Extraction", "4.2.3 LLM-based explanation and repair", None),
        "4.2.3 LLM-based explanation and repair": ("4.2.3 LLM-based explanation and repair", "4.3 Data Collection", None),
        "4.3 Data Collection": ("4.3 Data Collection", "4.4 Experimental Design", None),
        "4.4.1 Confirmatory 2 x 2 x 2 factorial": (
            "4.4.1 Architecture comparison: Analyser-only, Hybrid, and Agentic",
            "4.4.2 Grounded-iterative configuration",
            "4.4.1 Confirmatory 2 x 2 x 2 factorial",
        ),
        "4.4.2 Planned secondary effects of grounding and control structure": (
            "4.4.2 Grounded-iterative configuration",
            "4.4.3 Context Level evaluation",
            "4.4.2 Planned secondary effects of grounding and control structure",
        ),
        "4.4.3 Supplementary four-level context experiment": (
            "4.4.3 Context Level evaluation",
            "4.5 Evaluation Metrics",
            "4.4.3 Supplementary four-level context experiment",
        ),
        "4.6 Planned statistical analysis": (
            "4.6 Planned statistical analysis",
            "4.7 Validation Strategy",
            None,
        ),
        "5.1.1 Architectural Overview": (
            "5.1.1 Architectural Overview",
            "5.1.2 Anti-pattern Detection",
            None,
        ),
        "5.1.3 Context extraction": (
            "5.1.3 Context extraction",
            "5.1.4 Prompt construction",
            None,
        ),
        "5.1.4 Prompt construction": (
            "5.1.4 Prompt construction",
            "5.1.5 LLM integration",
            None,
        ),
        "5.1.5 LLM integration": (
            "5.1.5 LLM integration",
            "5.1.6 Output structuring and storage",
            None,
        ),
        "5.1.7 Output structuring and storage": (
            "5.1.6 Output structuring and storage",
            "5.1.7 Design considerations",
            "5.1.7 Output structuring and storage",
        ),
        "5.1.8 Design considerations": (
            "5.1.7 Design considerations",
            "5.2 Experimental environment and setup",
            "5.1.8 Design considerations",
        ),
        "5.2.1 Experimental environment": (
            "5.2.1 Experimental environment",
            "5.2.2 Language Model Selection",
            None,
        ),
        "5.2.2 Language Model Selection": (
            "5.2.2 Language Model Selection",
            "5.2.3 Dataset: the constructed corpus",
            None,
        ),
        "5.2.3 Dataset": (
            "5.2.3 Dataset: the constructed corpus",
            "5.2.4 Ground Truth Construction",
            "5.2.3 Dataset",
        ),
        "5.2.5 Experimental Variables": (
            "5.2.5 Experimental Variables",
            "5.2.6 Prompt configuration",
            None,
        ),
        "5.2.6 Prompt configuration": (
            "5.2.6 Prompt configuration",
            "5.2.7 Experiment execution and result storage",
            None,
        ),
        "5.2.7 Experiment execution and result storage": (
            "5.2.7 Experiment execution and result storage",
            "5.3 System Validation and Testing",
            None,
        ),
        "5.3 System Validation and Testing": (
            "5.3 System Validation and Testing",
            "5.4 Technical Evaluation of the Hybrid Pipeline",
            None,
        ),
    }
    if title in body_replacements:
        current, following, renamed = body_replacements[title]
        steps = [
            f'1. Find the current heading "{current}".',
            f'2. Select all body text after that heading up to, but not including, the next heading "{following}".',
        ]
        if renamed:
            steps.append(f'3. Rename the current heading to "{renamed}".')
            steps.append("4. Replace the selected body text with the paste-ready text below. Do not paste the Markdown code fences.")
        else:
            steps.append("3. Keep the existing heading and replace only the selected body text with the paste-ready text below. Do not paste the Markdown code fences.")
        steps.append(f'5. Leave the following heading "{following}" and everything after it untouched.' if renamed else f'4. Leave the following heading "{following}" and everything after it untouched.')
        return "\n".join(steps)

    exact = {
        "1.1 Context": (
            '1. Find the final sentence of Section 1.1, ending with "within such systems [19]."\n'
            '2. Place the cursor after that sentence and before the heading "1.2 Problem Statement".\n'
            '3. Insert the paste-ready paragraph below. Keep the existing Section 1.1 text.'
        ),
        "1.5 Contributions, obsolete claims": (
            'No separate deletion is needed after completing "1.5 Contributions" above. '
            'Replacing the complete numbered list already removes the current identifier-groundedness and fabrication claims. '
            'Use this entry only as a check that those claims no longer remain elsewhere in Section 1.5.'
        ),
        "4.2.4 Generated characterisation tests": (
            '1. Find the end of the current Section 4.2.3, immediately before the heading "4.3 Data Collection".\n'
            '2. Insert a new heading, "4.2.4 Generated characterisation tests".\n'
            '3. Paste the text below under the new heading.\n'
            '4. Keep the existing heading "4.3 Data Collection" after the inserted subsection.'
        ),
        "4.4 Experimental Design, opening": (
            '1. Find the heading "4.4 Experimental Design".\n'
            '2. Select only the introductory text between that heading and "4.4.1 Architecture comparison: Analyser-only, Hybrid, and Agentic".\n'
            '3. Replace that introductory text with the paste-ready text below.\n'
            '4. Do not alter the 4.4 heading or the 4.4.1 subsection in this step.'
        ),
        "4.5 Evaluation Metrics, outcome definitions": (
            '1. Find the heading "4.5 Evaluation Metrics".\n'
            '2. Insert the paste-ready endpoint definitions immediately below that heading and before "4.5.1 Detection metrics".\n'
            '3. Keep Sections 4.5.1 to 4.5.3 unchanged in this step. Section 4.5.4 is removed separately below.'
        ),
        "4.5.4 Automated groundedness and fabrication": (
            '1. Find the heading "4.5.4 Automated groundedness and fabrication".\n'
            '2. Delete that heading and all text and tables beneath it up to, but not including, "4.5.5 Automated quality-attribute mention and alignment".\n'
            '3. Join Section 4.5.3 directly to Section 4.5.5. Do not renumber Sections 4.5.5 and 4.5.6 unless your university requires consecutive numbering.'
        ),
        "4.5.6 Behavioural preservation": (
            '1. Find the heading "4.5.6 Behavioural preservation".\n'
            '2. Replace only its opening paragraph, beginning "The two instruments above are static" and ending "the manner its change class warrants."\n'
            '3. Keep the following paragraphs beginning "Refactoring repairs", "Obsolete-API repairs", and "Relation to the verified-repair outcome".\n'
            '4. Review those retained paragraphs only for terminology consistency after inserting the new overview.'
        ),
        "4.7 Validation Strategy": (
            '1. Find the heading "4.7 Validation Strategy".\n'
            '2. Insert the three paste-ready paragraphs immediately under that heading, before the current paragraph beginning "The validity of the evaluation rests on the integrity of the constructed ground truth."\n'
            '3. Keep the existing two-layer corpus-verification protocol and Section 4.7.1 after the insertion.'
        ),
        "4.8 Threats to Validity": (
            'Paste the four paragraphs separately, not as one continuous block:\n'
            '1. Append the paragraph beginning "The supplementary experiment" to Section 4.8.1 Internal validity.\n'
            '2. Append the paragraph beginning "Strict success combines" to Section 4.8.2 Construct validity.\n'
            '3. Append the paragraph beginning "The constructed corpus" to Section 4.8.3 External validity.\n'
            '4. Append the paragraph beginning "The confirmatory factorial" to Section 4.8.4 Conclusion validity.\n'
            '5. Keep Section 4.8.5 Reliability unchanged.'
        ),
        "Chapter 5 opening": (
            '1. Find the single paragraph directly below the chapter title "Experiments & Results", beginning "This chapter reports the detection results".\n'
            '2. Replace that paragraph only with the paste-ready paragraph below.\n'
            '3. Keep the chapter title and the heading "5.1 System implementation and architecture".'
        ),
        "5.1 System implementation and architecture": (
            '1. Find the heading "5.1 System implementation and architecture".\n'
            '2. Select only the introductory paragraph beneath it, ending "without breaking the experimental workflow."\n'
            '3. Replace that paragraph with the paste-ready paragraph below.\n'
            '4. Keep the heading and Section 5.1.1.'
        ),
        "Figure 5.1": (
            '1. Select the current Figure 5.1 image and its caption, ending "objective-primary evaluation."\n'
            '2. Replace the image with output/figures/fig5_1_e2e_architecture.png, or the SVG/PDF variant required by the thesis source.\n'
            '3. Replace the old caption with the paste-ready caption below.\n'
            '4. Keep the paragraph after the figure, beginning "Each stage is designed to operate independently".'
        ),
        "5.1.2 Anti-pattern Detection": (
            '1. Find Table 5.1 and the sentence immediately after it, ending "the derivation is in §4.5.1."\n'
            '2. Insert the paste-ready paragraph after that sentence and before "5.1.3 Context extraction".\n'
            '3. Keep the existing detector implementation text and Table 5.1.'
        ),
        "5.1.6 Generated characterisation-test stage": (
            '1. Find the end of Section 5.1.5, immediately before the current heading "5.1.6 Output structuring and storage".\n'
            '2. Insert a new heading, "5.1.6 Generated characterisation-test stage", followed by the paste-ready text below.\n'
            '3. Renumber the current 5.1.6 to 5.1.7 and the current 5.1.7 to 5.1.8. Their replacement text is supplied in the next two entries.'
        ),
        "5.2.4 Ground Truth Construction": (
            '1. Find the final paragraph of Section 5.2.4, ending "stored with the same applied source state."\n'
            '2. Insert the paste-ready paragraph after it and before "5.2.5 Experimental Variables".\n'
            '3. Keep the existing truth-record field description.'
        ),
        "Figure 5.1, obsolete content": (
            'No separate deletion is needed after replacing Figure 5.1 above. '
            'Use this entry as a check that the replacement image contains no analyser-only branch, old Hybrid or Agentic arm labels, first-build-derived state, or human explanation-evaluation box.'
        ),
        "5.4 Technical Evaluation": (
            '1. Find the current heading "5.4 Technical Evaluation of the Hybrid Pipeline".\n'
            '2. Select that heading and everything beneath it through the end of Section 5.4, stopping before the next chapter heading.\n'
            '3. Replace the complete selection with the paste-ready Section 5.4 below. This block already contains the new 5.4 heading and all subsection headings.\n'
            '4. Remove the old GPT-5.4 tables and figures with the selected text, then insert the referenced regenerated tables and Figures 5.2 to 5.9 at the marked positions in the new section.'
        ),
        "5.4 obsolete results": (
            'No separate deletion is needed after completing the full Section 5.4 replacement above. '
            'Use this entry only as a final search check that the old 42.2%, 21.1%, and 53.3% results, first-build comparisons, unfinished groundedness table, StatementBuilder account, and GPT-5.4 figures are absent.'
        ),
    }
    return exact.get(title, fallback)

def entry(
    title: str,
    label: str,
    boundary: str,
    text: str | None = None,
) -> str:
    result = [f"## {title}", "", f"### {label}", "", "Exact edit instructions:", "", exact_edit(title, label, boundary)]
    if text:
        result.extend(["", "Paste-ready text:", "", "```text", normalise(text), "```"])
    return "\n".join(result)


def build() -> str:
    diff = SEMANTIC_DIFF.read_text(encoding="utf-8")

    chapter1 = []
    chapter1.append("# Chapter 1")
    chapter1.append(
        entry(
            "1.1 Context",
            "ADDED",
            "Insert at the end of Section 1.1.",
            """
For LLM-assisted remediation, a detector-resolving edit is insufficient on its
own. The resulting program must build and preserve the behaviour on which its
users depend.
""",
        )
    )
    chapter1.append(
        entry(
            "1.2 Problem Statement",
            "CHANGED",
            "Replace the paragraphs beginning \"It remains unclear\" and "
            "\"This thesis compares\".",
            """
The system studied in this thesis combines static analysis and an LLM within one
repair workflow. Static analysis supplies a reproducible diagnosis, target
location, and triggering evidence. The LLM interprets that evidence and produces
the source-code repair. This division of work permits measurement of the complete
repair outcome and of the contribution made by detector-derived grounding.

It remains unclear whether detector-derived grounding improves functionally
validated repair, whether iterative compiler-and-test feedback improves on an
independently executed single-shot repair, and whether an LLM-generated
characterisation test can reduce regression when it is created before repair and
made visible to the repair model. A further question is whether broader detector
context improves repair beyond a concise target diagnosis.

Detector resolution alone is insufficient evidence of correctness. A repair can
cross a static threshold while failing to build, changing externally observable
behaviour, or introducing quality problems elsewhere in the solution. Generated
tests cannot serve as their own independent correctness oracle because the same
model family participates in constructing the intervention. The evaluation
requires a hidden, author-written behavioural oracle in addition to build and
detector gates.

This thesis evaluates direct-editing repair in a controlled 2 x 2 x 2 factorial:
static-analysis grounding supplied or withheld, independent single-shot or
iterative control, and an LLM-generated characterisation test visible or
withheld. A separate matched supplement evaluates Minimal, Structural,
Relational, and Full context in the original Hybrid
suggestion-plus-strict-literal-applier pipeline. The experiments are reported
separately because they use different repair mechanisms and analysis
populations.
""",
        )
    )
    chapter1.append(
        entry(
            "1.3 Research Questions",
            "CHANGED",
            "Replace the complete current research-question block.",
            """
The main research question is:

To what extent can a repair pipeline that combines static analysis with an LLM
resolve detected anti-patterns while producing buildable code and preserving
existing behaviour?

The main question is operationalised through the following research questions:

RQ1, technical and functional repair success. Within the combined
static-analysis and LLM pipeline, to what extent do repair attempts achieve
strict success, defined as a successful build, resolution of the triggering
detector condition, and a pass on the private behavioural oracle?

RQ1.1, visible characterisation tests. What is the average effect of making a
pre-repair, LLM-generated characterisation test visible to the repair model on
strict repair success?

RQ2, grounding and control. What effect does supplying the static-analysis
diagnosis have on strict repair success, and what effect does iterative control
have?

RQ3, context granularity. In the original Hybrid suggestion-plus-applier
mechanism, does verified repair vary when detector-derived context increases
from Minimal through Structural and Relational to Full?

RQ4, multi-layer repair quality. After repair, what changes are observed in
triggering metrics, whole-solution detector and CodeAnalyzer diagnostics,
independent private behaviour, and computational cost?

The visible-test effect in RQ1.1 is the confirmatory estimand. Grounding and
iteration in RQ2 are planned secondary estimands. The four-level comparison in
RQ3 is a separately frozen supplementary experiment. Cell-specific visible-test
effects and interactions are exploratory. Computational cost is a secondary
resource outcome and is not part of RQ1 or strict success.
""",
        )
    )
    chapter1.append(
        entry(
            "1.4 Approach",
            "CHANGED",
            "Replace the current pipeline-stage and architecture paragraphs.",
            """
The instrument combines Roslyn-based static analysis with LLM-based source-code
repair. It has five experimentally relevant stages. First, Roslyn detects and
localises anti-patterns and records their triggering evidence. Second, the
pipeline constructs either neutral target coordinates, a Structural finding, or
one of four nested context payloads. Third, before any confirmatory repair, a
separate diagnosis-blind model call attempts to generate an immutable
characterisation test of the pristine behaviour. Fourth, gpt-5.6-sol repairs the
source under independently crossed grounding, control-structure, and
visible-test conditions. Fifth, the sealed final state is evaluated through a
build gate, detector remeasurement, a hidden author-written behavioural oracle,
independent whole-solution diagnostics, and resource accounting.

The confirmatory experiment crosses eight independently executed direct-editing
conditions. Iterative conditions may receive compiler and visible-test feedback,
but never detector or private-oracle feedback. Each single-shot condition has
its own one-call execution, independently of the iterative trajectories.

The four-level supplement retains the original Hybrid mechanism. The evaluated
model produces a recommendation and a fixed DeepSeek-V4-Pro applier attempts to
implement it under a strict-literal contract. The applier is held constant
across supplementary assignments and is considered as a source of confounding.
""",
        )
    )
    chapter1.append(
        entry(
            "1.5 Contributions",
            "CHANGED",
            "Replace the complete numbered contribution list.",
            """
1. An empirical assessment of a combined static-analysis and LLM repair
pipeline. The thesis records whether each final program builds, resolves the
triggering detector condition, and passes an independent private behavioural
oracle. The confirmatory treatment estimates the target-clustered
intention-to-treat effect of a characterisation test generated before repair and
made visible to the repair model.

2. An independently executed static-analysis-grounding-by-control ablation. A
crossed direct-editing design separates the effect of supplying a detector
diagnosis from the effect of iterative feedback; single-shot outcomes are not
derived from iterative trajectories.

3. A supplementary matched context-granularity experiment. The thesis compares
Minimal, Structural, Relational, and Full detector context under a frozen Hybrid
suggestion-plus-applier mechanism and reports both effectiveness and context
cost.

4. A multi-layer operationalisation of repair correctness. Strict success
requires a build, resolution of the triggering detector condition, and a pass on
an independently authored private behavioural oracle. Whole-solution
diagnostics and triggering-metric reductions remain separate outcomes.

5. A reproducible experimental package. Frozen manifests, prompts, model
configuration, generated-test artefacts, assignment traces, archived final
codebases, measurements, token counts, and analysis inputs support audit and
replication.

6. A bounded empirical account of the treatment effects. The thesis
distinguishes confirmatory, planned-secondary, exploratory, and supplementary
evidence and reports null findings and limitations alongside positive effects.
""",
        )
    )
    chapter1.append(
        entry(
            "1.5 Contributions, obsolete claims",
            "DELETED",
            "Delete the separate contributions claiming completed identifier "
            "groundedness and fabrication inference. Retain ISO/IEC 25010 lexical "
            "coverage only as a secondary descriptive measure.",
        )
    )
    chapter1.append(
        entry(
            "1.6 Outline",
            "CHANGED",
            "Replace the current outline paragraph.",
            """
Chapter 2 presents the background on software quality, anti-patterns, static
analysis, and large language models. Chapter 3 reviews related work and defines
the empirical gap. Chapter 4 describes the research design, the confirmatory
factorial, the supplementary context experiment, and the evaluation instruments.
Chapter 5 documents the implementation, validation, and experimental results.
Chapter 6 interprets the findings and discusses their implications and
limitations. Chapter 7 concludes the thesis and identifies directions for
replication.
""",
        )
    )

    chapter4 = ["# Chapter 4"]
    custom_chapter4 = {
        "4.4.3 Supplementary four-level context experiment": """
RQ3 examines whether increasing the quantity and relational scope of
static-analysis context changes verified repair in the original Hybrid
suggestion-plus-applier pipeline. This supplementary experiment includes all 30
frozen corpus targets: ten God Class, ten Long Method, and ten Obsolete API
Usage instances. Each target is evaluated once at each of four context levels,
yielding 120 matched assignments. Every assignment begins from a pristine
source state. Visible generated tests are disabled throughout this experiment.

The four context levels are nested. Minimal contains the anti-pattern label and
the detector-extracted code fragment. Structural adds the symbol, file and line
location, severity, triggering metrics, and thresholds. Relational adds an
enclosing-member summary and a surrounding source window. Full adds frozen
project, framework, and domain metadata. Each corpus target occupies a unique
source file, so Full contains no co-located finding and differs from Relational
only through project-level metadata.

gpt-5.6-sol generates one explanation and repair recommendation for each
assignment. A fixed DeepSeek-V4-Pro deployment subsequently attempts to apply
the recommendation under a strict-literal contract. The applier is held
constant and is not an experimental factor. An applied state is built and
remeasured by the detector. Failed generation, parsing, application, build, or
detector resolution remains in the assigned denominator, and no retry is made.

The primary analysis uses the matched global comparison of verified repair
across all four levels. The prespecified adjacent contrast between Structural
and Minimal is the primary pairwise comparison. The remaining adjacent
contrasts are secondary. Private Layer 3, whole-solution diagnostics, lexical
coverage, and resource use are reported as secondary outcomes. Target blocks
and context order use randomisation seed 20260728. Because each target-context
cell is observed once, the supplement cannot estimate within-cell generation
variability and remains separate from the confirmatory factorial.
""",
        "4.6 Planned statistical analysis": """
All binary arm outcomes are reported as proportions with Wilson confidence
intervals. The confirmatory factorial is analysed at target level because each
of the 19 targets appears in every treatment condition and the three repetitions
within a target are not independent experimental units. For each main effect,
strict-success proportions are first averaged within target and treatment
level. The estimand is the mean target-paired absolute risk difference. A
clustered confidence interval and an exact target-level sign-flip test are
reported.

The visible-test main effect is the confirmatory contrast. Grounding and control
structure are planned secondary contrasts. Cell-specific visible-test effects
and interactions are exploratory and are adjusted with Holm correction within
their reported family. A binomial generalised linear mixed model with target
random intercepts is used as a sensitivity analysis, with grounding, control
structure, visible-test access, and their interactions as fixed effects.
Disagreement between the paired analysis and the model-based sensitivity
analysis is reported without selecting the more favourable result.

The supplementary four-level experiment uses Cochran Q for the matched global
comparison and exact paired McNemar tests for prespecified pairwise contrasts,
with Holm correction. Target-block bootstrap intervals are reported for paired
differences. Per-pattern results are descriptive because each pattern stratum
contains ten targets and only one observation per target-context cell.
Confirmatory and supplementary denominators are never pooled.
""",
        "4.7 Validation Strategy": """
Before repair, the study froze the corpus revision, target manifest, detector
configuration, prompt families, model deployment, generated-test artefacts,
private behavioural oracle, iteration budget, randomisation seeds, and analysis
plan. Pre-run validation checked pristine builds, target inclusion, treatment
isolation, context nesting, generated-test admission, and the absence of private
or detector-result leakage into model-visible feedback.

Every prompt, response, source transition, build outcome, visible-test result,
and usage record was stored in an append-only trace. Final codebases and unified
diffs were archived with checksums. Post-repair validation checked assignment
completion, independent single-shot execution, iteration limits, source-state
reconstruction, and consistency between traces and sealed final states.

Detector remeasurement, private behavioural testing, and whole-solution
analysis were performed only after each final repair state had been sealed.
Their results were withheld from all repair calls. This separation preserved
the distinction between intervention feedback and independent outcome
measurement.
""",
    }
    for section_title, label, boundary, start, end in [
        (
            "4.1 Research Design",
            "CHANGED",
            "Replace the paragraphs that describe the old architecture and "
            "three-run context comparisons.",
            "@@ 4.1 Research Design @@",
            "@@ 4.2.2 Context Extraction @@",
        ),
        (
            "4.2.2 Context Extraction",
            "CHANGED",
            "Replace the paragraph that treats the four context levels as the "
            "only independent variable.",
            "@@ 4.2.2 Context Extraction @@",
            "@@ 4.2.3 LLM-based explanation and repair @@",
        ),
        (
            "4.2.3 LLM-based explanation and repair",
            "CHANGED",
            "Replace the current single-template and three-runs description.",
            "@@ 4.2.3 LLM-based explanation and repair @@",
            "@@ 4.2.4 Generated characterisation tests [new subsection] @@",
        ),
        (
            "4.2.4 Generated characterisation tests",
            "ADDED",
            "Insert after Section 4.2.3.",
            "@@ 4.2.4 Generated characterisation tests [new subsection] @@",
            "@@ 4.3 Data Collection @@",
        ),
        (
            "4.3 Data Collection",
            "CHANGED",
            "Replace the old 30 x 4 x 3 denominator paragraph and add the "
            "confirmatory inclusion and exclusion rules.",
            "@@ 4.3 Data Collection @@",
            "@@ 4.4 Experimental Design @@",
        ),
        (
            "4.4 Experimental Design, opening",
            "CHANGED",
            "Replace the introductory architecture-comparison paragraphs before "
            "Section 4.4.1.",
            "@@ 4.4 Experimental Design @@",
            "@@ 4.4.1 Architecture comparison: Analyser-only, Hybrid, and Agentic @@",
        ),
        (
            "4.4.1 Confirmatory 2 x 2 x 2 factorial",
            "CHANGED",
            "Replace the entire old Section 4.4.1, including the analyser-only, "
            "Hybrid, Agentic, H1a, and first-build design discussion.",
            "@@ 4.4.1 Architecture comparison: Analyser-only, Hybrid, and Agentic @@",
            "@@ 4.4.2 Grounded-iterative configuration @@",
        ),
        (
            "4.4.2 Planned secondary effects of grounding and control structure",
            "CHANGED",
            "Replace the entire old Section 4.4.2, including the old H1b and "
            "first-build decomposition.",
            "@@ 4.4.2 Grounded-iterative configuration @@",
            "@@ 4.4.3 Context Level evaluation @@",
        ),
        (
            "4.4.3 Supplementary four-level context experiment",
            "CHANGED",
            "Replace the entire old Section 4.4.3.",
            "@@ 4.4.3 Context Level evaluation @@",
            "@@ 4.5 Evaluation Metrics @@",
        ),
        (
            "4.5 Evaluation Metrics, outcome definitions",
            "CHANGED",
            "Replace the opening repair-outcome definition.",
            "@@ 4.5 Evaluation Metrics @@",
            "@@ 4.5.4 Automated groundedness and fabrication @@",
        ),
        (
            "4.5.6 Behavioural preservation",
            "CHANGED",
            "Replace the current behavioural-preservation overview. Retain any "
            "subsequent technical detail that is consistent with this distinction.",
            "@@ 4.5.6 Behavioural preservation @@",
            "@@ 4.6 Planned statistical analysis @@",
        ),
        (
            "4.6 Planned statistical analysis",
            "CHANGED",
            "Replace the old architecture and three-run context analysis.",
            "@@ 4.6 Planned statistical analysis @@",
            "@@ 4.7 Validation Strategy @@",
        ),
        (
            "4.7 Validation Strategy",
            "ADDED",
            "Add to the opening of Section 4.7 before the detailed validation "
            "procedures.",
            "@@ 4.7 Validation Strategy @@",
            "@@ 4.8 Threats to Validity @@",
        ),
    ]:
        chapter4.append(
            entry(
                section_title,
                label,
                boundary,
                custom_chapter4.get(section_title, plus_hunk(diff, start, end)),
            )
        )
        if section_title == "4.5 Evaluation Metrics, outcome definitions":
            chapter4.append(
                entry(
                    "4.5.4 Automated groundedness and fabrication",
                    "DELETED",
                    "Delete the complete subsection and its unfinished result table. "
                    "Identifier groundedness and fabrication were not completed as frozen "
                    "inferential outcomes.",
                )
            )
    chapter4.append(
        entry(
            "4.8 Threats to Validity",
            "ADDED",
            "Add the following paragraph and limitations to the relevant internal, "
            "construct, conclusion, and external validity subsections.",
            """
The confirmatory factorial contains 19 independent targets, which limits
interaction inference even though every target appears in all eight conditions.
Two generated suites were unavailable. Their test-ON assignments remain in the
intention-to-treat analysis.

The supplementary experiment introduces a second model at the application
stage. The fixed strict-literal applier can attenuate or amplify differences
between recommendations. One repetition per target-context cell prevents
estimation of within-cell generation variability. Full context adds project
metadata only because no target file contains a co-located finding.

Strict success combines buildability, detector resolution, and a private
behavioural pass. It remains bounded by detector construct validity and the
coverage of the authored private suite. Obsolete API Usage uses a smoke oracle
instead of behavioural equivalence. Threshold crossing is not equivalent to an
architectural improvement.

The constructed corpus, one evaluated deployment, and one bounded execution
period limit external validity. Replication on organically evolved systems,
other model deployments, and a larger number of independent targets is required
before generalising the treatment effects.
""",
        )
    )

    chapter5 = ["# Chapter 5"]
    chapter5.append(
        entry(
            "Chapter 5 opening",
            "CHANGED",
            "Replace the opening paragraph of Chapter 5.",
            plus_hunk(diff, "@@ Chapter 5 opening @@", "@@ 5.1 System implementation and architecture @@"),
        )
    )
    chapter5.append(
        entry(
            "5.1 System implementation and architecture",
            "CHANGED",
            "Replace the opening paragraph of Section 5.1.",
            plus_hunk(
                diff,
                "@@ 5.1 System implementation and architecture @@",
                "@@ 5.1.1 Architectural Overview @@",
            ),
        )
    )
    chapter5.append(
        entry(
            "5.1.1 Architectural Overview",
            "CHANGED",
            "Replace the current four-stage architecture overview.",
            """
The system begins with a frozen pristine corpus and Roslyn detector output. For
the confirmatory experiment, a diagnosis-blind test generator runs before repair
and produces an immutable candidate characterisation test. The assignment then
selects grounding OFF or ON, independent single-shot or iterative control, and
visible test OFF or ON. Every final state is evaluated for buildability,
triggering-detector resolution, private behaviour, whole-solution diagnostics,
and resource use.

For the supplementary experiment, the detector constructs one of four nested
context payloads. gpt-5.6-sol generates an explanation and repair
recommendation, after which the fixed DeepSeek-V4-Pro applier attempts to
materialise the recommendation under a strict-literal contract. The
confirmatory and supplementary paths share detector and measurement
infrastructure but retain separate repair mechanisms and denominators.
""",
        )
    )
    chapter5.append(
        entry(
            "Figure 5.1",
            "CHANGED",
            "Replace the old architecture figure and caption.",
            """
Figure 5.1: End-to-end experimental architecture. Detector output is routed to
the repair-grounding branch and, through neutral target coordinates only, to the
pre-repair characterisation-test generator. Confirmatory conditions cross
grounding, control structure, and visible-test access. Private behavioural tests
and detector remeasurement remain hidden until final evaluation. The separately
frozen four-level Hybrid supplement is reported outside the factorial. Human
output evaluation is absent from the executed study.
""",
        )
    )
    chapter5.append(
        entry(
            "5.1.2 Anti-pattern Detection",
            "ADDED",
            "Insert after Table 5.1 and retain the existing detector implementation.",
            """
The detector has three roles in the experiment. It admits and localises corpus
targets, supplies the Structural finding to grounded conditions, and remeasures
the triggering condition after repair. Ungrounded conditions receive the same
neutral target coordinates but not the diagnosis, severity, thresholds, or
metric values. Final detector results are withheld from every repair condition.
""",
        )
    )
    chapter5.append(
        entry(
            "5.1.3 Context extraction",
            "CHANGED",
            "Replace the current four-level-only description.",
            """
The confirmatory factorial uses a binary grounding construction. Ungrounded
payloads contain the complete pristine source and neutral file, symbol, and
declaration coordinates. Grounded payloads contain the same information plus the
Structural detector finding: anti-pattern label, location, severity, triggering
metrics, and thresholds. Keeping neutral coordinates constant prevents target
localisation from becoming an additional treatment.

The supplementary experiment uses four nested payloads. Minimal contains the
anti-pattern label and detector-extracted code fragment. Structural adds symbol,
file and line location, severity, metrics, and thresholds. Relational adds an
enclosing-member summary and surrounding source window. Full adds frozen
project, framework, and domain metadata. Every target occupies a unique source
file, so the Full payload contains no co-located findings.
""",
        )
    )
    chapter5.append(
        entry(
            "5.1.4 Prompt construction",
            "CHANGED",
            "Replace the current single-template description.",
            """
Prompt families are versioned separately by experimental role. The
test-generation prompt receives pristine production code, the fixed test-project
skeleton, and neutral target coordinates. It receives no detector diagnosis,
truth record, private test, reference repair, or generated edit.

Confirmatory repair prompts vary through their assigned grounding,
control-structure, and visible-test treatments. Single-shot prompts request one
production edit. Iterative prompts define the six-call budget and the compiler
and visible-test feedback available after each attempted state. Supplementary
prompts share an output schema while varying the four nested context payloads.
The strict-literal applier uses a separately frozen prompt and may not invent
unspecified design decisions.
""",
        )
    )
    chapter5.append(
        entry(
            "5.1.5 LLM integration",
            "CHANGED",
            "Replace the current GPT-family, compiler-only loop, and Claude-applier "
            "description.",
            """
The evaluated deployment is gpt-5.6-sol through Azure OpenAI. Confirmatory
single-shot and iterative conditions edit production source directly. Iterative
conditions receive build feedback and, in test-ON cells with an admitted suite,
visible-test execution feedback. Detector and private-oracle results are never
exposed. The iteration budget is six model calls.

The supplementary experiment uses gpt-5.6-sol to generate the recommendation
and a fixed DeepSeek-V4-Pro deployment for strict-literal application. The
applier is not an evaluated factor. Its influence is considered in the
supplementary threats to validity.
""",
        )
    )
    chapter5.append(
        entry(
            "5.1.6 Generated characterisation-test stage",
            "ADDED",
            "Insert after Section 5.1.5 and renumber the existing Sections 5.1.6 "
            "and 5.1.7.",
            """
One test-generation call is made for each of the 19 confirmatory targets before
any repair. Admission requires successful schema parsing and compilation, two
passes on the pristine system, invocation of production code, and a non-vacuous
assertion. Tests that depend on network access, uncontrolled randomness,
wall-clock assumptions, or mutable external state are rejected. An admitted
artefact is immutable, and a failed artefact is not regenerated.

The pipeline records the generation status, admission reason, source hash,
baseline executions, and test-ON exposure. An unavailable test does not alter
the assigned treatment. The observation remains in its test-ON cell under the
intention-to-treat policy.
""",
        )
    )
    chapter5.append(
        entry(
            "5.1.7 Output structuring and storage",
            "CHANGED",
            "Renumber the old Section 5.1.6 and replace its field summary.",
            """
Each assignment record stores its target and repetition identifiers, treatment
levels, pristine-source hash, prompt and response hashes, generated-test
reference, per-iteration edits, build outcomes, visible-test feedback, final
source reference, strict-success components, private outcome, whole-solution
diagnostics, model calls, token use, duration, and nominal cost. Raw responses
and parsed fields are retained together.

Failed, unapplicable, unavailable-test, parse-error, build-failing, and
detector-unresolved outcomes remain in the experiment records. Complete final
codebases, unified diffs, assignment metadata, and checksums are archived for
later inspection.
""",
        )
    )
    chapter5.append(
        entry(
            "5.1.8 Design considerations",
            "CHANGED",
            "Renumber the old Section 5.1.7 and replace its design summary.",
            """
Experimental isolation is maintained through pristine starting states,
immutable generated-test artefacts, independent single-shot execution, fixed
prompts and budgets, blocked randomisation, hidden final oracles, append-only
traces, and sealed post-repair evaluation. These controls address specified
sources of variation but do not remove deployment-side nondeterminism or the
limitations of the constructed corpus.
""",
        )
    )
    chapter5.append(
        entry(
            "5.2.1 Experimental environment",
            "CHANGED",
            "Replace the current general reproducibility paragraph.",
            """
The pipeline was executed in the frozen .NET and Roslyn environment recorded in
the experiment manifests, with Azure OpenAI providing model inference and Python
providing the sealed downstream analysis. The pipeline revision, corpus
revision, model-visible corpus hash, detector configuration, prompt versions,
timeouts, iteration budget, and randomisation seeds were fixed before their
respective campaigns.

Every repair began from the same pristine corpus state. Confirmatory assignments
used randomisation seed 503999552; supplementary target blocks and context order
used seed 20260728. Append-only ledgers record calls, completion, token use, and
trace hashes. The final source states can be reconstructed from the archived
codebases and checksums.
""",
        )
    )
    chapter5.append(
        entry(
            "5.2.2 Language Model Selection",
            "CHANGED",
            "Replace the current generic frontier-model and Claude-applier text.",
            """
The evaluated model is gpt-5.6-sol, accessed through the configured Azure OpenAI
deployment in every confirmatory and supplementary evaluated-model call.
Holding the deployment constant removes cross-model variation from the
treatment contrasts, although the results cannot be assumed to apply to other
models or future deployment versions.

The confirmatory factorial uses direct editing and has no external repair
applier. The supplement holds DeepSeek-V4-Pro constant as a non-evaluated
strict-literal applier. Nominal cost uses the frozen Standard Global prices of
$5.00 per million input tokens and $30.00 per million output tokens. These rates
are accounting assumptions for the experiment.
""",
        )
    )
    chapter5.append(
        entry(
            "5.2.3 Dataset",
            "CHANGED",
            "Replace the paragraph that implies co-located seeded findings and add "
            "the separate analysis populations.",
            """
The frozen corpus contains five independently compilable .NET solutions, 61
files, and 30 detector-confirmed targets: ten God Class, ten Long Method, and ten
Obsolete API Usage instances. Thirty target files contain one seeded finding
each; the remaining files are controls or near-miss distractors. The unique-file
layout means that Full supplementary context contains no co-located finding.

The confirmatory population contains ten God Class and nine Long Method targets.
LM-01 is excluded because it was used in end-to-end shakedowns before the
confirmatory freeze. Obsolete API Usage is excluded because the intended
migration changes behaviour, making equality with deprecated behaviour an
invalid characterisation criterion. The supplementary experiment includes all
30 targets.
""",
        )
    )
    chapter5.append(
        entry(
            "5.2.4 Ground Truth Construction",
            "ADDED",
            "Insert after the current truth-record field description.",
            """
The author-written private suite forms a separate behavioural oracle. It is
derived exclusively from the pristine corpus, admitted on the baseline, frozen
before repair outcomes are inspected, and hidden from every model-visible
surface. God Class and Long Method use behavioural equivalence over exercised
public behaviour. Obsolete API Usage uses a fixed-input smoke oracle because a
correct migration may intentionally change deprecated behaviour. Generated
visible tests and private tests have separate storage, terminology, and
experimental roles.
""",
        )
    )
    chapter5.append(
        entry(
            "5.2.5 Experimental Variables",
            "CHANGED",
            "Replace the entire current subsection.",
            """
The confirmatory factors are grounding (OFF or ON), repair control structure
(independent single-shot or iterative), and visible generated test (OFF or ON).
Nineteen independent targets are observed in three repetitions across eight
cells, yielding 456 intention-to-treat assignments.

The confirmatory primary endpoint is strict success:

strict_success =
    build_passed AND detector_resolved AND private_oracle_passed

The visible-test main effect is confirmatory. Grounding and control-structure
main effects are planned secondary estimands. Cell-specific visible-test effects
and interactions are exploratory. Secondary outcomes include target recovery,
the repair ladder, triggering-metric reduction, whole-solution diagnostics,
visible-test process measures, and resource use.

The supplementary experiment has one matched four-level context factor, 30
targets, and one repetition, yielding 120 evaluated-model calls and at most 120
applier calls. Its primary endpoint is verified repair:

verified_repair =
    strict_literal_application AND build_passed AND detector_resolved

Private Layer 3 is secondary in the supplement because Obsolete API Usage uses a
smoke oracle. The confirmatory and supplementary denominators remain separate.
""",
        )
    )
    chapter5.append(
        entry(
            "5.2.6 Prompt configuration",
            "CHANGED",
            "Replace the current single-template subsection.",
            """
The experiment uses frozen, role-specific prompt families. Within each
estimand, non-treatment content is held constant. The families cover
diagnosis-blind test generation, grounded and ungrounded direct editing,
single-shot and iterative control, visible-test insertion, four-level Hybrid
recommendations, and strict-literal application. Prompt identifiers and hashes
are stored in the frozen experiment packages.
""",
        )
    )
    chapter5.append(
        entry(
            "5.2.7 Experiment execution and result storage",
            "CHANGED",
            "Replace the current field-list-only subsection.",
            """
For each assignment, the controller restores pristine source, loads the frozen
treatment and generated-test artefact, executes the assigned repair contract
without retry, and archives the final source state. Detector remeasurement,
private Layer 3, and whole-solution analysis run after the repair state is
sealed. Tables and figures are derived from the sealed source data.

The confirmatory and supplementary experiments have separate manifests,
ledgers, freeze records, post-repair seals, private-result packages, and final
checksums. Completion or failure does not remove an assignment from its
prespecified denominator.
""",
        )
    )
    chapter5.append(
        entry(
            "5.3 System Validation and Testing",
            "CHANGED",
            "Replace the complete current Section 5.3 with the following text and "
            "subsections.",
            """
The experimental instrument was validated before the technical evaluation.
Validation covered the detector, context construction, prompt treatments,
generated-test admission, model execution, source-state reconstruction, hidden
evaluation, and storage. Its purpose was to establish that the recorded
treatments and outcomes corresponded to the frozen protocol.

5.3.1 Validation scope

Validation was divided into pre-run, post-repair, and post-private phases. The
pre-run phase checked corpus and pipeline hashes, target inclusion, factorial
assignments, prompt versions, model configuration, pristine builds, generated
tests, and feedback boundaries. The post-repair phase checked campaign
completion, append-only ledgers, call counts, source archives, diffs, and sealed
hashes. The post-private phase checked that Layer 3 and whole-solution rescoring
were applied only to sealed final states.

5.3.2 Detection validation

The configured God Class, Long Method, and Obsolete API Usage rules were checked
against the corpus truth records, source locations, and triggering values.
Controls and near-miss distractors supplied the false-positive check. The
perfect constructed-corpus detection result is treated as a manipulation check
because the same detector definitions admit and remeasure targets. Corpus review
occurred before model execution and did not evaluate LLM output.

5.3.3 Context extraction validation

For the confirmatory factorial, validation established that grounded and
ungrounded assignments received identical pristine source and neutral target
coordinates. Diagnosis fields occurred only in grounded payloads. For the
supplement, the four payloads were checked for the specified nesting from
Minimal to Full. Full contained frozen project metadata and no co-located
finding because each target occupied a unique file.

5.3.4 Prompt and generated-test validation

The prompt audit checked role-specific schemas and treatment isolation. The
test-generation prompt contained neutral coordinates but no anti-pattern label,
diagnosis, metrics, thresholds, private test, truth record, reference repair, or
generated edit. Detector remeasurement and private results were absent from
iterative feedback.

Nineteen test-generation calls produced nineteen immutable artefacts. Seventeen
were admitted; one failed to build and one failed against the pristine
baseline. No failed artefact was regenerated. Admitted tests compiled and passed
twice on the pristine corpus, invoked production code, and contained a
non-vacuous assertion.

5.3.5 LLM execution validation

End-to-end shakedowns verified model invocation, direct editing, compiler
feedback, visible-test feedback, parsing, and source restoration. LM-01 was
excluded from the confirmatory population because it had been exercised before
the freeze. The main campaign used the frozen gpt-5.6-sol configuration. API,
parse, build, application, and test failures remained recorded outcomes and
were not retried.

5.3.6 Output and archive validation

The confirmatory manifest contained 456 independent assignments and all
completed. The supplementary manifest contained 120 assignments and all
completed. Records were checked for treatment levels, paired target and
repetition keys, test exposure, final source references, strict-success
components, private outcomes, whole-solution diagnostics, and usage. Archived
codebases were reconstructed and checked against their recorded checksums.

5.3.7 Validation outcome

The validation established an auditable link between frozen assignments, model
calls, final source states, and derived measurements. It does not establish
production readiness or semantic correctness beyond the defined instruments.
Unavailable tests, failed repairs, and unapplicable recommendations remain in
their assigned denominators. Private evaluation occurred after the repair
campaigns were sealed.
""",
        )
    )
    chapter5.append(
        entry(
            "Figure 5.1, obsolete content",
            "DELETED",
            "Delete the analyser-only architecture branch, the old Hybrid and "
            "Agentic arm labels, first-build-derived single-shot states, and the "
            "human explanation-evaluation box.",
        )
    )
    chapter5.append(
        entry(
            "5.4 Technical Evaluation",
            "CHANGED",
            "Replace the complete current Section 5.4, including old GPT-5.4 "
            "tables, figures, rates, and placeholder results.",
            prepare_results(),
        )
    )
    chapter5.append(
        entry(
            "5.4 obsolete results",
            "DELETED",
            "Delete the old 42.2%, 21.1%, and 53.3% architecture results; "
            "first-build-derived comparisons; the unfinished groundedness and "
            "fabrication table; the old StatementBuilder regression account; and "
            "the old GPT-5.4 figures. Replace them with the frozen GPT-5.6 Sol "
            "tables and Figures 5.2 through 5.9.",
        )
    )

    return "\n\n".join(
        [
            "# Paste-ready thesis change set",
            (
                "This document supersedes the semantic unified diff. Text inside "
                "each ADDED or CHANGED block is ready to paste. Every entry gives "
                "exact edit instructions before the thesis text. The instructions "
                "and Markdown code fences are not part of the thesis. DELETED "
                "entries state whether a separate deletion is required."
            ),
            *chapter1,
            *chapter4,
            *chapter5,
        ]
    ) + "\n"


def prepare_results() -> str:
    text = RESULTS_SOURCE.read_text(encoding="utf-8")
    text = text.replace("# 5.4 Technical Evaluation\n", "5.4 Technical Evaluation\n")
    text = re.sub(r"^#{2,4} ", "", text, flags=re.MULTILINE)
    text = normalise(text)
    text = text.replace("generated artifact", "generated artefact")
    text = text.replace("failed artifact", "failed artefact")
    text = text.replace("broad analyzer count", "broad analyser count")
    replacements = {
        "reported separately rather than pooled": "reported separately and are not pooled",
        "uses a smoke oracle rather than behavioural equivalence": (
            "uses a smoke oracle because its migration changes behaviour"
        ),
        "rather than scoring single-shot outputs negatively for content they\nwere not asked to produce": (
            "because the single-shot prompts did not request that content"
        ),
        "coverage and is evidence rather than proof of preservation": (
            "coverage and provides evidence of preservation, without proving "
            "semantic equivalence"
        ),
        "with cost rather than ranked by success alone": (
            "together with cost"
        ),
        "the most parsimonious\nconfiguration observed here": (
            "the lower-cost configuration among those reaching ceiling success"
        ),
        "the defensible interpretation is: supplying a concise,\ntargeted diagnosis helped, but adding progressively broader context did not\nproduce a reliable additional gain.": (
            "the results indicate that a concise, targeted diagnosis improved "
            "repair, while progressively broader context produced no reliable "
            "additional gain."
        ),
        "supplies a concrete replication target rather than a\ngeneral causal conclusion": (
            "supplies a concrete target for replication and no general causal "
            "conclusion"
        ),
        "Within the tested setting, the most parsimonious engineering choice is grounded\nsingle-shot repair": (
            "Within the tested setting, grounded single-shot repair was the "
            "lower-cost configuration among those reaching ceiling strict success"
        ),
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    opening = (
        "5.4 Technical Evaluation\n\n"
        "This section evaluates whether the pipeline combining static analysis "
        "with LLM-based repair produces technically valid and functionally "
        "preserving repairs. The independently executed 2 x 2 x 2 factorial "
        "evaluates grounding, control structure, and visible characterisation "
        "tests. The separately frozen supplement evaluates four levels of "
        "detector-derived context in the Hybrid suggestion-plus-applier mechanism."
    )
    text = re.sub(
        r"5\.4 Technical Evaluation\n.*?(?=\n5\.4\.1 Analysis populations)",
        opening + "\n\n",
        text,
        count=1,
        flags=re.DOTALL,
    )
    synthesis_anchor = "5.4.10 Synthesis\n\n"
    overall = (
        "Across the confirmatory campaign, the pipeline achieved strict success "
        "in 423 of 456 attempts (92.8%). All final states built, 432 resolved "
        "the triggering detector condition, and 447 passed the private "
        "behavioural oracle. These totals answer RQ1 at campaign level.\n\n"
    )
    text = text.replace(synthesis_anchor, synthesis_anchor + overall, 1)
    return normalise(text)


def main() -> None:
    content = build()
    CHANGESET.write_text(content, encoding="utf-8", newline="\n")
    paste_blocks = "\n".join(re.findall(r"```text\n(.*?)\n```", content, re.DOTALL))
    style_checks = {
        "no_em_dash": "\u2014" not in paste_blocks,
        "no_en_dash": "\u2013" not in paste_blocks,
        "no_nonbreaking_hyphen": "\u2011" not in paste_blocks,
        "no_if_then_template": re.search(
            r"(?is)\bif\b.{0,100}\bthen\b", paste_blocks
        )
        is None,
        "no_negative_parallelism": re.search(
            r"(?i)not only|not merely|not [^\n.]{0,80},? but|rather than",
            paste_blocks,
        )
        is None,
        "academic_british_spelling": re.search(
            r"\b(behavioral|characterization|randomized|materialized|artifact|analyzer)\b",
            paste_blocks,
            re.I,
        )
        is None,
    }
    required = [
        "combines static analysis with an LLM",
        "423 of 456",
        "432 resolved",
        "447 passed",
        "3.95 percentage points",
        "11.84 percentage points",
        "5.70 percentage points",
        "Q=2.478",
        "2,426,669 tokens",
        "$33.6731",
        "VatResolver.Resolve",
    ]
    missing = [value for value in required if value not in content]
    labels = {
        label: len(re.findall(rf"^### {label}$", content, re.MULTILINE))
        for label in ("ADDED", "CHANGED", "DELETED")
    }
    if missing or not all(style_checks.values()) or not all(labels.values()):
        raise ValueError(
            {"missing": missing, "style_checks": style_checks, "labels": labels}
        )
    report = {
        "status": "pass",
        "artifact": str(CHANGESET.relative_to(ROOT)),
        "format": "ADDED, CHANGED, and DELETED with exact edit boundaries and paste-ready text blocks",
        "labels": labels,
        "paste_ready_blocks": len(
            re.findall(r"^Paste-ready text:$", content, re.MULTILINE)
        ),
        "style_checks": style_checks,
        "frozen_values_checked": required,
        "sha256": hashlib.sha256(CHANGESET.read_bytes()).hexdigest(),
    }
    VALIDATION.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
