# Hard review — *Static Analysis and LLMs for Verified Anti-Pattern Repair* (version of 4 August 2026)

Reviewed against the implementation (`hybrid-static-llm-pipeline`, revision `4f7c2607`), the frozen
corpus (`hybrid-pipeline-corpus` v1.0, manifest `2026-06-17`), and the two frozen result packages
(`experiments/confirmatory-gpt56-sol-20260728`, `experiments/grounding-gpt56-sol-20260728`).

Replacement text is given in fenced blocks and is written to sit in the thesis unchanged. It follows
the register of the surrounding chapters: British spelling, plain declaratives, no headline adjectives.

This document is a companion to `THESIS_PUNCHLIST.md`. Items 5, 6, 8, 10, 13, 14, 19, 20, 22 and 23 of
that punch-list are **still unapplied** in this version and are restated below with corrected values,
because some of the numbers in the old punch-list have themselves gone stale.

---

## Part 1 — Statements the artefacts contradict

These are the items that would not survive an examiner opening the repository. They are ordered by
severity.

### 1.1 §4.7 (step 2), §5.2.3, §5.2.4, §4.8.2 — the human corpus review is not recorded anywhere

The thesis states that a human reviewer inspected every generated solution before the freeze, that any
correction was recorded in a manual-intervention log, and that the truth record carries "the
verification status of each protocol layer".

In the frozen corpus none of that is present. All thirty records in `ground-truth/records/` carry a
single verification layer:

```json
"verification": { "programmatic": { "passed": true, "in_intended_band": true, "checked_at": "…" } }
```

`ground-truth/schema/truth-record.schema.json` *requires* `reviewer_r1`, so the thirty frozen records
do not satisfy their own schema. `RUNBOOK.md` (lines 107–108, 148–150) states plainly that the
reviewer layers were "left for the human review stage". Every record has `generation.manual_fixes: []`.

This matters more than a citation slip. The review is load-bearing in three separate places: it is the
mitigation offered for corpus representativeness (§4.8.2), the second of two verification layers
(§4.7), and part of the reproducibility claim (§5.2.4).

Two honest ways forward. If the review was in fact carried out, populate `verification.reviewer_r1`
across the thirty records from your notes and cite the log; nothing in the text then needs changing.
If it was not, §4.7 must be rewritten. Replacement for §4.7, item 2, in that case:

```
2. Corpus-construction review. Before freezing, the generated solutions were read by the author
   for semantic plausibility, realistic code structure, unintended anti-patterns, and agreement
   between the source and its truth record. This review was informal: it was not recorded per
   instance in the truth records, and no independent second reader was involved. It therefore
   supports the construction of the dataset but cannot be audited from the published artefacts,
   and it is not treated as a verification layer in the sense of the programmatic check above.
   Corpus verification, as published, is single-layer and programmatic.
```

and a matching sentence at the end of §4.8.2, replacing "the human corpus review (§4.7) screens for
implausible constructions":

```
the author read every generated solution before the freeze, although that reading is not recorded
per instance and cannot be reconstructed from the published records,
```

§5.2.3 then loses "and reviewed by a human reviewer §4.7", and §5.2.4's list of truth-record fields
loses "and the verification status of each protocol layer (§4.7)", replaced by "and the programmatic
verification status (§4.7)".

### 1.2 §4.3 (Seeded instances and strata) — the stratum counts are wrong

The thesis says four borderline and six clear-cut per type. The corpus manifest records the opposite
split and no borderline band at all for Obsolete API Usage:

```
"stratum_split": { "clear_cut": 20, "borderline": 10 }
God Class 5 + 5,  Long Method 5 + 5,  Obsolete API Usage 10 clear-cut + 0 borderline
"obsolete_strata": { "direct": 4, "workaround": 3, "removed": 3 }
```

Replacement for the paragraph beginning "Ten instances of each anti-pattern category are seeded":

```
Ten instances of each anti-pattern category are seeded. God Class and Long Method are each split
evenly into five clear-cut instances, whose measured values sit comfortably past the detection
bound, and five borderline instances, whose values only just satisfy it. Obsolete API Usage has no
borderline band, because the [Obsolete] marker is present or absent rather than measured against a
threshold; its ten instances are all clear-cut and are instead stratified by replacement
availability, combining genuinely deprecated BCL APIs with corpus-internal [Obsolete] libraries so
that the removed stratum is precisely constructible. The corpus therefore contains twenty clear-cut
and ten borderline instances, with four direct, three workaround and three removed replacement
cases.
```

The following paragraph in §4.3 then repeats the replacement-availability point and should be deleted
to avoid saying it twice.

### 1.3 §4.3 (Reference repairs) — no instance has a paired clean file, and God Class is not the exception

The thesis claims Long Method and Obsolete API Usage instances were built by degrading a clean variant,
so the clean original serves as a known-good reference repair, and that God Class alone lacks one.

Every one of the thirty records has `reference_repair.paired_clean_file: null`, and every one —
including all ten God Class records — carries a `reference_repair` object with `kind`, `description`
and `original_members`. The asymmetry the thesis describes does not exist in the frozen artefact; what
exists is a documented target decomposition for all three categories and compiled clean source for
none of them.

Replacement for the "Reference repairs" paragraph:

```
Reference repairs. Every instance carries a documented reference repair in its truth record: the
refactoring kind (extract method, extract class, or API migration), a prose description of the
intended target structure, and the member list that structure should produce. Long Method and
Obsolete API Usage instances were designed by first writing the clean form and then degrading it,
so their reference repair describes a structure that existed before seeding; God Class instances
were authored directly, so their reference repair describes an intended decomposition that was
never compiled. No record carries paired repaired source in either case. The reference repairs are
therefore documentation of intent, not an executable oracle, and no repair outcome in this study is
scored against them. Repairs are assessed through application, compilation, detector
re-measurement, independent diagnostics, and behavioural tests.
```

