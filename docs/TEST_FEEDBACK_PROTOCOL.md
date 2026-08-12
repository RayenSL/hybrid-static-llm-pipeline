# Generated Characterization Test Feedback Protocol

Status: draft for protocol freeze  
Protocol version: 0.2.0
Study: HybridLens generated-test extension  
Applicable anti-patterns: Long Method and God Class

## 1. Purpose

This protocol defines the controlled experiment for adding LLM-generated
characterization tests to the HybridLens repair pipeline. The generated tests
are an engineering feature available during repair. They are not an independent
correctness oracle and do not replace the frozen, author-written Layer-3 suite.

The experiment estimates how static-analysis grounding, repair control
structure, and access to a visible generated characterization suite affect
repair effectiveness and computational cost.

The secondary research question is:

> How does access to LLM-generated characterization tests affect the
> effectiveness and computational cost of grounded and ungrounded repair under
> single-shot and iterative control?

## 2. Scope

The generated-test intervention applies only to behaviour-preserving
refactorings:

- Long Method
- God Class

Obsolete API Usage is excluded from the generated-test comparison because its
migration is behaviour-modifying by construction and the corpus has no
specification or reference implementation that defines the correct new output.
Its existing private smoke oracle remains unchanged and is reported separately.

The original Hybrid architecture remains a deployed comparator. It is not used
as the grounded single-shot cell in the factorial design because its
suggestion-plus-applier mechanism differs from the direct-editing mechanism
used by the agentic arms.

## 3. Experimental factors

The controlled experiment is a 2 x 2 x 2 factorial:

| Factor | Level 0 | Level 1 |
|---|---|---|
| Grounding | Neutral target coordinates only; diagnosis withheld | Same target plus Structural finding and metrics |
| Control structure | Independent single-shot | Iterative |
| Visible test | No generated test supplied | Frozen generated test supplied |

All factorial cells use the same evaluated model, direct-editing contract,
pristine starting source, build environment, and final measurement pipeline.

The single-shot cells are independently executed conditions. A first-build
snapshot recovered from an iterative trajectory is retained only as descriptive
trajectory evidence and is not substituted for an independently executed
single-shot condition.

## 4. Terminology

- Visible generated test: an LLM-generated characterization test that may be
  shown to the repair model and, in iterative conditions, executed during the
  repair loop.
- Private test: an author-written, frozen characterization test that is never
  visible to the evaluated model and is executed only after a repair condition
  terminates.
- Test-informed single-shot repair: one repair call that can read a visible
  generated test but receives no execution result.
- Test-guided iterative repair: a multi-turn repair trajectory that can observe
  build and visible-test results between edits.
- Strict success: the final state builds, resolves the triggering detector
  condition, and passes the private behavioural oracle.

## 5. Generated-test construction

### 5.1 Timing and isolation

Generated tests are produced before any repair for the corresponding corpus
state. Test generation is confined to a separate pre-repair stage. It uses two
stateless calls: a planning call followed by an implementation call. If, and
only if, the resulting suite fails to compile, one further compile-correction
call is permitted. The test generator must not receive or retain a proposed
repair.

The same model family and deployment may be used for test generation and repair
because this is an experimental constraint. The calls must nevertheless use
separate conversations, versioned prompts, and independently persisted
artefacts.

### 5.2 Generator input

The frozen generator context is target-localized but diagnosis-blind. The experiment
controller reads the frozen analyzer baseline, selects one included instance, and
passes only:

- the complete pristine source file being characterised;
- its relative path and production-project name;
- a neutral target descriptor: symbol name plus declaration start/end lines;
- a deterministic project-local dependency slice containing only types named by
  the target file and their externally accessible members;
- a fixed test-project skeleton;
- the instruction to characterize observable public behaviour through that target.

The generator must not receive:

- the anti-pattern label;
- the anti-pattern diagnosis, severity, threshold, finding text, or triggering metrics;
- the seeded-instance truth record;
- the private tests or golden outputs;
- a reference repair;
- any generated or applied repair;
- detector remeasurement results.

Tests must characterize public behaviour exercised through the supplied target and
must not be named or described in a way that identifies a seeded anti-pattern.
The descriptor is identical in every repair condition for the same instance. This
prevents the visible test from giving test-ON cells unique target-localization
information.

