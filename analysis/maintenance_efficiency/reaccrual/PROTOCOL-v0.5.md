# Shadow loop on industrial history: protocol v0.5

Version 0.5, 6 October 2026. Status: **approved by the thesis author and frozen on 6 October 2026, before any v0.5 model call.** The feasibility audit in Section 8, the preparation and the stub checks used no model calls. v0.3 (`PROTOCOL.md`) and v0.4 (`PROTOCOL-v0.4.md`) remain the records of the completed studies. Decisions taken at approval: R2 reviews every accepted candidate (Section 7.2), and the WinForms UI test project stays excluded (Section 8.6).

## 1. Motivation and disclosure

- **v0.4 (constructed corpus).** Feeding the static analyser's findings back after each maintenance change removed all newly introduced God Class and Long Method findings (0 of 21 targets, against 12 of 21 under neutral maintenance), and every one of the 19 restructurings it triggered passed all gates.
- **v0.3 stratum A (Bouw history).** The agent matched the developers on small, real changes. Repairs of long-standing debt, acquired at an old commit, succeeded in 6 of 13 targets: 5 of 6 Long Method targets and 1 of 7 God Class targets.
- **The gap.** Nothing yet shows that the continuous loop works on industrial code, where the debt is introduced by real developers and the test suite is the only oracle. v0.5 asks whether a quality call made at the moment a developer commit introduces a Long Method can remove it safely.
- **Disclosure.** v0.5 was designed after the v0.3 and v0.4 outcomes were known, and is motivated by them. The sampling frame (Section 5) was built from a git-history audit that used no model calls. The "ordinary commit" bound was chosen after seeing the distribution of introductions across commits (Section 8.2), before any intervention outcome existed. Its outcome is unknown.

## 2. Research questions and hypothesis

- **RQ7.1 (descriptive).** How often do ordinary developer commits introduce Long Method debt, and how long does it survive? Answered by the audit (Section 8).
- **RQ7.2 (confirmatory).** At the moment a developer commit introduces a Long Method, can the v0.4 quality call remove it without breaking the build, the public API or the existing tests?
- **RQ7.3 (descriptive).** How does this compare with fixing debt late (v0.3 repair acquisition), and what does the fix cost?

The primary result is an **estimate**: the proportion p of oracle units (Section 5) whose introduced Long Method findings are all removed with every gate passing (Section 4.3), reported with an exact Clopper-Pearson 95% interval.

**Why the primary result is not a hypothesis test.** An earlier draft proposed a one-sided exact test of H0: p ≤ 0.75. A first oracle pilot suggested that only about 17 of the 48 frame candidates would have an oracle, and with 17 units that test needs 100% observed success to reject (power 0.17 if the true rate is 0.90). The full oracle check (Section 8.4) later found 33 oracle units, because two environment problems had depressed the pilot, but the rule below had already been written. The interval stays the primary result. The pre-specified reading is:
- the lower bound above 0.5 means that the fix usually works at introduction time;
- the upper bound below 0.5 means that it usually does not;
- anything else is inconclusive.

Context for the reader: the v0.4 corpus accepted 19 of 19 restructurings, and late acquisition on Bouw Long Method targets accepted 5 of 6.

**Secondary test.** The population has reached 30 units, so a one-sided exact test of H0: p ≤ 0.75 at α = 0.05 is added as a pre-specified secondary analysis. With 33 units it needs 30 successes (91%), and its power is 0.58 if the true rate is 0.90 and 0.25 if it is 0.85. Its p-value is reported but not used to claim support.

**What success means.** Section 8.4 shows that none of the oracle test code mentions any type declared in the 33 unit files. The tests gate is therefore a regression check on dependent code, not evidence that the unit file's own behaviour is preserved. A success means that the candidate builds, keeps the API, removes the finding, adds no new debt and leaves the existing suites green; it does not mean that the behaviour is unchanged. Behaviour preservation is assessed only by the review in Section 7.2.

## 3. Design overview

A **unit** is one developer commit that introduces at least one Long Method into one production file. For each unit, the post-commit file is given to the model with a quality call, and the result is judged by gates that need no human. There is no control arm: the question is whether the intervention works in place, not whether it beats an alternative. Section 7.4 gives a descriptive comparison with late repair acquisition.

## 4. Units, intervention and gates

### 4.1 Units

