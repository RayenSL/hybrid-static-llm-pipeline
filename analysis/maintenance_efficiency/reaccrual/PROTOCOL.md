# Quality of LLM output over software evolution: repair durability and maintenance accrual

Version 0.3, 5 October 2026. Draft protocol, **not frozen and not executable**. No maintenance-agent model call has been made under it. It becomes executable only after the gates in Section 12 and the user's authorisation of a token ceiling (Section 11). Changes after the freeze are recorded as deviations (Section 13).

Changes from v0.2. These were all made after the no-model feasibility audit (Section 10) and before any maintenance-agent call, so no agent outcome informed them:
- **Option B oracle tests.** Replay steps without a behavioural oracle receive supplementary oracle tests, written under [ORACLE_TEST_SPEC.md](ORACLE_TEST_SPEC.md) by a different model family from the agent, then validated by stub sensitivity, reviewed by a human and frozen before any agent call (Section 4.1).
- **H1 measures code volume.** The audit showed that the developers' changes in the eligible windows add a median of 0 decisions and 2 code tokens per change. Decision-burden accrual would therefore be close to floor. H1 now uses accrued code volume; decision burden becomes H1b, secondary (Sections 2 and 7.4).
- **Replication for H1.** The O branch runs three independent trajectories per stratum-A target, so H1 compares an averaged agent trajectory with the deterministic developer history (Section 8.1).
- **Target choice prefers God Class.** In a file with both finding types at t0, the God Class finding is the target (Section 4.1).
- **Token-based context bound** replaces the 28 KB byte rule (Section 6.1).
- **Fixed SESOI values** replace the data-derived one (Section 8.2).

Changes from v0.1:
- The v0.1 confirmatory hypothesis compared the maximum complexity of an original and its repair. For Long Method targets this is close to true by construction, because the repair has already split the method. It is withdrawn.
- The primary stratum is now **historical replay** on a private industrial system. Requirements and oracles come from real commits, and the developers' own history forms a third, human branch.
- The corpus becomes a controlled replication, with tasks authored by an independent reviewer who does not see the repairs.

This protocol supersedes [RESEARCH_RESET.md](../RESEARCH_RESET.md) for the maintenance line of work and uses option 4 of [GAP_REPORT.md](../gap_research/GAP_REPORT.md) (removal versus relocation) as its measurement layer. Earlier sealed maintenance results remain development evidence and are not reinterpreted.

## 1. Background and gap

### 1.1 What is known about the quality of LLM output

The quality of LLM-generated code is almost always judged **at the moment it is generated**: whether it compiles, passes tests and removes a warning. The thesis does the same. Its strict-success endpoint establishes that a repair is buildable, detector-resolving and behaviour-preserving at one point in time. Separate evidence suggests that point-in-time checks miss properties that matter for maintenance:

