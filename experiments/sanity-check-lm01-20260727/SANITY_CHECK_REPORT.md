# LM-01 real sanity pilot

Status: complete  
Purpose: end-to-end plumbing sanity check only; not inferential thesis evidence.

## Frozen scope

- Instance: LM-01, `OrderImporter.ImportBatch`
- Target range: lines 10-67
- Design: full 2 x 2 x 2 factorial, one repetition per cell
- Model: `gpt-5.4`
- Iterative budget: six builds; every iterative cell converged after one build
- Generated visible test: admitted after compilation and two pristine runs

## Results

| Cell | Strict success | LLM calls | Builds | Visible tests | Repair tokens | Repair time |
|---|---:|---:|---:|---:|---:|---:|
| Target-only iterative - test | 1/1 | 2 | 1 | 0 | 4,152 | 24.0 s |
| Target-only iterative + test | 1/1 | 2 | 1 | 1 | 5,181 | 28.6 s |
| Detector-grounded iterative - test | 1/1 | 2 | 1 | 0 | 5,025 | 25.2 s |
| Detector-grounded iterative + test | 1/1 | 2 | 1 | 1 | 6,252 | 29.3 s |
| Target-only single-shot - test | 1/1 | 1 | 1 | 0 | 1,382 | 14.1 s |
| Target-only single-shot + test | 1/1 | 1 | 1 | 1 | 1,950 | 16.6 s |
| Detector-grounded single-shot - test | 1/1 | 1 | 1 | 0 | 1,971 | 15.7 s |
| Detector-grounded single-shot + test | 1/1 | 1 | 1 | 1 | 2,477 | 17.6 s |

Strict success requires a successful build, resolution of the triggering detector metric, and a private Layer-3 pass. All eight cells met all three requirements. Every frozen repair passed all 30 private behavioral drivers; there were no behavioral regressions. The eight final source artifacts have eight distinct hashes.

## Resource totals

- Separate test-authoring call: 1,359 tokens (837 input + 522 output)
- Eight repair assignments: 28,390 tokens
- Entire pilot: 29,749 tokens across 13 LLM calls
- Build attempts: 8
- Visible-test executions: 4
- Summed repair wall time: 171.3 seconds
- Summed private-oracle time: 71.5 seconds

## Interpretation

This confirms the complete experimental path works: diagnosis-blind test generation, admission, target-only and detector-grounded repair, single-shot and iterative control, test OFF/ON handling, frozen final-source artifacts, blinded private evaluation, and token accounting. With only one attempt per cell and 100% success everywhere, this pilot cannot estimate whether grounding or visible tests improve repair quality. On this easy LM-01 case, tests increased token use but did not change the binary outcome.

## Instrumentation findings

1. Boundary newlines in archived analyzer snippets inflated the target end line. The calculation was fixed before live calls and now has LF/CRLF regression coverage.
2. The first private evaluation placed the harness outside `corpus/src`, so its project references failed and no behavioral driver ran. That output is explicitly archived as invalid. The evaluator was fixed and regression-tested, and Layer 3 was rerun against the unchanged frozen repair artifacts. No private output was returned to a model and no repair was retried.