- **Source.** Non-merge, single-parent commits of the Bouw history, from the introduction audit (Section 8).
- **Ordinary commit.** A commit that changes between 1 and 10 production C# files. Bulk imports and restructurings are excluded. The bound was fixed after the audit (Section 1); 3 and 30 are sensitivity analyses.
- **Production file.** A `.cs` file outside any path segment containing "test", and not generated (`.Designer.cs`, `.g.cs`, `.generated.cs`).
- **Introduction.** A method of a file is a genuine Long Method introduction at a commit when, in the post-commit file, its symbol (`Type.Method`) has cyclomatic complexity above 10 under the thesis detector's rule, and in the pre-commit file it did not. Symbols that moved or were renamed within the commit are not introductions: a relocation is the same symbol leaving another changed file; a rename is a method that stopped being long in the same commit with the same complexity and a line count within 2.
- **Unit file and findings.** Each qualifying commit contributes one unit. The unit's file is the file of its most complex introduced method (ties by symbol name). The unit's findings are all genuine Long Method introductions in that file at that commit.

### 4.2 Intervention

The quality call of v0.4 Section 4.2, applied to the post-commit file:
- the existing `gpt-5.6-sol` deployment, a fresh conversation, and strict JSON line patches restricted to the unit file;
- at most one call, plus one retry after an invalid patch or a build failure that carries compiler diagnostics only. Test names and outcomes are never shown;
- an output cap of 16,384 tokens per call, and a per-unit allocation of 120,000 tokens;
- the prompt holds the developer's commit message in place of "the change just implemented", the unit's findings in the thesis's grounded finding format (type, symbol, line, metrics and thresholds), the v0.4 instruction text, and the numbered editable file. No other file is provided.

### 4.3 Gates and success

A unit **succeeds** when the candidate file passes every gate, in order:
1. **Build.** The whole solution builds at the post-commit state with the candidate file substituted.
2. **API.** The candidate preserves the assembly-visible API of the post-commit file, including the internal members used elsewhere.
3. **Tests.** Every test that passes at the post-commit state in the oracle projects still passes. The oracle projects are the non-excluded test projects that reference the file's project; the database-integration, WinForms-dialog and end-to-end projects are excluded exactly as in v0.3. Test projects that target an older runtime are run with roll-forward to the installed runtime, identically at the post-commit state and for the candidate. This gate is a regression check on dependents (Section 2).
4. **Resolved.** None of the unit's introduced symbols is still a Long Method finding in the candidate file, judged by the exact-symbol rule of v0.3 (not by the verifier's name-overlap matching).
5. **No new debt.** The candidate file has no Long Method or God Class finding that the post-commit file did not have.

Gates 4 and 5 are evaluated by the CLI analyser on the whole solution. Units whose introduced symbol the CLI analyser does not report at the post-commit state are ineligible; the audit's syntax-only detector disagreed with the CLI on 4 of 936 methods in a check on one commit, because of files outside the projects' compile sets.

## 5. Sampling frame and eligibility

Eligibility filters apply in this order, and are all decided without any model call:
1. an ordinary commit with a genuine Long Method introduction (Section 4.1);
2. the post-commit unit file is at most 32,000 estimated tokens (3.5 UTF-8 bytes per token), as in v0.3. The resulting size bias is reported;
3. the post-commit solution builds, and the CLI analyser reports the introduced symbol (Section 4.3);
4. an oracle exists: at least 10 tests pass in the oracle projects at the post-commit state.

The frame is hash-ordered within strata (introduction subtype × complexity band), with SHA256(`reaccrual-v0.5` | commit | symbol). **All units that pass filters 1-3 are run (a census), up to a maximum of 48.** Two populations are reported separately:
- **Oracle units (population A)** pass filter 4 as well. This is the primary population, and the only one whose success includes the tests gate.
- **Static-only units (population B)** pass filters 1-3 but have no oracle. Their success means only that the candidate builds, preserves the API, removes the finding and creates no new debt. It says nothing about behaviour, and is reported as a secondary result under that label.

A unit that fails filter 3 is reported in the funnel, never replaced and never counted as a failure. The full oracle check (Section 8.4) fixed the populations before any model call: 36 units pass filters 1-3, of which 33 are in population A and 3 in population B.

The unit file lies in the UI layer for 28 of the 48 candidates, and in the business layer for 6, the data layer for 9 and elsewhere for 5. The UI test project is excluded as in v0.3 (it opens WinForms dialogs). The test projects that remain reference most UI files transitively, so UI units have an oracle (20 of 22 that build), but Section 8.4 shows that this oracle does not test the unit files themselves.