### 5.3 Output contract

The planning call returns exactly five test obligations. Their identifiers,
categories and order are fixed before any target is inspected:

1. `H1` (`happy_path`): a representative valid flow;
2. `E1` (`empty_or_invalid`): the most relevant empty, minimal, null or invalid input;
3. `B1` (`boundary_values`): three stimuli immediately below, at and above one
   source-supported boundary, or the nearest three-point cardinality or ordering
   equivalent;
4. `A1` (`alternative_path`): a materially different valid branch or partition;
5. `D1` (`dependency_or_state`): the first applicable of a deterministic
   dependency outcome, repeat invocation, duplicate input or state transition.

Five cases are a fixed experimental budget, not a claim of exhaustive testing.
The allocation combines one representative equivalence partition with four
predeclared edge obligations. In particular, `B1` contains three boundary
stimuli rather than treating a single boundary value as an edge case. The
allocation draws on equivalence partitioning in the [ISTQB Foundation Level
syllabus](https://istqb.org/wp-content/uploads/2024/11/ISTQB_CTFL_Syllabus_v4.0.1.pdf)
and three-value boundary-value analysis in the [ISTQB Test Analyst
syllabus](https://istqb.org/wp-content/uploads/2024/11/ISTQB_CTAL-TA_Syllabus_v3.1.2.pdf).
Fixing the allocation before generation also prevents favourable cases from
being selected after a repair result is known.

Each planned obligation records its source evidence, input partition, concrete
stimuli and expected observable result. The five partition descriptions must be
distinct. The implementation call must preserve the identifiers and categories
and returns structured source for all five cases. It may include deterministic,
in-memory fake types, but may not use a mocking package or external state. The
pipeline owns the project skeleton and the assertion helper. The generator may
not create or modify project files, production source, dependencies, build
settings, or private-test artefacts.

Each frozen generated-test artefact records:

- artefact and suite ID;
- source-file or source-scope mapping;
- model deployment and model configuration;
- prompt version;
- raw system prompt, user prompt, and model output;
- generated test source;
- total and per-stage input and output token counts, and generation-call count;
- generation duration;
- admission status and reason;
- baseline build and repeated execution results;
- source, neutral dependency-context and test SHA-256 hashes;
- the frozen target symbol and declaration line range.

Exactly one five-case suite is requested per target source file. The fixed
obligations standardise breadth without adapting the number of tests to a
particular target. Generated-test coverage, mutation score, and subjective quality are not study outcomes.
Admission checks only whether the artefact is executable, stable on the
pristine state, constrained, and non-vacuous; the independent private suite
judges behavioural preservation of the repair.

### 5.4 Admission gate

A generated suite is admitted only when it:

1. parses into the required structured form;
2. contains a non-vacuous production assertion in every one of the five cases;
3. compiles in the fixed test-project skeleton;
4. passes against the pristine corpus on three consecutive executions;
5. invokes production code;
6. admits all five cases together, without case deletion or selective pruning;
7. does not require network access, wall-clock assumptions, uncontrolled
   randomness, or mutable external state.

The optional compile-correction call receives only the frozen plan, the proposed
suite and compiler diagnostics. It receives no execution or assertion result.
It may alter only using directives and deterministic helper declarations; case
identifiers, names and bodies must remain byte-for-byte unchanged. There is no
correction after a pristine assertion failure, flaky execution, malformed plan
or malformed implementation. If generation or admission still fails, the repair
attempt continues without a visible test. The primary analysis retains the
attempt in its assigned test-generation-enabled condition (intention-to-treat).
A secondary per-protocol summary may describe cases in which an admitted suite
was actually available.

## 6. Repair conditions

### 6.1 Single-shot

The grounded single-shot condition receives:

- the neutral target symbol and declaration line range;
- the Structural static-analysis finding and metrics for that same target;
- the pristine complete source file;
- the admitted visible generated test in the test-enabled cell.

The target-only (ungrounded) single-shot condition receives:

- the same neutral target symbol and declaration line range;
- the pristine complete source file;
- the admitted visible generated test in the test-enabled cell;
- no anti-pattern label, severity, metrics, thresholds, finding text, or repair advice.

Both conditions make exactly one repair call. The returned production edit is
then materialized, built, tested, and measured externally. No build, visible
test, detector, or private-test result is returned to the model.

### 6.2 Iterative

The grounded and ungrounded iterative conditions use the same loop, model,
direct-editing contract, build timeout, and iteration budget. They share the same neutral target coordinates and differ only
in whether the opening prompt additionally contains the Structural finding and metrics.

In test-enabled cells, one iteration consists of:

1. materialize the proposed production edit;
2. build the solution;
3. if the build succeeds, execute the frozen visible test suite;
4. return build and visible-test feedback;
5. consume one iteration from the fixed budget.

The static detector and private suite are never exposed as tools or feedback.

### 6.3 Test immutability

An admitted visible test is immutable once repair starts. The agent may not
edit, replace, weaken, skip, or delete it. Its frozen hash is verified before
and after every repair trajectory.

Autonomous test repair is outside this study. Allowing the model to change its
oracle would require a separate research question and baseline revalidation
protocol.

## 7. Final-state measurement

Every materialized final repair state, including Hybrid, is persisted in a
common final-state artefact before the temporary working copy is restored.

The final measurement order is:

1. determine whether the repair was materialized;
2. build the repaired solution;
3. run the original frozen visible test when one was assigned and admitted;
4. remeasure the hidden triggering detector condition;
5. run the independent whole-solution quality instruments;
6. run the frozen private Layer-3 suite.

The visible generated test remains a process measure. Only the private suite is
used as independent behavioural evidence.

## 8. Outcomes

The primary binary outcome is:

`strict_success = build_passed AND metric_resolved AND private_test_passed`

The primary denominator is every assigned repair attempt. An unmaterialized or
non-building repair is therefore a strict-success failure.

Secondary outcomes are:

- repair materialization or direct-edit availability;
- build success;
- visible generated-test pass;
- triggering-metric resolution;
- private behavioural preservation;
- whole-solution quality change;
- input, output, and total tokens;
- model-call count;
- build-attempt and test-attempt count;
- repair-only wall time;
- test-generation wall time;
- total pipeline wall time;
- estimated API cost.

Private-test preservation is additionally reported among built repairs for
comparison with the original Layer-3 result, but this conditional rate is not
the primary endpoint.

## 9. Cost accounting and budgets

Matched comparisons within a control structure use identical limits:

- grounded versus ungrounded iterative cells use the same iteration budget;
- test-enabled versus test-disabled iterative cells use the same iteration
  budget;
- grounded versus ungrounded single-shot cells use the same model and token
  limits.

Iterative and single-shot conditions may consume different total computation
because that difference is part of the architecture. Results report both
effectiveness and cost.

Test-generation cost is stored separately. Reports show both repair-only cost
and total pipeline cost. Any amortized generated-suite cost is explicitly
labelled and the unamortized cost remains available.

## 10. Private Layer-3 oracle

The private suite is:

- authored exclusively from the pristine corpus and intended observable
  behaviour;
- admitted only after passing on the pristine baseline;
- frozen before experimental repair outputs are inspected;
- stored outside every model-visible prompt and tool surface;
- never used for test generation, repair feedback, retries, or prompt tuning;
- executed after a repair condition terminates;
- applied to final states from every repair architecture.

Long Method and God Class use behavioural equivalence against the pristine
golden output. Obsolete API Usage retains its separate smoke classification and
is excluded from the generated-test-factor analysis.

## 11. Experimental execution

For Long Method and God Class, the planned core volume is:

`26 instances x 3 repetitions x 8 factorial cells = 624 repair trajectories`

The Hybrid deployed comparator may additionally be run with and without visible
tests at the frozen architecture-comparison context:

`26 instances x 3 repetitions x 2 test conditions = 156 Hybrid attempts`

Before execution, a campaign manifest fixes:

- included instance IDs;
- condition assignment;
- repetition number;
- randomized blocked execution order;
- generated-test artefact mapping and target binding;
- model deployment;
- prompt versions;
- token, iteration, and timeout budgets;
- code and corpus revision identifiers.

Conditions are interleaved within instance and repetition blocks to reduce
temporal provider or deployment drift.

## 12. Statistical analysis

The primary analysis is intention-to-treat on strict success.

The prespecified factorial model is:

`strict_success ~ grounding * control_structure * visible_test + anti_pattern + (1 | instance)`

Planned paired contrasts estimate:

- generated-test effect within each grounding x control cell;
- grounding effect within each control x test cell;
- iteration effect within each grounding x test cell.

Binary effects are reported as absolute risk differences with 95% confidence
intervals. Related planned tests use Holm correction. Generated-test admission,
availability, and visible/private disagreement are reported only as brief
process diagnostics, not as generated-test quality scores.

Before the full campaign, a simulation-based power and sensitivity analysis
must assess whether the 20 independent instances support the intended
interactions. Increasing repeated generations does not substitute fully for
additional independent instances. If the three-way interaction is
underpowered, the corpus must be expanded or that interaction must be declared
exploratory before results are inspected.

The primary figure is a paired risk-difference plot showing the test-enabled
minus test-disabled strict-success rate for each grounding x control cell, with
95% confidence intervals. A secondary panel shows the corresponding token or
pipeline-cost change.

## 13. Piloting and freeze order

The required order is:

1. validate and hash the private suite on the pristine corpus;
2. implement the generated-test, repair, artefact, and analysis infrastructure;
3. test it with unit fixtures;
4. run an end-to-end pilot only on non-evaluation fixtures;
5. perform power, runtime, and cost estimation;
6. freeze prompts, schemas, model, budgets, campaign manifest, and code revision;
7. execute the full corpus campaign;
8. freeze all repair artefacts;
9. execute private Layer-3 evaluation;
10. run the prespecified analysis;
11. document deviations before interpreting results.

Private-test outcomes must not be inspected during prompt or runner tuning.

## 14. Required implementation invariants

The implementation is not ready for an experimental run until automated tests
demonstrate that:

- single-shot conditions issue exactly one repair call;
- iterative test feedback never contains detector or private-test information;
- visible tests cannot be modified by a trajectory;
- visible-test hashes remain stable and are bound to the exact pristine source revision and target declaration;
- target-only and grounded cells receive identical neutral target coordinates;
- a no-edit iterative final state still receives its assigned final visible-test measurement;
- malformed/unknown actions cannot consume a build and parse-failure counting is consecutive;
- a failed generated-test admission does not remove the assigned repair attempt;
- the frozen campaign contains all eight conditions per block and rejects source drift;
- final source states are retained for every architecture;
- Layer 3 can evaluate Hybrid, single-shot, and iterative final states through
  one common artefact contract;
- token, call, build, test, and duration fields survive JSONL round-tripping;
- analysis uses all assigned attempts for strict success;
- obsolete-API records cannot enter the generated-test-factor analysis.

## 15. Freeze gates still requiring recorded values

The following values must be filled before changing this document from draft to
frozen:

- evaluated model deployment and model configuration;
- single-shot token limit;
- maximum generated-test source size;
- fixed randomization seed;
- cost conversion source and date;
- minimum effect size used by the power analysis;
- whether the optional Hybrid with/without-test comparator is funded;
- corpus and pipeline revision identifiers.

Already fixed in the implementation:

- generated-test prompt family: `v2.0.0` (plan, implementation and optional
  compile-correction stages);
- generator context: one complete pristine source file, its neutral public
  dependency slice, relative path, project name, and a neutral
  symbol/start-line/end-line descriptor; no anti-pattern
  diagnosis, severity, metric, threshold, finding text, repair, or private oracle;
- generated output: one fixed five-case suite (`H1`, `E1`, `B1`, `A1`, `D1`);
- fixed harness: package-free `net10.0` console project with pipeline-owned
  `Check` assertions;
- admission: plan/schema checks, a per-case non-vacuous assertion gate, compile,
  and three successful pristine executions; at most one diagnostics-only compile
  correction and no runtime-feedback retry;
- single-shot repair prompt: `v1.1.0`;
- iterative prompt: `v2.0.2` without an admitted test and `v2.1.2` with one;
- iterative build budget default: 6 in every iterative cell;
- build and visible-test timeout default: 180 seconds;
- private oracle manifest: version `2.0.0`, verified before evaluation;
- private evaluation: one execution per common final-source artefact, with no
  model, repair, detector feedback, or retry;
- core analysis: Long Method and God Class final attempts only, ITT denominator,
  strict-success conjunction, and arm-level token/call/build/test/time summary.
