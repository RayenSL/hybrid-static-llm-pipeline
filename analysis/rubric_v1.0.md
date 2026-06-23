# HybridLens rating rubric — anchor criteria (v1.0)

Companion to Appendix B of the thesis. Both raters (R1, R2) read this before and
during scoring. Every dimension is a **3-point ordinal**: `poor` / `adequate` / `good`.

## Cross-cutting principles

1. **Rate each dimension independently** (§B.3.1). A correct explanation can be
   unclear; a clear one can be wrong. If your justification for dimension N
   references another dimension's score, re-rate.
2. **"Good" is lenient, not perfect.** Good = *no material defects*. A single
   cosmetic nitpick does **not** knock a rating from Good to Adequate.
3. **"Material" test.** A defect is material if a developer who believed/acted on
   it would make a wrong decision. Immaterial slips (e.g. "≈20 methods" when it's
   22) stay Adequate, not Poor.
4. **Adequate is not a dumping ground** (§B.3.3). Can't decide Poor vs Adequate →
   choose Poor + rationale. Can't decide Adequate vs Good → choose Adequate + mark
   uncertain (`a?`).
5. **Mandatory rationale** on any Poor or uncertain rating. "No idea" is not a
   rationale — if you genuinely cannot assess a dimension, mark it uncertain.
6. **Blinding benefit-of-the-doubt.** You cannot see the rest of the file. A repair
   that references a member not in the snippet is given the benefit of the doubt
   (it may exist elsewhere) **unless** it contradicts visible code.

---

## Explanation dimensions

### explanation_correctness — factual accuracy vs the code + anti-pattern definition

| Level | Criteria |
|---|---|
| **poor** | ≥1 *material* factual error: claims methods/fields that don't exist, misidentifies the anti-pattern, attributes the wrong quality impact (e.g. calls a Long Method a security issue), or invents code elements. |
| **adequate** | Largely accurate; ≤1 *minor* imprecision that doesn't change the diagnosis (slightly-off metric, defensible-but-loose characterisation). |
| **good** | Factually accurate throughout; every claim about the code, the anti-pattern, and the impact is verifiable against the supplied artefacts. Verbosity/length is **not** penalised here. |

### explanation_groundedness — specific to *this* code vs generic textbook

| Level | Criteria |
|---|---|
| **poor** | Entirely generic. Names no specific class/method/field/responsibility. Could be pasted onto any instance of this anti-pattern unchanged. |
| **adequate** | Names the specific symbol **and** ≥1 concrete element (a method, a field, or a metric value), but the bulk of the analysis is still generic. A cited metric ("612 lines") counts here. |
| **good** | Engages substantively with specific elements: names methods/fields, identifies the distinct responsibilities they reflect, or refers to structural features (call patterns, line ranges) that would not appear in a generic description. |

### explanation_completeness — covers *what* / *why* / *impact*

| Level | Criteria |
|---|---|
| **poor** | ≥1 of the three components missing, or the impact reduced to a generic phrase ("this affects maintainability"). |
| **adequate** | All three present, each ≥1 substantive sentence, but ≥1 component is treated thinly relative to the others. |
| **good** | All three present and developed; the impact component ties to specific quality attributes with reasoning, not a bare enumeration. |

### explanation_clarity — first-read comprehensibility (independent of correctness)

| Level | Criteria |
|---|---|
| **poor** | Hard to follow on first read: dense unstructured block, jargon without context, abrupt shifts, sentences needing re-reading. |
| **adequate** | Understandable on first read with minor issues (awkward phrasing, mild redundancy, one poorly-structured section). |
| **good** | Easy to follow: logical flow, good structure (grouping/bullets credited here), no needless jargon, concise without being terse. **An incorrect explanation can still be Good here.** |

---

## Repair dimensions

### repair_correctness — addresses the anti-pattern AND compatible with the code