## 6. Gates and implementation

- **G-AUDIT.** The audit and the oracle pilot are complete (Section 8). The frame is fixed before any call.
- **G-ORACLE.** Filters 3 and 4 are run for every frame candidate. This uses no model calls and fixes the final unit list before the freeze. Done on 6 October 2026 (Section 8.4): 48 candidates, 36 in the study, 33 with a dependents' regression suite.
- **G-INST.** The runner has unit tests. Three stub providers check the instrument on all 36 units, with no model calls: identity (the file returned unchanged) must pass the build, API and tests gates and fail the resolved gate; truncate (the closing line removed) must fail the build gate; revert (the parent version of the file) is a positive control that can succeed. Done on 6 October 2026 (Section 8.5): identity failed at `resolved` on all 35 eligible units with every earlier gate passing, which also shows that every unit's reference suites are stable across reruns; truncate failed at `build` on all 35; revert succeeded on 13 units, and failed at build on 16, at API on 2 and at no-new-debt on 4.
- **G-LEDGER.** About 0.7-0.9M tokens are projected (36 units, a median input of 10-15k tokens, an output of 1-4k, and a retry allowance). A ceiling of 1.0M is reserved within the existing authorisation.
- **G-FREEZE.** `freeze-v0.5.json` hashes the unit list, the post-commit file hashes, the commit messages, the oracle results, the prompt texts, the code, the settings and this protocol.

## 7. Endpoints and analysis

### 7.1 Primary

The success proportion over the oracle units (population A), with an exact (Clopper-Pearson) 95% interval and the reading of Section 2.

### 7.2 Secondary

- The static-only success of population B (Section 5), and of A and B together, labelled as having no behavioural check.
- **Behaviour-preservation review.** Because no test exercises the unit files (Section 8.4), the second corpus reviewer (R2) judges every accepted candidate from the diff against the post-commit file: behaviour-preserving restructuring, not behaviour-preserving, or cannot tell. The judgement uses the requirement-free diff only and is recorded before any other outcome is shown. The result is reported as the share of accepted candidates judged behaviour-preserving, with an exact 95% interval, and states that it rests on human review.
- Whether a unit's oracle test code mentions a type declared in the unit file (0 of 33 in the audit; Section 8.4).
- The gate flow: built, API preserved, tests passed, resolved, no new debt.
- The failure stage per unit, and success by stratum (crossing versus new method; complexity band).
- Tokens per unit and per success, calls per unit, and wall time.
- Edit footprint: lines and C# tokens changed.
- **Gaming checks (descriptive).** The change in file decision burden and the count of methods with complexity 8-10 and above 10 before and after the fix. A fix that only trims a method to complexity 10 is reported as such.
- Persistence: for the unit methods, the share still long at the repository head in the developers' own later work (from the audit).

### 7.3 Sensitivity analyses

1. The first call only, excluding retries.
2. Commits with at most 3 production files, and at most 30.
3. Excluding units whose commit also changed test files.
4. Complexity 11 versus 12 and above.
5. Crossing versus new-method introductions.
6. Success counted without gate 5 (new debt), to show how often a fix trades one finding for another.
7. **One unit per file.** Units are not independent: the same file, and sometimes the same method, crosses the bound at several commits (Section 8.5). The primary interval treats units as independent, so the analysis is repeated with one unit per file, taking the first unit of each file in hash order, and with the file as the cluster in a bootstrap interval.

### 7.4 Comparison with late acquisition (descriptive only)

v0.3 acquired repairs for old, accumulated debt, with up to three independent attempts per target and whole-file replacement, and accepted any attempt that passed. v0.5 makes one attempt (plus a retry) with line patches on debt that is minutes old. The populations, instruments and sizes differ, so this comparison cannot be causal. It is reported as an observation, with the instrument differences stated. Late acquisition succeeded for 5 of 6 Long Method targets and 1 of 7 God Class targets.

### 7.5 God Class

The syntax-only audit can only bound God Class introductions from above (WMC of 47 or more). They are described in Section 8, and are not part of the primary result. A God Class arm is run only if the full detector confirms at least 8 introductions that also pass filters 2-4. Its result would be descriptive.

## 8. Feasibility audit (no model calls)

### 8.1 Instrument