This also removes the tension with §4.5.5, which already says the truth records "carry no paired
repaired source".

### 1.4 §4.4.2 and §5.1.6 — the iteration budget is six *build attempts*, not six model calls

`AgenticRunner.cs:333` sets `maxCalls = iterationBudget + 2`, with the budget capping builds
(`AgenticRunner.cs:390, 461`) and the extra turns reserved for a planning or declaration response. The
frozen manifest records `iteration_budget: 6`. In the executed campaign the iterative arms averaged
2.0 model calls against 1.0 build attempts, so the two counts are not interchangeable.

§4.4.2: replace "An iterative repair may use at most six model calls." with

```
An iterative repair may request at most six builds. A turn that declares completion does not
consume a build, so a trajectory may use up to eight model calls within the same budget.
```

§5.1.6: replace "The iteration budget is six model calls." with

```
The frozen iteration budget is six build attempts. A trajectory ends when the model declares
completion or when the sixth build is spent, and an exhausted budget is recorded as a distinct
outcome.
```

§4.2.4's "within a six-iteration budget" and §4.4.1's "over a maximum of six iterations" are both
fine as written.

### 1.5 §4.5.1 and §3.5 (Gap 1) — precision over known-clean files was not measured

Both passages rest the case for a constructed corpus on precision being measurable over known-clean
files. In the executed confirmatory campaign it was not. Each assignment in
`factorial-manifest.json` carries one `file_path`, and that file always holds a seeded instance;
`AgenticCommand.cs:54` documents `--sweep-corpus` as the flag that widens scoring to clean and
distractor files, with the default being "only files holding a seeded instance". Table 5.10's
"Spurious 0" is therefore zero spurious findings *inside target files*, which is a much weaker
statement than zero false positives over the corpus. §5.4.4's closing paragraph already concedes the
scope; §4.5.1 and Gap 1 have not caught up.

Replacement for the second paragraph of §4.5.1:

```
Detection plays a second role in the ungrounded conditions (§4.4.1). Because the truth set is known
by construction, a finding the model reports can be scored against the recorded instance positions
rather than against a sampled annotation. A finding matches when its symbol, method, or line range
overlaps the recorded position; exact line agreement is not required. Recall and precision are
reported as percentages with 95% Wilson intervals. Both are scoped to the files that carry a target,
which is what the ungrounded conditions receive: the constructed truth set would also support
scoring spurious findings over the clean and distractor files, but the confirmatory campaign did not
exercise that wider scope, so the reported precision speaks to target files only.
```

Replacement for the second structural flaw in Gap 1 (§3.5), currently "an unguided Agentic
configuration cannot be scored for precision since the truth set is constrained by what the detector
or annotator happens to uncover":

```
Second, an ungrounded configuration cannot be scored for precision, because the truth set is
bounded by whatever the detector or the annotator happened to uncover, and a finding outside the
annotated set can be judged neither correct nor spurious. A constructed corpus removes that bound:
clean controls and near-miss distractors are known to be clean, so a report on them is a scoreable
false positive.
```

and Gap 1's closing sentence "This approach makes detection recall accurate and, for the ungrounded
Agentic configuration, makes precision measurable" (also in §1.2) becomes:

```
This makes detection recall exact rather than estimated, and makes precision over known-clean code
measurable in principle; the confirmatory campaign scored precision within target files only
(§4.5.1).
```

### 1.6 §4.8.2 — the applier is not a Claude-family model

"Using a non-evaluated Claude-family model to generate and apply corpus code is the
self-contamination precaution." The generator is `claude-opus-4-8`; the applier is
`DeepSeek-V4-Pro` (`grounding-manifest.json: applier_model`). Replacement:

```
Self-contamination is controlled by keeping the evaluated model away from code produced by its own
family. The corpus was generated by claude-opus-4-8 and the supplementary applier is
DeepSeek-V4-Pro, so the evaluated GPT deployment neither reads code drawn from its own output
distribution nor materialises its own recommendations. The arrangement is described in §4.3 and is
not repeated here.
```

The same stale wording sits in the code comment at `src/HybridLens.ContextBuilder/PromptTemplate.cs:201`
("A separate, NON-evaluated Claude-family model applies each repair suggestion") and should be
corrected there too, so the two do not drift apart again.

### 1.7 §4.3 and §5.2.3 — five projects in one solution, not five solutions

The corpus is a single `corpus/Corpus.sln` containing five `.csproj` projects and 61 `.cs` files
(Ordering 12, Invoicing 12, Inventory 11, Scheduling 12, Notifications 14). Both experiment manifests
point at that one solution. "Independently compilable solutions" is wrong, and the rationale attached
to it in §4.3 ("independent buildability provides Roslyn with a real semantic model") actually
describes project-level separation within one solution.

§4.3, replacing "Four to six independently compilable solutions (five to fifteen files apiece) covering
basic business areas (ordering, invoicing, scheduling) make up the corpus":

```
The corpus is one solution of five separately compiled .NET 8 projects, of eleven to fourteen files
each, covering ordering, invoicing, inventory, scheduling and notification domains.
```

§5.2.3, replacing "5 independently compilable .NET solutions totalling 61 files":

```
five separately compiled .NET 8 projects in a single solution, totalling 61 files,
```

### 1.8 Table 5.1 and §4.5.2 — lines of code is a severity signal, not a detection condition