- Generated and agent-written code shows structural problems that functional correctness does not reveal. Zhu, Tsantalis and Rigby report that more capable models produce more bloated and coupled code, and that neither functional correctness nor detailed prompting prevents this ([AI-Generated Smells](https://arxiv.org/abs/2605.02741), preprint, abstract-level assessment).
- When code quality is varied in a controlled way, the agent's correctness on single tasks does not change (91.3% vs 92.1% over 660 trials), but its footprint does ([minimal-pair study](https://arxiv.org/html/2605.20049v1), preprint). The authors state that whether effects compound over a longer horizon is unknown.
- How agent-generated code evolves after it is merged is starting to be studied observationally: [Sawada et al.](https://arxiv.org/abs/2605.06464) (preprint) on how agent-written files are later maintained, and [Coppola et al.](https://arxiv.org/abs/2609.04208), an ESEM 2026 registered report, results pending, comparing agent implementations of issues with developer commits.
- [SlopCodeBench](https://arxiv.org/html/2603.24755v1) (preprint) follows agents extending their own code across evolving requirements.

### 1.2 Link to the thesis's debt motivation

The thesis motivates repair through technical-debt interest, which is a cost that accumulates as code keeps changing:
- smelly classes attract more changes and fixes ([Palomba et al.](https://link.springer.com/article/10.1007/s10664-017-9535-z));
- about 80% of smell instances survive (Tufano et al., thesis reference [48]);
- in Appendix B, 93–98% of God Class and Long Method findings in Jenkins and Tomcat were redetected after their files changed.

A repair that does not last does not pay down debt. Equally, an LLM maintainer that piles complexity back into code may be a new source of debt.

### 1.3 Gap

**No study tests the quality of LLM output across the evolution of real code under controlled conditions.** Specifically:

1. whether a verified LLM repair stays repaired once later changes arrive; and
2. whether an LLM maintainer adds complexity faster or slower than the developers who actually made the same changes.

Both are measured on identical requirement sequences from real history, with private code that cannot have appeared in training data.

The closest work differs:
- Observational studies of agent code (Sawada; Coppola) do not hold the requirement sequence fixed or apply a repair intervention.
- SlopCodeBench and the minimal-pair study use public or constructed code, with no verified-repair arm and no human branch on the same changes.
- Studies of refactoring persistence in human history (e.g. [Robredo et al.](https://link.springer.com/article/10.1007/s10664-025-10801-3)) do not study LLM output.

## 2. Research questions and hypotheses

These extend RQ4. They were formulated after the original campaigns and after earlier maintenance results were known.

- **RQ5.1 (durability of LLM repair).** After a verified LLM repair, how often does the repaired anti-pattern recur during subsequent maintenance, and after how many changes?
- **RQ5.2 (accrual by an LLM maintainer).** On identical historical change requests, does an LLM maintainer add more complexity to the target code than the developers did?
- **RQ5.3 (effect of the repair on later maintenance).** Starting from the repaired rather than the original code, does an LLM maintainer add less complexity, complete more changes correctly, or use fewer tokens?

Two confirmatory hypotheses, tested in the industrial stratum with Holm correction across the two:

- **H1 (RQ5.2):** per change, the LLM maintainer adds more code to the target file than the developers did for the same commits (V_O > V_H, Section 7.4).
- **H2 (RQ5.3):** per change, the LLM maintainer adds less decision burden starting from the repaired code than from the original (A_R < A_O).

Secondary, not part of the confirmatory family: **H1b**, per change the LLM maintainer adds more decision burden than the developers (A_O > A_H).

Neither confirmatory comparison is true by construction. In H1, O and H start from the same source and implement the same commits, so volume differences reflect how much code each writes for an identical change. In H2, decision burden counts all branching logic in the file, wherever it is placed, so splitting a method does not reduce it mechanically.

H1 is motivated by reports that LLM-generated code is more voluminous and bloated than necessary (Section 1.1). The audit found that the developers' changes in the eligible windows are small (median 2 tokens and 0 decisions added per change), so an agent's excess code is measured against a small, stable baseline.

RQ5.1 is estimated with an interval and has no test. Correctness and tokens are estimated, without a directional hypothesis.

## 3. Design overview

| Stratum | Role | Code | Requirements and oracle | Branches |
|---|---|---|---|---|
| A, industrial replay | Primary | Ibis.Calculeren.Bouw (private, organic) | Real commits that changed the target file, and their tests | H (history), O (agent on original), R (agent on repaired) |
| B, corpus replication | Controlled replication | 21 held-out corpus targets | Four authored requirements per target, written by an independent reviewer | O, R |

In every branch, each step starts from that branch's own previous state. The agent's contract is identical in O and R and blind to the branch label. Structure is measured after every step. The unit of analysis is the target; steps, calls and test executions are not independent samples. Strata are analysed separately and never pooled.

## 4. Stratum A: historical replay

### 4.1 Target eligibility

A **target** is a God Class or Long Method finding of the thesis detector (GC: ATFD > 4, WMC ≥ 47, TCC < 1/3; LM: historical CC > 10) in a production file of the loaded solution. A target is eligible if all of the following hold:

1. **Replay window.** After the 2024-07-27 lineage break, there is a run of K consecutive commits touching the target file, with 2 ≤ K ≤ 4, such that each commit:
   - is non-merge and changes at most 30 files;
   - changes the target file; and
   - has at least one fail-to-pass test, meaning a test in the test projects that reference the target's production project, plus any test project changed by the commit. The test must pass with the post-commit target file, with every other file held at its post-commit state, and must fail under one of two checks:
     - **Test kind:** it fails with the pre-commit target file.
     - **Stub kind:** the pre-commit target file does not compile against the commit's other changes, and the test fails on the *stubbed* file. The stubbed file is the post-commit file with the body of every member added or changed by the commit replaced by `throw new NotImplementedException()`; unchanged members keep their post-commit bodies (`src/HybridLens.ChangeStub`).

     A step whose pre-commit file does not compile and whose stubbed file exposes no failing test is **unchecked**. Changed field or auto-property initialisers cannot be stubbed and are listed per step.
     - **Oracle-test kind (option B, v0.3):** an unchecked step that has at least one stubbable changed member qualifies once a supplementary oracle test class for it passes every check in [ORACLE_TEST_SPEC.md](ORACLE_TEST_SPEC.md): static guard, pass twice on the post-commit state, at least one failure with the changed members stubbed, and human review. Unchecked steps with no stubbable member cannot be validated and stay unchecked. A step whose oracle class is rejected twice stays unchecked, and the window is cut there. Oracle classes are frozen before any agent call. They then form part of that step's fail-to-pass set, and of the retained tests of later steps in the window where they still pass on the historical post-commit state.

   Amendment 0.2.1 (5 October 2026, before any model call): the stub kind was added after the interim audit showed that most qualifying steps failed only at compilation, so the developers' tests had never run against the pre-commit file.

   "Consecutive" means that no unreplayed commit touches the target file inside the window, so every branch sees exactly the change sequence the developers worked through. The window start is t0, the parent of the first commit.
2. **Flagged at t0.** The finding is present at t0 under the same detector configuration.
3. **History builds and passes.** At t0 and at each historical step, the solution builds and the selected test projects pass, apart from failures recorded as pre-existing and excluded identically in every branch.
4. **Context fits.** The target file at t0 is at most 32,000 tokens, estimated at 3.5 UTF-8 bytes per token (Section 6.1). Larger files are excluded and the resulting size bias is reported.
5. **Independence.** At most one target per file. If the file has a God Class finding at t0, that finding is the target. Otherwise, and between several findings of the same type, the one with the lowest SHA256(seed|file|symbol|line) is chosen.

Eligible targets are ordered by SHA256(seed|target ID) within strata of anti-pattern type and band (borderline: WMC within 10% of 47 or CC 11; otherwise clear-cut). Up to N_A targets are taken in that order (Section 11). Selection is fixed before any repair is attempted.

### 4.2 Repair acquisition

At t0, each target receives up to three independent repair attempts with the thesis's grounded single-shot arm. The first attempt that passes all of the following is accepted:
- build;
- the target no longer flagged and no new finding of the target's anti-pattern type in the file;
- the assembly-visible API preserved, including internal members referenced from other files (later historical commits may use them);
- every selected test project passing at t0.

Every attempt is charged. An acquisition flow table records selected, attempted, built, resolved, API-preserved, tests-passed and accepted. A target with no accepted repair keeps its H and O branches for H1. It is excluded from H2 and P1, and the exclusion is reported as an acquisition failure. Failed acquisition is never replaced by another target.

### 4.3 Steps

At step k:

- **H branch:** the historical post-commit target file. No model is used.
- **O and R branches:** the repository is set to the historical post-commit state of commit k, **except for the target file**, which holds the branch's state after step k−1. The agent must make the target-file part of the change.

The agent receives:
- the commit message, and any linked work-item title and description the commit references;
- the commit's changes to non-test files other than the target file, as a diff;
- the current branch target file;
- the registered supporting files.

The agent never receives the developers' target-file diff, any test file, future commits, the other branch or the branch label.

A step is **completed** when all of the following hold:
- the patch applies and the solution builds;
- the assembly-visible API is preserved, apart from members the historical commit itself removed or changed;
- every fail-to-pass test of commit k (test or stub kind) passes;
- every test that passes on the historical post-commit state also passes;
- the step is within the branch allocation.

A branch stops at its first failed step; later steps count as not completed. No reference, developer diff or test result is ever given to continue a branch.

### 4.4 Privacy

Sources, target identities, commit texts, prompts, outputs and per-target results are stored outside this repository (`z:\rayen\reaccrual\`). Only aggregate, de-identified results are reported in the thesis and this repository. Model calls go only to the existing gpt-5.6-sol deployment used for the thesis's industrial campaigns. Sending Bouw source to it requires the same organisational approval obtained for Besteks, recorded before the freeze.

## 5. Stratum B: corpus replication

The source pairs are the 26 deterministic pairs in `../generated/campaign.json`. GC-01, GC-06, LM-02, LM-04 and LM-05 are reserved for development and calibration. **Validation:** GC-02, -03, -04, -05, -07, -08, -09, -10, -11, -12 and -13; LM-01, -03, -06, -07, -08, -09, -10, -11, -12 and -13.

Prior-knowledge disclosure: these repairs were generated and censused in earlier work. GC-12 and LM-13 appear in thesis Section 5.7. No maintenance outcome has been observed on any of the 21. All 26 selected repairs have zero GC/LM findings in their file at step 0.

Each target receives K = 4 cumulative requirements from families F1–F4:
- F1, variant addition;
- F2, rule interaction;
- F3, cross-cutting constraint;
- F4, state or side-effect extension.

At least two steps come from F1 or F2. Requirements describe observable behaviour only and never prescribe a decomposition.

**Authorship.** Sequences, hidden tests, cumulative references and at least two deliberately faulty variants per step are written by the second corpus reviewer (R2). R2 works from the original source, its public API and the private oracle, and does not see the repairs. The thesis author may review tests for executability only, without changing requirement content.

**Admission gates per step k:**
- G1: the previous reference fails a step-k case (at step 1, so does the repair).
- G2: the reference passes all current and retained cases.
- G3: every faulty variant fails a case.
- G4: original and repair give identical results on every case at step 0.
- G5: the final reference adds at least one owned decision.

Superseded obligations are listed explicitly.

## 6. Maintenance agent

### 6.1 Contract (both strata, O and R branches)

| Setting | Value |
|---|---|
| Model | Existing `gpt-5.6-sol` deployment. The returned model identifier is recorded per call. |
| Calls per step | At most 2: initial, plus one retry only after an invalid patch or a build failure, carrying compiler diagnostics. Never test results. |
| Edit contract | Strict JSON line patches (`../natural_validation/patches.py`) restricted to the target file. New types and members inside the file are permitted. |
| Output cap | 4,096 completion tokens per call, reasoning included. |
| Input bound | 49,152 tokens per call. The deployment's context limit must be confirmed to exceed input plus output before the freeze; if it does not, the bound and the eligible set (Section 4.1, item 4) are reduced before any agent call. Calibration validates the per-call reservation against provider-reported input usage. The reservation is serialised UTF-8 bytes divided by 3.5, plus 10% and 512 tokens of framing; it is revised only if calibration shows provider usage exceeding it. |
| Context | As in Section 4.3 (A) or as the step-k requirement plus supporting files (B). Supporting files are chosen by the type-reference closure of the **original** target file, identical across branches. |
| Instruction | Neutral: implement the requirement and keep the public API. No mention of design quality, anti-patterns or the repair. |
| Conversation | Fresh for every step. |
| Order | Steps alternate between O and R within a target. The first branch is set by the parity of SHA256(seed\|target ID). |

A tool-using agent that opens files on its own is out of scope. Token outcomes therefore cannot capture navigation effects.

### 6.2 Guards

These are the existing forbidden-symbol checks, child-process timeouts and API checks. They are not an operating-system sandbox. Bouw tests run in the local environment in which the selected test projects already pass. Test projects that require external services are excluded from the oracle and listed.

## 7. Measurements and endpoints

### 7.1 Structure

Structure is measured on the target file inside the loaded solution after every step, in every branch:
- thesis detector findings, with identity (rule, Roslyn documentation ID);
- owned-decision complexity per callable, file decision burden (Σ owned decisions), maximum nesting and exact clone coverage at 50 tokens (sensitivities 30 and 70), as defined in `../../repair_design_quality/MEASUREMENT_CONTRACT.md`;
- class WMC;
- lines changed per step relative to the previous state of the same branch.

### 7.2 Notation

S_(b,k) is the state of branch b ∈ {H, O, R} after step k. L_b is the number of completed steps; L_H = K by definition.

### 7.3 P1, durability of the LLM repair (RQ5.1, estimate)

A recurrence occurs at step k if S_(R,k) has a finding of the **target's own anti-pattern type** in the target file that S_(R,0) did not have. Cross-type findings are reported separately. In the corpus, God Class repairs still contain methods at CC 8–10, so a single added decision creates a Long Method finding regardless of whether the repair held.

The time to recurrence is the first such step. A branch that fails before recurring is censored at L_R. The proportion recurred by step K is estimated with Kaplan–Meier, plus the crude proportion among R branches that completed K steps (exact Clopper–Pearson interval). Results are reported per stratum, anti-pattern type and band.

### 7.4 P2, accrual per change (RQ5.2 and RQ5.3, tests H1 and H2)

For branch b and its first j completed steps, two accruals per change are defined:

V_b = [T(S_(b,j)) − T(S_(b,0))] / j and A_b = [D(S_(b,j)) − D(S_(b,0))] / j,

where:
- T is the number of C# syntax tokens in the target file, excluding trivia (whitespace and comments);
- D is the file decision burden.

| Comparison | Steps compared, j | Quantity |
|---|---|---|
| **H1** | L_O of each O trajectory | The mean, over the target's O trajectories with j ≥ 1, of V_O(j) − V_H(j). Each trajectory is compared with the developers' state after the same j steps. When all trajectories complete equally many steps, this equals averaging V_O first (Section 8.1). |
| **H1b** | Same as H1 | A_O − A_H |
| **H2** | min(L_O, L_R), using O trajectory 1 | A_O − A_R |

A trajectory or target with j = 0 contributes nothing to that comparison and is counted. Comments and formatting are excluded from T, so neither documentation nor layout counts as code volume.

### 7.5 Secondary endpoints

- **Correctness:** L_O/K and L_R/K; full-sequence completion; first-failure stage (invalid patch, build, API, fail-to-pass, regression).
- **Tokens:** input, output and total per branch, including failed calls and repair acquisition (kept separate). Cached-input and reasoning tokens are subsets and are not added again; unknown usage stays unknown. No monetary cost is reported.
- **Concentration:** maximum owned callable complexity and maximum class WMC per step, in all branches. O versus R is descriptive only, because of the construction issue described in the version notes.
- **Placement:** the share of a step's added decisions that land in the callable that was largest at the previous step.
- **Duplication:** growth in clone coverage.
- **Edit footprint:** agent lines changed per step divided by the developers' lines changed on the same commit (stratum A).
- **Introduced findings of any type,** and their lineage relative to the original target, using the repair-design continuity rules. Uncertain mappings stay uncertain.

## 8. Analysis

### 8.1 Confirmatory tests (stratum A)

In stratum A, the O branch runs three independent trajectories per target, each with fresh conversations and the same contract. For H1, a target's V_O is the mean over its trajectories with j ≥ 1. H is deterministic. For H2, only O trajectory 1 is paired with the single R trajectory. Trajectories 2 and 3 are not used for H2 or P1, so both branches enter H2 with one trajectory each.

For each of H1 and H2:
- the mean of the paired per-target differences with a 95% t-interval, matching the thesis's target-level reporting;
- a one-sided exact sign-flip p-value in the hypothesised direction;
- Holm correction across the two hypotheses at familywise α = 0.05.

A hypothesis is supported only if its Holm-adjusted p-value is below 0.05 and the interval lies on the hypothesised side of zero. Stratum B tests the same two quantities, but H1 does not exist there because it has no H branch. Stratum B reports H2 as a replication with its own interval, not as an additional confirmatory test.

### 8.2 Equivalence

The smallest effects of interest (SESOI) are fixed values, set before any agent call:
- 25 tokens per change for volume comparisons (H1), about two statements, and twice the developers' median absolute volume change per change in the eligible windows (12.5 tokens);
- 1 decision per change for decision-burden comparisons (H1b, H2).

The v0.2 rule, half the developers' median accrual, was dropped because that median is 0 in the eligible windows. Equivalence is claimed only if the 90% interval lies within ±SESOI. Otherwise a non-significant result is inconclusive.

### 8.3 Pre-specified sensitivity analyses

1. Exclude targets where any step needed the retry call.
2. Stratum B without GC-12 and LM-13 (prior detailed knowledge of the repairs).
3. Clear-cut versus borderline.
4. P1 limited to recurrences on symbols whose owned decisions increased since step 0 (excludes pure relocation).
5. P1 and P2 with censored or instrument-failed branches treated as best case and as worst case.
6. H2 using each branch's full completed prefix instead of the common prefix (labelled unpaired in steps).
7. Stratum A excluding commits whose linked work-item text was unavailable.

### 8.4 Precision

The smallest exact one-sided sign-flip p-value is 1/2ⁿ for n targets, so after Holm correction across two hypotheses the smallest attainable adjusted p-value is 2/2ⁿ. A confirmatory test therefore needs at least 6 targets with completed steps. With fewer, the hypothesis is reported as not testable rather than unsupported.

Target counts are limited by real history and repair yield, not by budget alone. The feasibility audit (Section 10) reports the attainable N_A and the resulting interval widths before any model call. Repeated calls on the same target do not increase precision.

## 9. Calibration

Calibration uses separate development material: the stratum-B development targets, plus two stratum-A **God Class** targets chosen by the lowest SHA256(seed|target ID) and removed from validation. They are drawn from the God Class stratum because it has the surplus after oracle admission; this rule was fixed after the eligibility counts and before any agent call. It runs the O branch only, under the final contract, with three trajectories on the two stratum-A calibration targets. It estimates the spread of V_O − V_H, which is reported as the expected precision of H1 before validation starts; it is not used to change endpoints. It checks:
- floor: at least half the development branches complete step 1;
- instrument health end to end: patch, build, tests, measurement and ledger;
- context-bound exclusions.

Instrument defects found here are fixed before the freeze. Calibration outcomes are never used to select, rank or exclude validation targets, and calibration tokens are charged.

## 10. Feasibility audit (no model calls)

Preliminary checks, 5 October 2026; details are stored outside the repository in `z:\rayen\reaccrual\bouw-feasibility\`:
- The detector loads the solution and reports GC and LM findings at HEAD.
- Many flagged files have several later focused commits that also change test files.
- One business-logic test project builds and passes in about a second.

These figures use HEAD findings and any test-file change in the same commit, so they **overestimate** eligibility. The audit must establish the real counts:

1. For each candidate file, replay its post-break commits and identify fail-to-pass tests per commit (Section 4.1). This needs builds and test runs per commit but no model calls.
2. Confirm that the target is flagged at each candidate t0.
3. Record test projects that need external services.
4. Report eligible targets per type and band, the attainable N_A, the SESOI (Section 8.2) and the context-bound exclusions.

**Audit attempt, 5 October 2026 (no model calls).** The audit tooling is [feasibility_audit.py](feasibility_audit.py) and [summarise_audit.py](summarise_audit.py).
- The git-level stage found candidate files with runs of at least two consecutive focused commits that also change tests, which gives 121 commits to build and test.
- The build stage was **blocked by package access, not by history**. Historical commits pin older versions of internal packages (the Ibis.* family on the organisation's authenticated Azure DevOps feed, and licensed vendor feeds). Those versions are not in the local NuGet cache. Only 9 of the 121 commits have every private package version cached, which leaves too few files with a restorable run of K ≥ 2.
- The user then authenticated the private feeds, and old commits now restore and build. Credentials are never handled by the tooling.
- Instrument corrections made before any final count. Each is recorded so that earlier partial runs, archived as invalid, are not reused:
  1. Compiler errors are classified from the full build output, not its tail.
  2. Test projects are those referencing the target's production project, plus test projects changed by the commit, rather than only the latter. One test project is a test-free helper library.
  3. Each test project's `bin`/`obj` is removed before every commit, after stale output from later revisions made older test projects discover zero tests.
  4. A test name counts as passed only if all its data rows passed.
  5. Stub-kind fail-to-pass steps were added (amendment 0.2.1).
  6. The database-integration test project is excluded under Section 6.2: it requires SQL Server, and most of its tests do not execute without it.
- An interim review of the first 39 commits found three issues:
  - Most steps fail only at compilation. Stubbing gives a behavioural oracle for about one third of those steps.
  - Under the 28 KB byte-based context rule, 12 of 15 targets are excluded. In real tokens nearly all would fit.
  - The developers' changes in these windows add a median of zero decisions per change.

  These issues require protocol decisions after the audit completes: a token-based context bound, a fixed SESOI floor, and a descriptive report of the change types in the windows.

**Final audit, 5 October 2026 (all 121 commits, no model calls).** Excluded test projects: database integration, end-to-end UI automation (launches the application), and the WinForms UI test project (excluded at the user's request; it opens dialogs). The same exclusions apply to every commit.

Step outcomes over 266 candidate steps:

| Kind | Steps |
|---|---|
| Test kind | 15 |
| Stub kind | 53 |
| Unchecked | 67 |
| No effect | 131 |

Results by oracle rule:

| Rule | Windows | Flagged at t0 | Within 32k tokens | God Class / Long Method (within 32k) | Window lengths (within 32k) |
|---|---|---|---|---|---|
| Developers' own tests only | 16 | 14 | 8 | — | — |
| Option B (unchecked steps get oracle tests) | 30 | 27 | **21** | 13 / 8 | 15 × K=2, 3 × K=3, 3 × K=4 |

- Under the 32k-token bound, option B needs 29 oracle test classes. Five of those steps have no stubbable member and cannot be validated, which removes two targets and leaves **19 eligible targets**, minus two for calibration.
- In the 21 windows, developer accrual per change has median 0 decisions (range −12.5 to 6) and median +2 code tokens (median absolute value 12.5).
- The developers' tests alone do not meet the threshold below. Option B does, subject to oracle-test admission.

**Oracle-test authoring, 5 October 2026 (no maintenance-agent call).** Of the 29 packages within the 32k-token bound:
- 5 had no stubbable member and were not attempted.
- Claude Sonnet 5.5 reported 12 as not deterministically testable. These are data-layer classes reachable only through FoxPro or SQL databases or the file system, or call-path refactors with no observable effect.
- Sonnet wrote 12 classes. All 12 passed the automatic checks, one after its single retry (missing service registration in the test setup).

Eligible windows after admission: **15 targets (9 God Class, 6 Long Method)**, with 13 at K=2, 1 at K=3 and 1 at K=4. All windows keep their original t0. After removing two God Class calibration targets, **13 validation targets remain (7 God Class, 6 Long Method)**. This meets the threshold below, subject to human review of the 12 admitted classes.

**Go/no-go.** Stratum A proceeds if, after oracle-test admission, at least 12 eligible validation targets with K ≥ 2 remain, of which at least 4 are God Class and at least 4 are Long Method. Otherwise stratum B becomes primary: H2 is confirmatory there and H1 is reported as not testable. That outcome is reported as such.

## 11. Resources

The shared cumulative maintenance ledger (`../budget-ledger.json`) currently authorises 672,000 tokens, with 342,178 remaining. This is insufficient. Planning estimates, to be replaced by the audit's per-target prompt sizes:

| Phase | Expected tokens |
|---|---:|
| Calibration: corpus development targets plus 2 stratum-A targets × 3 O trajectories | ~0.6M |
| Stratum A, 17 validation targets: acquisition ≤3 attempts each, plus (3 O + 1 R trajectories) × mean K ≈ 2.5 steps × about 1.3 calls × about 21k tokens per call | ~6.5M |
| Stratum B, 21 targets × 2 branches × 4 steps | ~1.3M |

Enforcement:
- Each O and R branch has the same allocation A_branch: 160,000 tokens in stratum A and 100,000 in stratum B.
- A call is made only if the branch's spent tokens plus the call's conservative reservation are within A_branch.
- A target block starts only if the remaining ceiling covers both of its branches' allocations and any pending acquisition attempts.
- Missing usage, a reservation violation or a context rejection stops the campaign until it is reconciled. No automatic retries.

The required cumulative ceiling is about 9M tokens, including the 329,822 already used and the headroom for the last admitted block. Oracle-test authoring uses a different provider and is accounted separately as research infrastructure. The user sets the actual ceiling, and N_A is reduced to fit it before the freeze, never after outcomes.

## 12. Implementation and gates

Build test-first under `../tests`:
1. a historical replay harness (per-commit worktree, target-file substitution, fail-to-pass identification, test execution);
2. a cumulative branch runner (state carry-over, alternation, stop rule, allocations, per-call records);
3. the stratum-B task builder and admission (G1–G5);
4. per-step structural measurement for solution-loaded states (Bouw) and corpus states, cached by state hash;
5. analysis for P1, P2 and the secondaries, using exact sign-flip, Holm and Kaplan–Meier with no new dependencies, checked on synthetic fixtures with known answers;
6. offline replay of saved outputs (no model resampling).

Implementation status, 5 October 2026 (no model calls). The following modules are implemented, with 53 unit tests:
- `replay_core.py`, `replay_prepare.py`, `replay_run.py`, `replay_ledger.py`, `replay_analyze.py`, `recurrence.py` and `acquire_repairs.py`;
- `src/HybridLens.ChangeStub` (`--missing-api`) and `src/HybridLens.DesignQuality` (`--file-metrics`), each with fixture checks.

Stub-provider instrument checks on the draft manifest (15 targets):
- Replaying the developers' own target-file change completed **33 of 33 steps**.
- A no-op edit completed **0 of 15 first steps**: 14 rejected at build and 1 at fail-to-pass. The no-op check mainly exercises the build gate. Behavioural sensitivity rests on stub-sensitivity admission of every fail-to-pass set.
- Live provider calls go through the shared ledger (reserve before each call, reconcile after) and are refused while `replay_settings.json` has `live_execution_enabled: false`.
- Repair acquisition, the live path and the P1 detector stage have not been run end to end, because they need model calls or accepted repairs.

| Gate | Condition |
|---|---|
| G-AUDIT | Feasibility audit complete; oracle tests admitted, reviewed and frozen (ORACLE_TEST_SPEC.md); go/no-go decided on the admitted windows; validation and calibration targets fixed. |
| G-TASK | Stratum-B sequences authored by R2 and admitted; authorship record kept. |
| G-CAL | Calibration passed and instrument fixes completed. |
| G-INST | Unit tests and synthetic fixtures pass; a stub-model dry run on a development target produces the expected records. |
| G-LEDGER | Ceiling authorised; block admission check passes. |
| G-FREEZE | Freeze record: targets, windows, exclusions, task and test hashes, prompts, context lists, settings, seed, SESOI, runner/evaluator/measurement/analysis hashes, SDK and package locks, starting ledger state. |

## 13. Deviations and reporting

- Every departure from the frozen protocol is logged with a date, reason and whether outcomes had been seen. Outcome-dependent changes to targets, windows, tasks, thresholds, endpoints or allocations are not permitted.
- Report every selected target, including acquisition failures, censored branches and excluded steps, and per-target trajectories of D, findings, L and tokens.
- Development, calibration, stratum A and stratum B are reported separately.

## 14. Remaining limitations

These cannot be removed by any affordable design and are reported as scope:

- **Agent, not developers.** Results describe what the specified model does under this contract. They do not measure human effort or comprehension.
- **Structural proxies.** Decision burden and detector findings stand in for debt; they are not interest measured in time or defects.
- **One model and one contract.** Single-file patches, no navigation, no test feedback, neutral instructions. Other agents may behave differently.
- **Historical requirements are imperfect specifications.** Commit messages and work items can underspecify a change. This affects O and R equally, but can lower completion and shorten the steps available for comparison.
- **Selection by testability.** Replay requires commits with fail-to-pass tests, which favours better-tested parts of the system.
- **One organisation's history** for stratum A, and a constructed corpus for stratum B.
- **Not future change frequency.** Replay fixes the change sequence, so the study cannot show whether a repair would change how often code is changed. That requires an adopted repair in a live project.

## 15. What each outcome would mean

- **Durable repairs (low P1) and H2 supported:** LLM repairs keep their quality under later LLM maintenance and lower the complexity each change adds. This is evidence that verified repair reduces debt interest, conditional on this agent.
- **Recurring repairs (high P1):** verification is a temporary property of LLM output, which supports re-verifying at every change rather than repairing once.
- **H1 supported:** the LLM maintainer writes more code than the developers for the same real changes. This is a quality property of LLM output that point-in-time checks cannot see, and it is measured on private code without training exposure. H1b shows whether the extra code also adds decision logic.
- **H1 reversed:** the LLM maintainer is as economical as or more economical than the developers, which challenges observational claims of AI-driven bloat.
- **H2 null with equivalence:** the repair does not change how much complexity later changes add.
- **Inconclusive:** reported with the attained precision.