- `HybridLens.DesignQuality --history-metrics` computes, syntax-only, the cyclomatic complexity of every method with the thesis detector's rule and class WMC with the same formula. It was validated against real detector output. On the thesis corpus the Long Method findings were identical (13 of 13, symbol and complexity), and class WMC matched on every God Class. On one Bouw commit, all 932 detector Long Method findings were reproduced; four extra methods came from files outside the projects' compile sets (0.4%).
- `introduction_audit.py` walks every non-merge single-parent commit, measures each changed production file before and after, keys findings by symbol, and classifies each new finding as genuine, relocation or rename.

### 8.2 History

- The repository has 3,482 commits, 2,333 of them non-merge with a single parent. C# production changes occur only from November 2022 to October 2024 (1,617 commits); earlier history holds no C# production files.
- **Bulk commits distort the counts.** Over all commits there are 2,064 apparent genuine introductions in 120 commits, but four bulk commits (80 to 1,080 production files; a migration and a restructure) account for about 1,900 of them. These are not developer changes.
- **Ordinary commits** (at most 10 production files) number 1,358. They contain 122 raw Long Method introductions, of which 50 (41%) are renames and none are relocations, leaving **72 genuine introductions in 66 commits** (4.9% of ordinary commits). Of the 72, 39 are existing methods that crossed the bound and 33 are new long methods. By complexity: 11 (33), 12-14 (23), 15-19 (9), 20 and above (7). By year: 2022 (3), 2023 (32), 2024 (37).
- Sensitivity bounds: at most 3 files gives 36 commits and 36 introductions; at most 30 files gives 87 commits and 100 introductions.
- **Persistence.** 38 of the 72 introduced symbols (53%) are still Long Methods at the repository head, matched by symbol. This is an upper bound on persistence, because a renamed method would not match.
- **Tests.** Only 1 of the 72 introducing commits also changes test files. Developers rarely add tests with these changes, so the existing suite, not the commit's own tests, is the oracle.
- **God Class.** The syntax-only bound finds 26 WMC crossings in 22 ordinary commits (14 crossing, 12 new class). The ATFD and cohesion conditions need the full detector.

### 8.3 Frame

Of the 66 commits with a genuine introduction, 48 satisfy the 32,000-token bound for the unit file (18, or 27%, are larger). The 48 candidates fall into these strata (subtype and band):

| Stratum | Units |
|---|---|
| crossing, 11 | 15 |
| crossing, 12-14 | 10 |
| crossing, 15-19 | 2 |
| new method, 11 | 4 |
| new method, 12-14 | 7 |
| new method, 15-19 | 4 |
| new method, 20 and above | 6 |

By year they split 2022 (1), 2023 (16), 2024 (31). The run is therefore close to a census of recent, mid-complexity introductions, and says little about 2022 or about very complex Long Methods in older files.

### 8.4 Oracle check

Every candidate was checked out at its post-commit state in a disposable clone and built as a whole solution with the root-solution and local-cache package configuration of v0.3. The test projects that reference the unit's project were then run, with the database-integration and WinForms-dialog projects excluded.

**A first pass was invalid, for two environment reasons, and was redone.**
- The older test projects target net6.0, but only runtimes 8 and later are installed. The test host could not start ("Test Run Aborted"), so 12 built units looked as if they had no tests. The oracle check now runs them with roll-forward to the installed runtime. A project that reported no tests then ran 228 tests, all passing.
- Seven post-commit states failed to restore because the repository's configuration lists package feeds on a developer machine (`C:\LocalPackages` and one other drive path) that do not exist here. The check now disables a configured feed when its drive path does not exist.
- A 14-unit pilot made before these fixes suggested 17 oracle units (95% interval 6-31); the corrected check found 33. The first pass is kept for the record.

**Result (all 48 candidates, no model calls).**

| Stage | Units |
|---|---|
| Frame candidates | 48 |
| Solution builds | 36 (75%, 95% interval 60-86%) |
| Oracle: at least 10 passing tests | 33 (69%, 95% interval 54-81%) |
| Built, but no test project references the project | 3 |
| Does not build | 12 |

