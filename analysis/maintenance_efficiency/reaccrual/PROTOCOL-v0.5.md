# Shadow loop on industrial history: protocol v0.5 (draft)

Version 0.5-draft, 6 October 2026. Status: **draft, not frozen; no v0.5 model call has been made.** The feasibility audit in Section 8 used no model calls. v0.3 (`PROTOCOL.md`) and v0.4 (`PROTOCOL-v0.4.md`) remain the records of the completed studies.

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

**Why there is no hypothesis test.** An earlier draft proposed a one-sided exact test of H0: p ≤ 0.75. The oracle pilot (Section 8.4) showed that only about 17 of the 48 frame candidates will have a test oracle (95% interval 6-31). With 17 units the exact test needs 100% observed success to reject, and its power is 0.17 if the true rate is 0.90 and 0.42 if it is 0.95. A confirmatory test would be uninformative, so none is registered. The interval is the result. The pre-specified reading is:
- the lower bound above 0.5 means that the fix usually works at introduction time;
- the upper bound below 0.5 means that it usually does not;
- anything else is inconclusive.

Context for the reader: the v0.4 corpus accepted 19 of 19 restructurings, and late acquisition on Bouw Long Method targets accepted 5 of 6. If the oracle population reaches 30 units or more, a one-sided exact test of H0: p ≤ 0.75 is added as a pre-specified secondary analysis, and its p-value is reported without being used to claim support.

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
3. **Tests.** Every test that passes at the post-commit state in the oracle projects still passes. The oracle projects are the non-excluded test projects that reference the file's project; the database-integration, WinForms-dialog and end-to-end projects are excluded exactly as in v0.3.
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

A unit that fails filter 3 is reported in the funnel, never replaced and never counted as a failure. The oracle pilot suggests about 31 units that pass filters 1-3, including those in population A (95% interval 17-42), so population B is the difference, about 14.

The unit file lies in the UI layer for 28 of the 48 candidates, and in the business layer for 6, the data layer for 9 and elsewhere for 5. The UI test project is excluded as in v0.3 (it opens WinForms dialogs). The test projects that remain still reference many UI files transitively, so UI units can have an oracle; its power to detect a change in a UI file's behaviour is unknown.

## 6. Gates and implementation

- **G-AUDIT.** The audit and the oracle pilot are complete (Section 8). The frame is fixed before any call.
- **G-ORACLE.** Filters 3 and 4 are run for every frame candidate. This uses no model calls and fixes the final unit list before the freeze.
- **G-INST.** The runner has unit tests. A stub run with an identity provider (returning the file unchanged) must pass the build, API and tests gates on every unit and fail the resolved gate on every unit. A second stub that removes a method body must fail at the build or API gate.
- **G-LEDGER.** About 0.6-0.8M tokens are projected (about 31 units, a median input of 10-15k tokens, an output of 1-4k, and a retry allowance). A ceiling of 1.0M is reserved within the existing authorisation.
- **G-FREEZE.** `freeze-v0.5.json` hashes the unit list, the post-commit file hashes, the commit messages, the oracle results, the prompt texts, the code, the settings and this protocol.

## 7. Endpoints and analysis

### 7.1 Primary

The success proportion over the oracle units (population A), with an exact (Clopper-Pearson) 95% interval and the reading of Section 2.

### 7.2 Secondary

- The static-only success of population B (Section 5), and of A and B together, labelled as having no behavioural check.
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

### 8.4 Oracle pilot

The first two candidates of each stratum (14 commits) were checked out at their post-commit state in a disposable clone. Each was built as a whole solution with the root-solution and local-cache package configuration of v0.3. The test projects that reference the unit's project were then run, with the database-integration and WinForms-dialog projects excluded.

| Stage | Units |
|---|---|
| Checked | 14 |
| Solution builds | 9 (64%) |
| Oracle: at least 10 passing tests | 5 (36%, 95% interval 13-65%) |

- **Build failures (5).** Three post-commit states do not compile in this environment (missing types or an unimplemented interface member). Whether the developers' own builds were also broken at those commits, or whether a package version differs, is not known. One needs a package source that existed only on a developer machine, and one needs a strong-name key file that is not in the repository. The last two are environmental.
- **No oracle although built (4).** In three units the only referencing test project discovered no tests at that commit, and in one unit no test project references the project.
- **Layers.** In the pilot the oracle appeared for UI-layer files (through test projects that reference the UI project) as well as for data-layer files.
- **Extrapolation to the frame.** About 31 of 48 units are expected to build (95% interval 17-42) and about 17 to have an oracle (95% interval 6-31). The pilot is small and stratified two per stratum, so these are rough.
- **Not done.** The full oracle check (G-ORACLE) on all 48 candidates has not been run; it would fix the final population before the freeze.

### 8.5 Consequences for the design

1. The confirmatory test was dropped, and the primary result is an interval (Section 2).
2. Two populations are reported, so that the larger static-only population is not mistaken for evidence of behavioural safety (Section 5).
3. A decision remains for the thesis author: running the WinForms UI test project on this machine, as an additional oracle for UI units. It opens dialogs and was excluded in v0.3, so v0.5 keeps the exclusion unless that decision changes before the freeze.

## 9. Limitations

- One codebase, one model, and one prompt wording, over mostly 2023-2024 history.
- The quality call sees only the unit file. Allowing context files, or a larger output budget, could raise success.
- The tests are the only behavioural oracle. It is defined by test projects that reference the unit's project, not by tests that execute the unit file, so its coverage of the unit file is unknown. A fix that passes may still change behaviour that no test covers. Only 1 of the 72 introducing commits changed any test file.
- The oracle population is small (about 17 units expected), so the primary interval will be wide.
- The syntax-only audit is exact for Long Method but cannot confirm God Class. The rename heuristic may discard a few real introductions.
- The ordinary-commit bound and the 75% bar are design choices made after seeing the audit and the earlier results (Sections 1 and 2).
- The 32,000-token bound removes 27% of the units, which are the large legacy files.

## 10. Deviations and reporting

As in v0.3 Section 13:
- every departure is logged with its date and reason, and whether outcomes had been seen;
- every unit and every funnel stage is reported, including units that are ineligible, and the failure stage of each unit;
- v0.3, v0.4 and v0.5 are reported separately, and the results use only aggregate descriptions of the proprietary code.