| Level | Criteria |
|---|---|
| **poor** | Does not address the detected anti-pattern, or is clearly incompatible with visible code (contradicts visible types, would not compile against what's shown). |
| **adequate** | Addresses the anti-pattern, broadly compatible, with minor issues a developer would correct (slightly-off signature, a name clash). Members not in the snippet get benefit of the doubt. |
| **good** | Clearly addresses the anti-pattern and is fully compatible with the supplied code; signatures, type names, and structural assumptions match what's visible. |

### repair_completeness — main steps + necessary side-changes

| Level | Criteria |
|---|---|
| **poor** | One-liner naming a refactoring without *how* ("Apply Extract Class."), or omits a step that would block implementation. |
| **adequate** | Describes the main steps but omits 1–2 practical considerations (updating callers, test impact, DI/config). |
| **good** | Main steps **and** principal side-effects covered; a developer would have a clear plan. |

### repair_actionability — could a developer start within minutes?

*Discriminator vs completeness: completeness = "are all the steps there?"; actionability = "could I start step 1 in under 5 minutes without more design work?"*

| Level | Criteria |
|---|---|
| **poor** | Too abstract to start: principle-level advice ("follow SRP"), pattern names without concrete targets. |
| **adequate** | Concrete enough to start, but non-trivial decisions remain before coding ("extract the validation logic" without saying which methods). |
| **good** | Names specific code elements (methods/fields/line ranges) for the changes; developer can begin editing within minutes. |

### repair_semantic_risk — REVERSE-CODED (good = low risk)

| Level | Criteria |
|---|---|
| **poor (high risk)** | If followed literally would likely change behaviour the developer might not anticipate (silently alters exception semantics, swaps a deprecated API for one with different defaults, breaks an implicit invariant) — and does **not** flag it. |
| **adequate (some risk)** | Mostly safe but contains a step to verify carefully; the risk is present/named but not mitigated. |
| **good (low risk)** | Safe as described, **or** where risks exist they are explicitly flagged with guidance ("before applying, check no caller relies on the existing exception type…"). |

> If you cannot assess the risk, mark **uncertain** (`g?` / `a?`) — do **not** default to Poor.

---

## Baseline (analyser-only) rating rule  ⚠ read before rating any baseline row

Baseline rows have `model_name = static-analyser` and `context_level = analyser_only`.
Their output is the analyser's diagnostic line plus *"not provided by the static
analyser"* placeholders for quality impact and remediation.

**Rate the baseline honestly under the same rubric** — do not mark everything Poor
by reflex. This is what makes the H1 comparison a *fair* test rather than a
tautology, and it is required to test H1's prediction of *no systematic accuracy
difference* (§4.4.1). Verify each per instance, but the expected pattern is:

| Dimension | Baseline default | Why |
|---|---|---|
| explanation_correctness | **good** | The diagnostic (type, location, metric values) is factually accurate. Poor only if the metrics/location are actually wrong. |
| explanation_groundedness | **adequate** | Names the specific symbol and cites metric values, but offers no responsibility-level analysis. |
| explanation_completeness | **poor** | Only "what" is present; no "why" or "impact". |
| explanation_clarity | **adequate** | A single clear factual sentence. Apply uniformly to *every* baseline row. |
| repair_correctness | **poor** | No repair is provided. |
| repair_completeness | **poor** | No repair is provided. |
| repair_actionability | **poor** | No repair is provided. |
| repair_semantic_risk | **good (low risk)** | A non-existent repair cannot introduce behavioural risk. Reverse-coding applied consistently. |
| hallucination_categories | **(none)** | The baseline makes no false claims. |

This asymmetry is expected and worth reporting: hybrid should beat baseline on
completeness, groundedness, clarity, and the three positive repair dimensions,
but **not** on correctness (both accurate) and **not** on semantic risk (an empty
repair is risk-free). That is exactly H1's predicted shape.

---

## Change log

- **v1.0** — initial anchored rubric. Constructs from thesis §B.4–B.5; anchors and
  the baseline rule fixed here for the pilot.