- **Build failures (12).** Nine post-commit states do not compile in this environment (missing types or an unimplemented interface member). Whether the developers' own builds were also broken at those commits is not known. One needs a strong-name key file that is not in the repository, and two failed with no compiler error recorded. These units stay in the funnel and are not counted as failures of the intervention.
- **Oracle units (33).** 20 are UI-layer files, 4 business-layer, 6 data-layer and 3 elsewhere. They have between 212 and 756 passing tests in the referencing test projects (mostly 224-230 or 587 and more). 27 are from 2024 and 6 from 2023, so the study says little about 2022 or about the oldest legacy files.
- **By stratum (units with an oracle / built / candidates).** crossing 11: 12/13/15; crossing 12-14: 8/8/10; crossing 15-19: 2/2/2; new method 11: 3/3/4; new method 12-14: 2/3/7; new method 15-19: 2/2/4; new method 20 and above: 4/5/6.

**The oracle does not test the unit files.** For each unit, the check looked for any type declared in the unit file as a whole word in the oracle projects' source at the post-commit state. This was true for none of the 33 oracle units: no test code in the oracle projects mentions a type declared in any of the 33 files. This holds in the business and data layers too, where direct tests would be expected. A spot check confirmed it: the types of two business-layer units appear in only two or three source files each, none in a test project. Indirect execution through other types is possible, but the audit cannot show it.

The oracle is therefore a regression suite for dependent code. It can detect a candidate that breaks something that depends on the unit file, but not that the unit file's own behaviour changed. The hidden-test and fail-to-pass machinery of v0.3 has no counterpart here.

### 8.5 Preparation (no model calls)

`v05_run.py prepare` captured, for each of the 36 units that build, the post-commit file, the parent file, the commit message, the reference test outcomes of the oracle projects, and a baseline scan of the whole solution with the CLI analyser.

- **35 units are eligible**: the CLI analyser reports the introduced symbol at the post-commit state. One UI-layer unit is not reproduced (the symbol is not reported), and is ineligible by filter 3.
- **32 of the 35 have an oracle** (the reference suites hold between 212 and 756 passing tests); 3 have none and form population B.
- **Units are clustered.** The 36 units lie in 26 distinct files. Six files hold 16 units (one file holds five), and four methods cross the bound at more than one commit, which means that they went back under the bound and were pushed over it again. The exact interval of Section 7.1 assumes independence, so sensitivity analysis 7 repeats it with one unit per file.
- **Instrument check results (Section 6).** Identity, truncate and revert behaved as specified on all 36 units (35 eligible); the revert control succeeded on 13 units.
- **Case of folder names.** The scanner reports a folder as `UI`, while the history spells it `ui`, depending on which commit the clone last had checked out. Paths are matched without case. The first preparation run missed all UI units because of this, and was redone.

### 8.6 Consequences for the design

1. The primary result is an interval (Section 2). The secondary test applies, because the population reached 30.
2. Success is defined by automatic gates and does not claim behaviour preservation (Sections 2 and 4.3).
3. R2 reviews every accepted candidate for behaviour preservation (Section 7.2). This is the only behavioural evidence in the study.
4. A decision remains for the thesis author: running the WinForms UI test project on this machine as an additional oracle for UI units. It opens dialogs and was excluded in v0.3, so v0.5 keeps the exclusion unless that decision changes before the freeze. Given that no oracle test mentions a UI-layer unit file, it is unlikely to help unless it tests the dialogs directly.
5. A stronger oracle would need new characterisation tests written at the post-commit state. That is outside this protocol.

## 9. Limitations

- One codebase, one model, and one prompt wording, over mostly 2023-2024 history.
- The quality call sees only the unit file. Allowing context files, or a larger output budget, could raise success.
- The automatic oracle is a regression suite for dependents. None of its test code mentions a type declared in a unit file (Section 8.4), so a fix that passes may change the unit file's own behaviour. Only R2's review addresses that. Only 1 of the 72 introducing commits changed any test file.
- The oracle population is 33 units, mostly from 2024 and mostly UI-layer files, so the primary interval is wide and the result says little about older code.
- The syntax-only audit is exact for Long Method but cannot confirm God Class. The rename heuristic may discard a few real introductions.
- The ordinary-commit bound and the 75% bar are design choices made after seeing the audit and the earlier results (Sections 1 and 2).
- The 32,000-token bound removes 27% of the units, which are the large legacy files.

## 10. Deviations and reporting

As in v0.3 Section 13:
- every departure is logged with its date and reason, and whether outcomes had been seen;
- every unit and every funnel stage is reported, including units that are ineligible, and the failure stage of each unit;
- v0.3, v0.4 and v0.5 are reported separately, and the results use only aggregate descriptions of the proprietary code.
