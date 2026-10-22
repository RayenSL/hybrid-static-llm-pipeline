# Stratum B task specification: cumulative requirement sequences

Version 1.0, 5 October 2026. Applies to protocol v0.3, Section 5. The author is the second corpus reviewer (R2). Sequences are written, admitted and frozen **before any maintenance-agent model call**.

## Purpose

Each of the 21 validation targets receives one sequence of **four cumulative requirements**. In the replay, the same sequence is applied to the original code and to an accepted LLM repair of it. The study measures whether the repair stays repaired and how much complexity each change adds, so the sequence should describe how the component's business behaviour plausibly evolves, with changes that add logic.

## What R2 receives and must not see

Per target, a work package under `z:\rayen\reaccrual\stratum-b\<target>\` contains:
- `original.cs`: the target file before any repair;
- `supporting/`: the other source files of the same corpus project, read-only;
- `oracle-drivers.txt`: the private characterisation drivers and golden files (`layer3/characterization`, `layer3/golden`) that exercise this target;
- `steps/S1` to `steps/S4`: empty templates.

R2 must **not** open any repaired source (`analysis/repair_design_quality/generated/sources/`, factorial final sources or campaign traces) or any maintenance-agent output. Requirements and tests are derived only from the original code, its public API and the private oracle. This keeps the sequence independent of how the repair restructured the code.

## Sequence design rules

1. **Four steps per target, cumulative.** Step k assumes steps 1 to k−1 are implemented.
2. **Families.** Each step is one of:
   - F1 variant addition: a new category, case, type or jurisdiction;
   - F2 rule interaction: a new rule that composes with or takes precedence over existing rules;
   - F3 cross-cutting constraint: validation or normalisation across several existing paths;
   - F4 state or side-effect extension: new recorded state, an emitted event, a counter or retry behaviour.

   At least two steps are F1 or F2.
3. **Logic growth.** The cumulative reference after step 4 must add at least one decision point (if, case, conditional, loop or boolean condition) to the target file (gate G5). Prefer requirements that add genuine branching over renames or constants.
4. **Observable behaviour only.** A requirement describes inputs, outputs, state changes and side effects through the existing public API. It never names private members, never prescribes a decomposition, and never asks for a refactoring.
5. **Coherence.** The four steps read as one realistic evolution of the component, in a domain consistent with the existing code.
6. **Superseded behaviour.** If a step intentionally changes behaviour that an earlier case checked, list that case's name in `superseded.txt` for the step. It is then retired from the retained set at that step.
7. **Scope.** Each step must be implementable by editing only the target file, without changing its public signatures. New public members may be added.

## Deliverables per step `steps/Sk/`

| File | Content |
|---|---|
| `requirement.md` | The requirement text, 3–8 sentences, in the style of the existing benchmark tasks. Ends with "Preserve all other behaviour and public APIs; edit only `<file>`." |
| `family.txt` | One of F1, F2, F3, F4. |
| `tests.cs` | Case body using the existing probe format: `Check("case-name", acceptance, () => <bool>);`. Use `acceptance` true for cases of this step's new requirement, and false for regression cases protecting existing behaviour this step could break. The harness supplies the surrounding header and footer and runs the cases against a candidate file. |
| `reference.cs` | The complete target file after steps 1 to k, hand-written from the previous step's reference. It is evaluator material only and is never shown to any agent. |
| `mutant1.cs`, `mutant2.cs` | Two deliberately faulty versions of `reference.cs`, each with one realistic mistake in this step's behaviour: a wrong boundary, a missing interaction with an existing rule, wrong precedence, or a side effect missing or duplicated. |
| `superseded.txt` | Optional. Names of earlier cases this step intentionally changes, one per line. |

Per target, an optional `helpers.cs` next to `original.cs` may declare probe classes shared by all steps, for example an `IShipper` probe that counts calls. It is appended after the harness footer. The harness runs the bodies of steps 1 to k together, so **case names must be unique across the four steps**: prefix them `S1-`, `S2-` and so on.

Test rules:
- Use only public types and members and observable effects, as in the existing tasks: return values, probe collaborators, state readable through public members.
- Be deterministic: no clock, randomness, file system, network or environment.
- Use literal expected values, never values recomputed with copied implementation logic.
- Write 4–8 cases per step, with at least 2 acceptance cases and at least 1 regression case.

## Admission gates (run by the harness)

For each step k:
- **G1:** the step-(k−1) reference fails at least one step-k acceptance case. At step 1, the original fails one. The harness also checks that the repaired source fails one at step 1, without showing the repair to R2.
- **G2:** `reference.cs` passes all step-k cases and all retained cases from steps 1 to k−1, except superseded ones.
- **G3:** each mutant fails at least one step-k case.
- **G4 (step 1 only):** the original and the repaired source give identical results on every case of all four steps. A difference means the repair changed behaviour the sequence relies on; the target is then ineligible.
- **G5 (sequence):** the step-4 reference has a higher file decision burden than the original.

A step failing a gate goes back to R2 once, with the harness output. After that the target is excluded and the exclusion is reported. The harness never edits R2's material.

## Freeze

Admitted sequences are hashed into the freeze record (protocol Section 12). After the freeze, no requirement, test, reference or mutant changes for any reason linked to agent outcomes.

## Recording

R2 records, per target, the time spent and any requirement considered and dropped. The thesis reports admission results per gate and the families used.