`LongMethodConfig` (`src/HybridLens.Core/Configuration/DetectorConfig.cs:34–41`) gates detection on
cyclomatic complexity alone; exceeding 50 lines only escalates the finding from Warning to Critical.
§5.1.2 gets this right. Table 5.1 lists "Lines of code > 50" in a column headed *Condition*, and
§4.5.2 folds it into the resolution criterion ("cyclomatic complexity (and the secondary LOC signal)
for Long Method ... falls below its detection threshold"), which would make a repair that cut
complexity but stayed long look unresolved. It does not.

Table 5.1, Long Method rows:

| Anti-pattern | Metric | Condition | Source |
|---|---|---|---|
| Long Method | Cyclomatic complexity | > 10 (detection) | McCabe (1976); Watson & McCabe (1996) |
|  | Lines of code | > 50 (severity only) | — |

§4.5.2, replacing the re-measurement sentence:

```
Re-measurement (Layer 1). The detector of §4.2.1 is re-run on the final repair state for repairs
that build. A repair is metric-resolved when the condition that triggered it no longer holds: for
Long Method, cyclomatic complexity at or below the configured bound; for God Class, failure of the
composite (ATFD, WMC, TCC) condition; for Obsolete API Usage, absence of the flagged [Obsolete]
usage. Lines of code governs the severity of a Long Method finding rather than its existence, so it
does not enter the resolution criterion.
```

### 1.9 §6.2.5 — the token total disagrees with §5.4.9 by 10,000

§5.4.9 reports 2,426,669 tokens; §6.2.5 reports 2,436,669. The first is correct. Summing
`results/arm_summary.csv` gives 2,388,193 repair tokens, and the nineteen test-generation calls add
22,241 input plus 16,235 output, for 2,426,669. The cost follows from it exactly:
1,542,837 input at $5/M plus 845,356 output at $30/M is $33.075, plus $0.598 for test generation, or
$33.6731.

§6.2.5, replacing "required 707 model calls and 2,436,669 tokens at a nominal cost of 33.67":

```
required 707 model calls and 2,426,669 tokens at a nominal cost of $33.67
```

### 1.10 Table 5.21 — the CodeAnalyzer columns are shifted by one row

Source: `experiments/grounding-gpt56-sol-20260728/results/package/tables/grounding_whole_solution_quality.md`.

| Context | Materialised n | Mean smell delta | Mean CA headline delta | Mean CA all-rules delta |
|---|---|---|---|---|
| Minimal | 9 | −1.000 | +0.222 | −0.222 |
| Structural | 8 | −1.000 | +0.000 | −0.250 |
| Relational | 13 | −0.923 | −0.231 | −0.615 |
| Full | 11 | −1.000 | −1.545 | −4.545 |

As printed, Relational has no headline value, Full's headline shows −4.545, and −1.545 is orphaned
below the table. The corrected Full row also changes what can be said about the supplement: Full is
the only level where the independent all-rules count falls sharply. §5.4.5's "Context cost" paragraph
currently says only that Full cost the most without improving verified repair; one sentence is worth
adding after it:

```
Full was nonetheless the level at which the independent all-rules diagnostic count fell furthest
(-4.55 per materialised repair against -0.62 at Relational). Because verified repair did not move
with it and only eleven repairs were materialised at that level, this is an observation about the
resulting program states rather than an effect of context.
```

### 1.11 Table 5.14 — the context labels are offset by one row

The prose in §5.4.5 is correct and matches
`tables/grounding_results_by_antipattern.md`; the table as typeset has slipped its Context column, so
that God Class shows only three named levels and Long Method appears to begin at Full. Correct
contents:

| Anti-pattern | Context | Verified repair | Behaviour-preserving verified |
|---|---|---|---|
| God Class | Minimal | 0/10 | 0/10 |
| God Class | Structural | 0/10 | 0/10 |
| God Class | Relational | 0/10 | 0/10 |
| God Class | Full | 0/10 | 0/10 |
| Long Method | Minimal | 9/10 | 8/10 |
| Long Method | Structural | 8/10 | 7/10 |
| Long Method | Relational | 9/10 | 8/10 |
| Long Method | Full | 8/10 | 7/10 |
| Obsolete API Usage | Minimal | 0/10 | 0/10 |
| Obsolete API Usage | Structural | 0/10 | 0/10 |
| Obsolete API Usage | Relational | 2/10 | 0/10 |
| Obsolete API Usage | Full | 1/10 | 0/10 |

### 1.12 Table 5.16 — Obsolete API Usage is missing from the expected mapping it is scored against

Table 5.16 lists expected ISO/IEC 25010 attributes for God Class and Long Method only. Table 5.18
then reports "at least one expected" and "all expected" over thirty supplementary outputs per level,
ten of which are Obsolete API Usage targets, so a third of that table is scored against a mapping the
thesis never states. `QualityAttributeMap.cs:57` supplies it. Add the row:

| Anti-pattern | Expected ISO/IEC 25010 attributes |
|---|---|
| Obsolete API Usage | Maintainability, Security, Reliability, Compatibility |

and extend the caption:

```
Table 5.16: Literature-derived expected quality-attribute mapping. God Class and Long Method are the
confirmatory categories; the Obsolete API Usage row applies only to the supplement, whose lexical
coverage in Table 5.18 spans all three categories.
```

### 1.13 Appendix A — the God Class metrics block is not what the detector emits

Levels 2 and 4 show `Methods: 22 / Fields: 24 / LinesOfCode: 612`, and §C's expected response repeats
those counts in prose. `GodClassDetector.cs:55–61` emits ATFD, WMC and TCC together with their
configured bounds, and §4.2.1, §5.1.2 and Table 5.1 all describe the composite condition. The appendix
example therefore shows the model receiving evidence the pipeline never sends. Use the real corpus
target (GC-01, `Ordering.OrderProcessor`, `measured_metrics` from its truth record):

```
## Finding
Anti-pattern : GodClass
Severity     : Critical
Symbol       : Ordering.OrderProcessor
Location     : src/Ordering/OrderProcessor.cs:6

## Metrics
   ATFD: 17
   WMC: 67
   TCC: 0.0455
   AtfdFew: 4
   WmcVeryHigh: 47
   TccThreshold: 0.3333
```

and in §C:

```
"OrderProcessor exhibits the God Class anti-pattern. It reaches into seventeen distinct foreign
  attributes (ATFD 17), carries an aggregate method complexity of 67 against a bound of 47, and has
  a tight class cohesion of 0.05, so its methods barely share state ..."
```

The punch-list's earlier figures (ATFD 12, WMC 68) predate the re-derivation of `measured_metrics`
from the HybridLens detector and should not be used.

### 1.14 Appendix E — the printed prompt is two revisions behind the implementation, and one variant is missing

`PromptTemplate.cs` defines two iterative prompt versions, `v2.0.2` for the compiler-only condition
and `v2.1.2` for the condition that also executes the visible test. Appendix E prints one prompt,
labels it v2.0.0, and differs from the implementation on the points that matter to the design:

- The implemented system prompt supplies **neutral target coordinates** and asks the model to
  diagnose "the supplied target declaration(s)", falling back to whole-file identification only when
  no coordinates are given. The printed prompt asks it to "identify every occurrence ... in the
  file", which contradicts §4.2.2, §4.4.1 and §5.4.4, all of which state that both grounding
  conditions receive the same neutral coordinates.
- The implemented prompt handles the grounded case explicitly ("When the opening message also
  supplies static-analysis findings, use that additional evidence"), and
  `BuildGroundedIterativeUserPrompt` prepends the Structural finding block. The appendix documents
  neither, so the grounded iterative arm has no printed prompt at all.
- The tool paragraph is one of two frozen alternatives. The visible-test form adds the immutable test,
  its execution after each successful build, and the instruction never to weaken or bypass it. Since
  visible-test access is the confirmatory factor, its prompt has to be in the appendix.
- `{ITERATION_BUDGET}` is left unsubstituted. It is six.
- The three subsection labels still read "(LLM-only)", the running header reads "LLM prompt
  (v1.1.0)", and E.3 shows a bare JSON array although E.1's contract is an object carrying `action`,
  `edited_file` and `findings`.

Rewrite the appendix opening as follows, retitling it **Appendix B — iterative repair prompt and loop
contract (v2.0.2 / v2.1.2)** and relabelling E.1–E.3 as B.1–B.3 with "(iterative)" in place of
"(LLM-only)":

```
The iterative conditions (§4.4.1) replace the single-shot contract with an autonomous loop, frozen
under two version identifiers: v2.0.2 for the compiler-only conditions and v2.1.2 for the
conditions in which an admitted characterisation test is also executed. The loop differs from the
single-shot contract in four ways. The model must diagnose the neutrally located target before
repairing it, unless the opening message supplies the analyser's finding. It sees the complete
source file rather than a fragment. It is granted one external check, which it may invoke
repeatedly while observing the result between calls, until it declares completion or the frozen
budget of six builds is spent. And each turn is a JSON object carrying an action, the full edited
file, and the located findings. The three target anti-pattern types are named so that diagnosis is
scoped to the same categories the static analyser targets; without that scope the task would be
unbounded and the comparison uncontrolled. Nothing is said about the existence, location, or number
of occurrences. The detector is never exposed as a tool, which is what keeps the ungrounded
conditions ungrounded; the grounded conditions receive the detector's Structural finding in the
opening user message and nowhere else.
```

Then print the system prompt exactly as `AgenticSystemPromptTemplate` renders it with the budget
substituted, followed by both tool paragraphs under the headings "Compiler only (v2.0.2)" and
"Compiler and visible test (v2.1.2)", the ungrounded opening user prompt, the grounded opening user
prompt from `BuildGroundedIterativeUserPrompt`, the build-feedback turn from
`BuildAgenticBuildFeedback`, and an expected response that is an object rather than an array.

---

## Part 2 — Execution facts the thesis needs to disclose

`DEVIATIONS.md` in both campaigns records events that current claims in the thesis rule out. Deviation
9 is the one that changes what a reader may believe.

### 2.1 §4.7, §4.7.1, §4.8.1 and §6.1.1 — iterative trajectories were not all archived

Confirmatory deviation 9: the campaign named iterative trajectory artefacts from the source path and
run number without the factorial condition, so the four iterative cells overwrote one another and 57
trajectory files survive for 228 iterative assignments. Canonical run records, final sources,
build/detector/private outcomes and the 456 archived codebases are unaffected.

Against that, the thesis says "every source transition is archived" (§4.8.1), "Every prompt, response,
source transition, build outcome, visible-test result, and usage record was stored in an append-only
trace" (§4.7), and "prompts, model configuration, randomisation seeds, generated-test artefacts,
source transition, and usage records were retained" (§6.1.1). Figure 5.4 is then presented as an
instance of "individual trajectories show repairs recovering from intermediate build failure" when it
is the one surviving trajectory of 228.

§4.7, replacing the second paragraph:

```
Every prompt, response, build outcome, visible-test result, and usage record was written to an
append-only trace, and every final codebase and unified diff was archived with a checksum.
Intermediate iterative source states are the exception: trajectory artefacts were keyed on source
path and repetition without the factorial condition, so the four iterative cells overwrote one
another and 57 of 228 iterative trajectories survive. The canonical run records, sealed final
sources, build, detector and private outcomes, and the 456 archived codebases are unaffected, so
every reported outcome remains reconstructible; the per-iteration path taken to reach it is
recoverable for the surviving subset only. Post-repair validation checked assignment completion,
independent single-shot execution, iteration limits, source-state reconstruction, and consistency
between traces and sealed final states.
```

§4.8.1, replacing "The six-call budget is frozen, exhausted trajectories remain recorded outcomes, and
every source transition is archived":

```
The budget of six builds is frozen and exhausted trajectories remain recorded outcomes. Intermediate
iterative source states were partly overwritten by an artefact-naming defect (§4.7), so trajectory
depth is analysed only where it survives; sealed final states, which carry every reported outcome,
are complete.
```

§6.1.1: delete "source transition," from the list of retained records, and add after that sentence:

```
Intermediate iterative source states are incomplete for the reason given in §4.7, which bounds
trajectory-level analysis but not the sealed outcomes on which every reported contrast rests.
```

Figure 5.4's caption and the sentence citing it in §5.4.3:

```
Individual trajectories show repairs recovering from an intermediate build failure (Figure 5.4).
Only one iterative trajectory survives the artefact-naming defect of §4.7, so the figure is an
illustration of the mechanism and carries no distributional weight.
```

```
Figure 5.4: Per-iteration triggering-metric trajectory for the one surviving iterative trajectory
(grounded iterative, test OFF, AllocationCalculator.Allocate). Illustrative only; see §4.7.
```

### 2.2 §4.7 and §4.6 — the interval and test implementation were written after execution

Confirmatory deviation 5 records that the estimands, strict-success rule, model formula, Holm
requirement and power classifications were frozen before outcomes, but that the Student-t clustered
interval and the exact sign-flip implementation were added afterwards as analysis-only
operationalisation. §4.7's opening sentence currently lists "analysis plan" among the artefacts frozen
before repair, without that distinction. Add to the end of §4.6:

```
The inferential hierarchy, the strict-success rule, the mixed-model formula, the Holm families, and
the power classifications were fixed before any outcome was inspected. The concrete estimator — a
paired target-level Student-t interval on 18 degrees of freedom and an exact sign-flip
randomisation test over all 2^19 cluster sign assignments — was implemented after execution. It
operationalises the frozen estimands rather than redefining them, but it was not itself
pre-registered, and it is reported here so that the distinction is visible.
```

### 2.3 §5.3.6 and §6.1.1 — the two campaigns did not run cleanly end to end

Confirmatory deviation 3: execution stopped after 320 assignments; one zero-byte trace for assignment
321 was quarantined and the resume skipped the 320 committed assignments, repeating none. Grounding
deviations 2 and 3: assignments 1 and 2 hit an orchestration defect in trace disposal and checksum
ordering; both completed their model calls, and assignment 2's completion row was reconstructed
mechanically after the records, source link, manifest identity, tokens and trace hash were validated.
Two pre-run amendments bind the corrected binaries.

None of this invalidates a result, and saying so is better than leaving it out of a thesis that makes
much of its append-only ledgers. Add to §5.3.6, after the first two sentences:

```
Neither campaign ran uninterrupted. The confirmatory campaign halted after 320 completed
assignments; a zero-byte trace for the next assignment was quarantined and the resumed run skipped
every committed assignment, so no assignment was executed twice. In the supplement, the first two
assignments met a defect in trace disposal and checksum ordering: both completed their model calls,
and the second assignment's completion row was reconstructed after its records, source link,
manifest identity, token counts and trace hash had been validated. Two pre-run amendments record
the corrected orchestration and bind it to the remaining assignments. Prompt construction, model
adapters, generation, application, build, and detector measurement were not changed in either case.
```

### 2.4 §4.5.3 — the whole-solution measurement is a post-hoc rescore of archived states

Confirmatory deviation 11: the campaign did not persist a per-repair whole-solution delta, so all 456
frozen final sources were remeasured afterwards with the same Layer 1 detector and Layer 2
CodeAnalyzer instrument, each copied into an isolated pristine workspace, rebuilt, scanned and
restored, with no LLM and no private oracle involved. §5.4.7 hints at this ("The no-LLM whole-solution
rescore covered all 456 archived states"); §4.5.3 reads as though the measurement happened in flight.
Add to §4.5.3, after "held apart from the build gate of the verified-repair outcome":

```
The whole-solution measurement was not taken during the repair campaign. Each of the 456 sealed
final sources was copied into an isolated pristine workspace afterwards, rebuilt, scanned, and
restored, with no archive edited, no model called, and no private test executed. Measuring after
the seal is what keeps the quality reading from touching the outcome it describes.
```

### 2.5 §4.3, §5.4.1 — the reason given for excluding LM-01 is not the reason recorded

The thesis says LM-01 was excluded "because it was used in end-to-end shakedowns". Confirmatory
deviation 1 records something narrower: the protocol prose planned twenty targets, the frozen
detector-derived baseline contained nineteen, and "LM-01 `OrderImporter.ImportBatch` exists in the
corpus and private oracle but was absent from the frozen repair baseline". Both may share a root
cause, but the thesis states the causal claim and the deviations log does not. Pick one and make them
agree. If the shakedown is the reason, say so in `DEVIATIONS.md`; if not, §4.3 becomes:

```
`LM-01` is excluded because it was absent from the detector-derived baseline frozen for this
campaign, having been used in end-to-end shakedowns beforehand; it remains in the corpus and in the
private suite. The manifest, power analysis, and denominators were fixed at nineteen targets before
any repair output was produced.
```

### 2.6 §5.3.7 — the truncation claim has no support and the observed prompt sizes argue against it

"Truncation is often caused by input-size constraints at the richer context levels (Relational, Full);
truncation events are recorded on the experiment record and examined independently." No truncation
count appears anywhere in Chapter 5, and Table 5.15 puts mean prompt size at 3,554 and 3,686
characters for Relational and Full, comfortably inside the configured 2,000-token context budget
(`appsettings.json`, `Context.TokenBudget`). Replacement:

```
Secondly, the richer context levels are the ones that could exceed the configured context budget,
so truncation is recorded on the experiment record when it occurs. In the executed supplement mean
prompt size reached 3,686 characters at Full context, well inside that budget, so truncation did
not shape the reported results.
```

If any truncation events were in fact logged, report the count instead.

---

## Part 3 — Stale vocabulary from earlier designs

The 2×2×2 restructure renamed the arms but the older vocabulary survives in places, and in three of
them it says something factually different from the current design.

**§1.4** — "The study examines context level within the Hybrid arm and architecture across the Hybrid
and Agentic configurations. Analyser-only remains a descriptive no-repair baseline." There is no
Agentic arm and no analyser-only arm in this design; there is a factorial over grounding, control
structure and visible tests, plus a detector manipulation check. Replacement:

```
The technical evaluation uses detection outcomes, automated explanation signals, and metric-resolved
repair outcomes. Repair suggestions are materialised in source, compiled, and re-measured against
the detector condition that triggered them (§4.5). Detection recall and precision are measured
against the constructed truth set. The confirmatory factorial varies grounding, control structure
and visible-test access; the supplement varies context level within the original suggestion-plus-
applier mechanism. The detector-only measurement is a manipulation check on the corpus, not a
repair arm.
```

**§4.8.3** — "the Hybrid-versus-Agentic contrast (H1b) is likewise a single-model comparison". H1b is
not defined in this version, and no such contrast is reported. Replacement:

```
so results may not transfer to other anti-patterns, model families, languages beyond C#, or organic
industrial code. Transfer to organic legacy systems and generalisation across model families are
scoped as future work (§7.3); every treatment contrast reported here is a single-deployment
comparison.
```

That sentence also carries a wrong cross-reference: future work is §7.3, not §5.2.2.

**§4.8.5** — "three runs are generated for each combination of (instance, context, and model)" describes
neither experiment. The factorial has three repetitions per target and cell; the supplement has one
per target and context level. The paragraph then says "The Agentic condition combines this
stochasticity across its loop". Replacement:

```
The stochastic nature of model inference limits the reproducibility of the LLM results. To
characterise within-cell variability the confirmatory factorial generates three repetitions of every
target and cell; the supplement observes each target and context level once and therefore cannot
estimate that variability at all. Without seeded inference, which the deployed APIs do not offer,
precise reproduction of an individual run is not attainable. Detection, prompt construction, and
context extraction are deterministic and reproduce exactly from the repository. The iterative
conditions compound the stochasticity across the loop, because each turn conditions the next, so
run-for-run reproduction is furthest out of reach there. Reproducibility is preserved at the
artefact level.
```

**§5.1.7, §5.2.7, §5.3.4, §5.3.5** — four passages describe comparison "across models" and validating
that "the selected models could be invoked", left from the three-model draft. §5.2.2 states one
deployment. Corrections, in order:

§5.1.7, replacing "This representation enables (systematic) comparison across models, context levels,
and anti-pattern types":

```
This representation supports systematic comparison across experimental conditions, context levels,
and anti-pattern types, and it feeds the Python analysis and plotting stages directly.
```

§5.2.7, replacing the list ending "model families, repeated executions":

```
anti-pattern categories, experimental conditions, context levels, and repeated executions.
```

§5.3.4, replacing "the prompt requested the same output structure across models":

```
the prompt requested the same output structure in every condition,
```

and, per punch-list item 22, "structured chunks covering the quality impact, problem, suggested repair,
and risks or assumptions" becomes "structured fields covering the explanation, the quality impact, and
the suggested repair", which is what the v1.1.0 schema defines.

§5.3.5, replacing "prove that the selected models could be invoked successfully":

```
confirm that the deployment could be invoked successfully,
```

and later in the same paragraph, "correctly associating each response with the corresponding model,
context level, anti-pattern instance, run number, and prompt version" becomes "correctly associating
each response with its experimental condition, anti-pattern instance, run number, and prompt
version". The closing sentence "Since experiment contains context levels, multiple models, and
repeated runs" becomes "Since the experiments span several conditions and repeated runs".

**Appendix E labels** — see §1.14 above.

---

## Part 4 — Internal consistency, references, and numbering

- **Undefined references.** `§??` or `Table ??` appears at §1.4 (twice), §4.1, §4.5.1 (taxonomy),
  §4.5.2 (detector section), §4.5.3 (independent diagnostics), §4.8.2 (expected mapping table), §5.2.4
  (expected mapping table), §5.3.3 (per-finding strategy), and §5.3.7 (three times). Targets:
  architecture and factorial → §4.4.1; detector → §4.2.1; independent diagnostics → §4.5.3; expected
  mapping → Table 5.16; results → §5.4; per-anti-pattern reporting → Table 5.14.
- **Non-existent tables.** Table 5.11's status column points at "Table 5.9b" three times and §5.4.5
  ends with "(Table 5.3d)". Both are labels from the frozen result packages, not thesis numbers.
  5.9b → Table 5.12; 5.3d → Table 5.15. While correcting Table 5.11, note that the frozen package's
  version of that table says Minimal, Relational and Full were "Not run" — the thesis version, which
  says they were run in the supplement, is the current and correct one.
- **Unresolved citation keys.** §4.5.5 prints `[opdyke1992, fowler]` and `[apr-review]` literally.
  Fowler is [10]; add Opdyke's 1992 thesis to the bibliography, and either cite Zhang et al. [33] for
  the plausible-versus-correct distinction or add Qi et al. on patch plausibility.
- **§3.3 miscitation.** The passage cites [14] for the critique that HumanEval and MBPP
  under-represent contextual reasoning, then presents SWE-bench as the answer to that critique with no
  citation. [14] *is* SWE-bench. Replacement:

  ```
  Benchmarks such as HumanEval [7] and MBPP [3] measure functional correctness on isolated
  programming problems. SWE-bench [14] was introduced on the argument that such benchmarks
  under-represent the contextual reasoning real software work demands, and evaluates models on
  actual GitHub issues instead. The methodological lesson is that evaluating language models on
  code is not a solved problem: findings from synthetic benchmarks do not transfer directly to real
  codebases.
  ```

- **Contribution numbering.** §1.5 lists six contributions and §7.1 lists five. §4.1 then cites "§1.5,
  contribution 4" for the claim that the pipeline is an instrument rather than an outcome, but
  contribution 4 is the multi-layer operationalisation of correctness; no numbered contribution makes
  the instrument claim. Either drop the pointer in §4.1 or point it at §1.4, and reconcile the two
  lists — §7.1 has absorbed contributions 1 and 2 of §1.5 into one and dropped number 6.
- **Appendix ordering.** The appendices run A, then E, then A.1. Renumber to A (single-shot prompt
  family), B (iterative prompt and loop contract), C (strict-literal applier prompt), and update the
  four in-text references to "Appendix A" that mean the applier prompt (§4.5.2, §5.1.4 and twice in
  §4.7.1) to the applier appendix.
- **§5.4.2 ambiguity.** "The six attempts without a test remain in their assigned test-ON cells" reads
  as six in total. It is six per test-ON arm, twenty-four across the factorial (two targets × three
  repetitions × four arms), which is what confirmatory deviation 2 records. Replace with:

  ```
  The six attempts per test-ON arm that had no admitted test, twenty-four across the four test-ON
  cells, remain in their assigned cells under the prespecified intention-to-treat analysis.
  ```

- **Table 5.4 versus §4.4.1.** Table 5.4 reports 51 tests executed in the single-shot test-ON arms,
  while §4.4.1 says single-shot conditions receive no test-execution result. Both are true — the
  execution is a post-seal fidelity check — but the table does not say so. Extend its caption:

  ```
  Table 5.4: Visible-test availability and execution fidelity in test-ON arms. In the iterative arms
  the test is executed inside the loop and its result returned to the model; in the single-shot arms
  it is executed only after the final state is sealed, as a fidelity check, and no result reaches the
  model.
  ```

- **Formula rendering.** The three endpoint definitions (§4.5 twice, §5.2.5 once) render as
  `strictsuccess = buildpassedAN Ddetectorresolved...`. They need text mode and explicit operators:

  ```
  strict success = build passed ∧ detector resolved ∧ private oracle passed
  verified repair = strict-literal application ∧ build passed ∧ detector resolved
  ```

  The same fault hits the God Class condition in §2.3 and §4.2.1, where the conjunctions and the
  `≥` have dropped out: `(ATFD > FEW) ∧ (WMC ≥ VERY_HIGH) ∧ (TCC < 1/3)`.
- **Front matter.** The abstract is still the template text, the acknowledgements are still the
  template text, two committee entries read "Dr. xxx (xxx, UvA)", the copyright line ends "2026.l",
  and the cover note reads 'A "random" maze.'
- **Reproducibility locator.** §4.3 and §7.1 promise the corpus, truth records, generation prompts and
  verification scripts under an open licence, and §7.1 gives only the pipeline URL. The corpus
  manifest records MIT and `github.com/aceve/hybridlens-corpus`, under a different account from the
  pipeline's `github.com/RayenSL/...`. Give the corpus URL in §4.3 and confirm which account will host
  it before submission.
- **§4.4.3 seed.** "Target blocks and context order use randomisation seed 20260728" matches
  `grounding-manifest.json`. The confirmatory seed 503999552 in §5.2.1 matches
  `factorial-manifest.json`. Both are correct; noting them so they are not re-checked.

---

## Part 5 — Sentences that do not parse, and language edits

Grouped by kind. Each replacement keeps the author's voice.

**Broken sentences.**

§1.1, add the missing full stop: "The resulting program must build and preserve the behaviour on which
its users depend."

§1.2 runs two fragments together. "The experiments are reported separately because they use different
repair mechanisms and analysis populations. for God Class, Long Method, and Obsolete API Usage." and,
three sentences earlier, "When ground truth is recovered by post-hoc annotation of an existing system,
neither of these goals can be achieved" has no antecedent for "these goals". Replacement for the whole
final paragraph of §1.2:

```
This thesis evaluates direct-editing repair in a controlled 2 × 2 × 2 factorial over God Class and
Long Method: static-analysis grounding supplied or withheld, independent single-shot or iterative
control, and an LLM-generated characterisation test visible or withheld. A separate matched
supplement evaluates Minimal, Structural, Relational and Full context in the original hybrid
suggestion-plus-applier pipeline over all three anti-patterns, including Obsolete API Usage. The two
experiments use different repair mechanisms and different analysis populations, so their rates are
reported separately and never pooled. Both run on a constructed corpus of compilable .NET solutions
in which the seeded instances are checked programmatically before the corpus is frozen. Construction
rather than post-hoc annotation is what makes detection recall exact and makes precision over
known-clean code measurable at all; an annotated truth set can deliver neither, because no annotator
can enumerate every true instance in a non-trivial system and no finding outside the annotation can
be judged.
```

§4.3, "The only self-contamination protection in the study, so It cannot benefit from stylistic
familiarity." Replacement for the two sentences before it and it:

```
The assessed GPT model therefore never encounters code drawn from its own output distribution,
either in the corpus or in the applied repairs (§4.5.2), and cannot benefit from stylistic
familiarity. This is the study's only self-contamination protection.
```

§5.1.2, "reporting a method when it over the preset complexity bound" → "reporting a method whose
complexity exceeds the configured bound".

§6.1.2, "the final state must be build" → "the final state must build".

**Notation and typographical slips.**

§1.3, RQ1.1 ends with "??" — one question mark.
§4.1, "andfunctionally" → "and functionally".
§2.3, "the[Obsolete] attribute" → "the [Obsolete] attribute".
§4.5.1 and §4.5.3 use "S4.3", "S4.4.1", "S4.2.1", "S4.8.2" where the rest of the thesis uses §.
§6.2.2, "(p=0.125/)" → "(p = 0.125)".
§6.2.3, "p - 0, 03125" → "p = 0.03125".
§5.3.7, "this motivates the the human corpus-review layer" → one "the"; and see §1.1 above on whether
that layer can be cited at all.

**Spelling and agreement.**

"seperation" → "separation" (§6.1.2); "seperate" → "separate" (§6.2.3); "though evolution" → "through
evolution" (§3.1); "to be studies" → "to be studied" (§7.1); "changing behavioural or introducing
other diagnostics" → "change behaviour or introduce other diagnostics" (§7.1); "Grounding iterative
control, and visible-test access" → "Grounding, iterative control, and visible-test access" (§7.1);
"reorganise or extract member" → "reorganise or extract members" (§6.2.5); "established uncertainty"
→ "establishes uncertainty" (§6.1.3); "should not interpreted" → "should not be interpreted" (§6.2.3);
"limits the possibility" → "limit the possibility" (§6.1.1); "were later used for remeasurement" →
"was later used for remeasurement" (§6.1.1); "The pipeline was ran locally" → "The pipeline was run
locally" (§5.2.1); "have recently been emerged" → "have recently emerged" (§2.5); "have recently been
developed as a (promising) alternative" → "have emerged as a promising alternative" (§3.3).

**Parenthesised hedges.** Chapters 2, 3 and 5.1 carry about twenty single words in brackets —
"(inherently) limited", "(rich) program representations", "(current) hybrid approaches", "(promising)",
"(complementary)", "(potential)", "(dominant)", "(practical)", "(complex)", "(systematic)",
"(additional)", "(experimental)", "(evidential)", "(recurring)". The brackets do no work and read as
drafting marks. Either commit to the adjective or delete it; a mixture within one paragraph is worse
than either.

**Two register slips.** §5.4.4's "These figures show that diagnosis withholding rarely prevented
target recovery" and §6.2.3's "This important difference strengthens the practical case" both assert
more than the numbers carry, in a thesis that is otherwise careful. "rarely prevented" rests on 113 of
114 within a localised design and is already qualified in the next sentence, so it can stay; "This
important difference" should become "This difference in cost".

**One structural note.** §5.3.2's Detection Validation and §5.3.7's summary both say God Class
detection needs interpretive judgement, and §2.3 says the same thing a third time, forward-referencing
§5.3.2. The point is a good one and is worth making once, in §5.3.2, with §2.3 and §5.3.7 pointing at
it rather than restating it.

---

## Part 6 — Verified as correct

Checked and consistent with the frozen artefacts; no action needed. Listed so the same ground is not
covered twice.

- Detector thresholds in Table 5.1 against `DetectorConfig.cs` and `appsettings.json`: ATFD > 4,
  WMC ≥ 47, TCC < 1/3, cyclomatic complexity > 10, `[Obsolete]` marker presence. The corpus's
  `analyser-config.json` carries the same values, so the certification and detection paths agree.
- Model deployments: `gpt-5.6-sol` evaluated in both campaigns, `DeepSeek-V4-Pro` as the fixed
  supplementary applier, `claude-opus-4-8` as the corpus generator.
- Seeds: 503999552 confirmatory, 20260728 supplementary and for the GLMM and bootstrap.
- Design arithmetic: 19 targets × 3 repetitions × 8 cells = 456; 30 targets × 4 levels = 120;
  17/19 tests admitted, 51/57 per test-ON arm, 204/228 overall.
- Tables 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 5.12, 5.13, 5.15, 5.17, 5.19, 5.20 and 5.22
  reproduce their frozen source tables exactly, to the reported precision.
- Every internal total: 423 strict successes across the eight arms, 432 detector-resolved,
  447 private passes, 24 unresolved and 9 regressions summing to the 33 failures, 41 materialised and
  79 unapplicable summing to 120, 30 + 7 + 4 Layer 3 outcomes summing to 41, and the +46 headline
  CodeAnalyzer change summing across the eight Performance rows of Table 5.20.
- Whole-solution deltas: the per-arm means in Table 5.19 multiply out to the campaign totals quoted in
  §5.4.7 (−429 smells, −106 all-rules, +46 headline).
- Cost accounting: $5.00/M input and $30.00/M output reproduce $0.5983 for test generation, $33.6731
  for the confirmatory campaign, and $3.1710 for the supplement, including each per-level figure in
  Table 5.15.
- Statistics: +3.95 pp [−0.57, +8.46] p = 0.125 for the visible-test main effect, +11.84 pp
  [+1.27, +22.41] p = 0.03125 for grounding, +5.70 pp [−2.88, +14.28] p = 0.21875 for iteration, all
  four cell-specific estimates, and +234.4 [+135.1, +333.8] repair tokens, all match
  `paired_risk_differences.csv` and `paired_token_differences.csv`.
- GLMM sensitivity: random-intercept SD 0.746 under MAP against 2.176 under variational Bayes, with a
  weak-prior fit that does not converge, matches `GLMM_METADATA.json` and `glmm_random_effect.csv`.
  §5.4.3's refusal to let the model override the paired analysis is the right call and is stated well.
- Supplement inference: Cochran Q = 2.4783, df = 3, p = 0.4792; adjacent contrasts −3.3, +10.0 and
  −6.7 pp with McNemar p of 1, 0.375 and 0.6875 and Holm p of 1 throughout.
- Corpus counts: 61 files, 30 seeded instances split 10/10/10, 31 clean and distractor files, one
  file per instance so that the co-located-finding component of Full context is empty, and the three
  distractor kinds named in §4.3 all present.
- The nine private regressions are one target, `VatResolver.Resolve`, in the arms the thesis names.
- 707 model calls: 228 single-shot, 19 test generation, and approximately 460 iterative, from the
  per-arm call means.

---

## What I would fix first

Part 1.1, then 2.1. Everything else is correctable prose or a number; those two are places where a
reader who opens the repository finds something the thesis says is there and it is not. Both have
clean fixes that cost the thesis very little: the corpus verification becomes single-layer with a
stated limitation, and the trajectory archive becomes complete for sealed states and partial for
intermediate ones. Neither touches a reported result.
