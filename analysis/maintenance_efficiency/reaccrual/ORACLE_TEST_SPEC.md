# Oracle test specification for unchecked replay steps

Version 1.0, 5 October 2026. Applies to protocol v0.3, option B (Section 4.1). Tests written under this specification must be written, validated and frozen **before any maintenance-agent model call**. The specification is generic. Per-step work packages contain proprietary source and are stored outside this repository.

## Purpose

A replay step is *unchecked* when none of the developers' own tests fails if the members changed by the commit are stubbed to throw. In that state, the replay cannot judge whether a maintenance agent made the change correctly. For each unchecked step in an eligible replay window, a supplementary **oracle test class** is written. The class checks the behaviour that the commit introduced or changed. Once validated, the class joins the developers' tests as part of that step's oracle.

The tests are oracle material for evaluating the agent branches. Every agent branch is judged by the same tests. The tests are derived from the developers' historical change, never from any agent output.

## Author and inputs

Tests are drafted by Claude Sonnet 5.5 (a different model family from the maintenance agent, gpt-5.6-sol). A human reviews every draft before it is frozen. The author receives exactly one work package per step, containing:

- `step.json`: step ID, commit, date, commit subject, target file, target test project, changed members (the stubbed member list), changed caller files, and the existing test files changed by the commit;
- `target.pre.cs` and `target.post.cs`: the target file before and after the commit;
- `target.diff`: the commit's diff of the target file;
- `callers/`: the commit's post-commit versions of other non-test source files it changed;
- `existing-tests/`: the post-commit versions of test files the commit changed, as style examples only.

The author may read any file of the repository at the post-commit revision for context. One author session may handle several work packages. The author never receives any maintenance-agent output, and receives harness output only for its own retry (see Automatic validation).

## Deliverable

One C# file, `Step_<ID>.cs`, containing exactly one public test class:

```csharp
namespace Reaccrual.Oracle;

[TestClass]
public sealed class Step_<ID>
{
    [TestMethod]
    public void <Behaviour>_<Condition>_<Expected>() { ... }
}
```

It is placed in the work package's designated test project (`step.json: test_project`) by the harness, not by the author. Existing files are never modified. Use the project's framework and conventions: MSTest, Moq, and the shared builders and helpers already referenced by that test project. No new packages.

## Rules

1. **Behaviour, not implementation.** Assert observable results only: return values, state readable through accessible members, thrown exception types, and calls made to injected collaborators that represent external dependencies. Do not assert which internal helper is called, how work is split between methods, or private state. Do not use reflection on non-public members. A different correct implementation of the same change must pass.
2. **Cover the change.** Every changed member listed in `step.json` that has observable behaviour should be exercised by at least one test method. Include the commit's main case and at least one boundary or alternative case where the diff shows one, for example a new condition, a new parameter value or a new branch.
3. **Concrete expectations.** Use literal expected values derived by reasoning about the post-commit code on concrete inputs. Never recompute the expectation with logic copied from the implementation.
4. **Deterministic and isolated.** No current time, random values, file system, network, database, registry, environment variables, UI windows or dialogs, sleeps or ordering dependencies between tests. Replace such dependencies with the existing seams (constructor injection, interfaces, builders) or test a lower-level member that does not need them. If a behaviour cannot be tested without them, say so in the report instead of writing a fragile test.
5. **Size.** 2–6 test methods, at most about 200 lines.
6. **Accessibility.** Production assemblies expose internals to their test projects. Internal members may be used. Private members may not.
7. **No weakening.** No `[Ignore]`, no empty tests, no assertions that cannot fail, and no catch-all exception handling around the code under test.

## Report

Return a short report with the file, listing each test method, the changed member and behaviour it targets, and any changed member deliberately left untested with the reason.

## Automatic validation (harness, before human review)

A test class is **admitted** only if all of the following hold:

| Check | Requirement |
|---|---|
| Static guard | No forbidden constructs from rule 4, no `[Ignore]`, no reflection on non-public members, exactly one class `Reaccrual.Oracle.Step_<ID>` |
| Post-commit | Compiles in the designated test project at the commit; every test method passes, in two consecutive runs |
| Stub sensitivity | With the commit's changed members stubbed to throw (`src/HybridLens.ChangeStub`), **at least one** test method fails |
| Retention | Tests are re-run at each later step's post-commit state in the same window. A test that still passes there is retained for that step; one that fails because of an intentional later change is retired at that step and recorded. |

A class that fails any check goes back to the author once, with the harness output. A second failure leaves the step unchecked, and the window is cut at that step.

## Human review

The reviewer checks rules 1–3 against the diff. Does each test check behaviour the commit actually introduced or changed? Would a correct alternative implementation pass? The reviewer may delete over-specified assertions, or reject the class. The reviewer records accept, edit or reject per class. Edits are re-validated by the harness. The reviewer does not see any agent output, since none exists before the freeze.

## Freeze

Admitted and reviewed classes are hashed, and their hashes enter the protocol's freeze record. After the freeze, no oracle test is added, edited or removed for any reason linked to agent outcomes.

## Reporting

The thesis reports the number of steps that needed oracle tests, how many were admitted on the first and second attempts, reviewer edits and rejections, and a sensitivity analysis restricted to steps checked only by the developers' own tests. Model-authored oracle tests are a stated limitation, mitigated by: a different model family from the agent, behaviour-only rules, stub-sensitivity validation, human review, and freezing before any agent run.
