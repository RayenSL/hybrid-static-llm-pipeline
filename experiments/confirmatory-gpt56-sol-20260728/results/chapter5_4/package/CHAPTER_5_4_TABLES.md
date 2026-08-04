# GPT-5.6 Sol replacement tables for Chapter 5.4

### Table 5.2: Static-detector performance and the frozen Sol factorial subset

| Anti-pattern | Seeded | Detected | False positives | Precision | Recall | F1 | Sol-factorial targets |
|---|---|---|---|---|---|---|---|
| God Class | 10 | 10 | 0 | 100.0% | 100.0% | 100.0% | 10 |
| Long Method | 10 | 10 | 0 | 100.0% | 100.0% | 100.0% | 9 |
| Obsolete API Usage | 10 | 10 | 0 | 100.0% | 100.0% | 100.0% | 0 |
| Overall | 30 | 30 | 0 | 100.0% | 100.0% | 100.0% | 19 |

### Table 5.3: Final strict-success outcome by factorial arm

| Arm | n | Build failures | Metric unresolved | Private regressions | Strict success | Strict success [95% Wilson CI] |
|---|---|---|---|---|---|---|
| Ungrounded · single-shot · test OFF | 57 | 0 | 14 | 0 | 43 | 75.4% [62.9, 84.8] |
| Ungrounded · single-shot · test ON | 57 | 0 | 9 | 0 | 48 | 84.2% [72.6, 91.5] |
| Grounded · single-shot · test OFF | 57 | 0 | 0 | 0 | 57 | 100.0% [93.7, 100.0] |
| Grounded · single-shot · test ON | 57 | 0 | 0 | 0 | 57 | 100.0% [93.7, 100.0] |
| Ungrounded · iterative · test OFF | 57 | 0 | 1 | 3 | 53 | 93.0% [83.3, 97.2] |
| Ungrounded · iterative · test ON | 57 | 0 | 0 | 3 | 54 | 94.7% [85.6, 98.2] |
| Grounded · iterative · test OFF | 57 | 0 | 0 | 3 | 54 | 94.7% [85.6, 98.2] |
| Grounded · iterative · test ON | 57 | 0 | 0 | 0 | 57 | 100.0% [93.7, 100.0] |

### Table 5.4: Ungrounded iterative target-recovery recall

| Anti-pattern | Independent targets | Recovery attempts | Attempt recall [95% Wilson CI] |
|---|---|---|---|
| God Class | 10 | 60/60 | 100.0% [94.0, 100.0] |
| Long Method | 9 | 53/54 | 98.1% [90.2, 99.7] |
| Overall | 19 | 113/114 | 99.1% [95.2, 99.8] |

### Table 5.5: Ungrounded iterative target-recovery precision

| Anti-pattern | Reported findings | Matched | Spurious | Precision [95% Wilson CI] |
|---|---|---|---|---|
| God Class | 60 | 60 | 0 | 100.0% [94.0, 100.0] |
| Long Method | 53 | 53 | 0 | 100.0% [93.2, 100.0] |
| Overall | 113 | 113 | 0 | 100.0% [96.7, 100.0] |

### Table 5.6: Strict success across the grounding x control x visible-test factorial

| Grounding | Control | Visible test | Strict success | Rate [95% Wilson CI] |
|---|---|---|---|---|
| Ungrounded | single-shot | OFF | 43/57 | 75.4% [62.9, 84.8] |
| Ungrounded | single-shot | ON | 48/57 | 84.2% [72.6, 91.5] |
| Grounded | single-shot | OFF | 57/57 | 100.0% [93.7, 100.0] |
| Grounded | single-shot | ON | 57/57 | 100.0% [93.7, 100.0] |
| Ungrounded | iterative | OFF | 53/57 | 93.0% [83.3, 97.2] |
| Ungrounded | iterative | ON | 54/57 | 94.7% [85.6, 98.2] |
| Grounded | iterative | OFF | 54/57 | 94.7% [85.6, 98.2] |
| Grounded | iterative | ON | 57/57 | 100.0% [93.7, 100.0] |

### Table 5.7: Prespecified paired main effects on strict success

| Contrast | Status | Independent targets | Risk difference (pp) | 95% CI (pp) | Exact sign-flip p |
|---|---|---|---|---|---|
| visible_test_main | confirmatory_primary | 19 | +3.95 | [-0.57, +8.46] | 0.125 |
| grounding_main | planned_secondary | 19 | +11.84 | [+1.27, +22.41] | 0.03125 |
| iteration_main | planned_secondary | 19 | +5.70 | [-2.88, +14.28] | 0.21875 |

### Table 5.8: Cell-specific visible-characterization-test effects

| Grounding | Control | Test effect (pp) | 95% CI (pp) | Exact p | Holm p | Interpretation |
|---|---|---|---|---|---|---|
| ungrounded | single-shot | +8.77 | [-3.01, +20.56] | 0.25 | 1 | exploratory / underpowered |
| ungrounded | iterative | +1.75 | [-1.93, +5.44] | 1 | 1 | exploratory / underpowered |
| grounded | single-shot | +0.00 | [+0.00, +0.00] | 1 | 1 | exploratory / underpowered |
| grounded | iterative | +5.26 | [-5.79, +16.32] | 1 | 1 | exploratory / underpowered |

### Table 5.9a: Correspondence between the original four context levels and the frozen Sol grounding factor

| Original context level | Original thesis payload | GPT-5.6 Sol status | Relationship to frozen Sol factor |
|---|---|---|---|
| Minimal | Detected code fragment only | Not run as a distinct level | No direct equivalent; ungrounded Sol received the complete pristine source plus neutral target coordinates, with diagnosis withheld |
| Structural | Minimal plus symbol, file/line location, anti-pattern type, and metrics | Operationalized as the grounding addition | Grounded Sol added the Structural finding and metrics to the same target coordinates and complete pristine source |
| Relational | Structural plus surrounding code and enclosing class/member summary | Not run | No Sol factorial arm |
| Full | All prior elements plus project metadata and additional same-file findings | Not run | No Sol factorial arm |

### Table 5.9: Pre-repair characterization-test generation and admission

| Anti-pattern | Generated | Admitted | Baseline failed | Build failed | Admission rate |
|---|---|---|---|---|---|
| God Class | 10 | 9 | 1 | 0 | 90.0% |
| Long Method | 9 | 8 | 0 | 1 | 88.9% |
| Overall | 19 | 17 | 1 | 1 | 89.5% |

### Table 5.10: Visible-test availability and execution fidelity in test-ON arms

| Arm | Assigned test-ON | Artifact available | Executed | Passed visible test | Availability |
|---|---|---|---|---|---|
| Ungrounded · single-shot · test ON | 57 | 51 | 51 | 51 | 89.5% |
| Grounded · single-shot · test ON | 57 | 51 | 51 | 51 | 89.5% |
| Ungrounded · iterative · test ON | 57 | 51 | 51 | 51 | 89.5% |
| Grounded · iterative · test ON | 57 | 51 | 51 | 51 | 89.5% |

### Table 5.11: Literature-derived expected quality-attribute mapping

| Anti-pattern | Expected ISO/IEC 25010 attributes |
|---|---|
| God Class | Maintainability, Modularity, Analysability, Modifiability |
| Long Method | Maintainability, Analysability, Testability, Modifiability |

### Table 5.12: Automated ISO/IEC 25010 mention and lexical alignment

| Anti-pattern | Evaluable scope | Outputs | Mention rate | At-least-one expected attribute | All expected attributes |
|---|---|---|---|---|---|
| God Class | Iterative arms | 120 | 100.0% | 100.0% | 59.2% |
| Long Method | Iterative arms | 108 | 99.1% | 99.1% | 88.9% |

### Table 5.13: Whole-solution quality impact of all frozen final repairs

| Arm | n | Mean smell delta | Collateral | Mean CA headline delta | Mean CA all-rules delta | CA available |
|---|---|---|---|---|---|---|
| Ungrounded · single-shot · test OFF | 57 | -0.754 | 0/57 | +0.140 | +0.088 | 57/57 |
| Ungrounded · single-shot · test ON | 57 | -0.842 | 0/57 | +0.053 | +0.018 | 57/57 |
| Grounded · single-shot · test OFF | 57 | -1.000 | 0/57 | +0.140 | -0.596 | 57/57 |
| Grounded · single-shot · test ON | 57 | -1.000 | 0/57 | +0.193 | -0.439 | 57/57 |
| Ungrounded · iterative · test OFF | 57 | -0.947 | 1/57 | +0.088 | -0.105 | 57/57 |
| Ungrounded · iterative · test ON | 57 | -0.982 | 0/57 | +0.070 | -0.105 | 57/57 |
| Grounded · iterative · test OFF | 57 | -1.000 | 0/57 | +0.088 | -0.351 | 57/57 |
| Grounded · iterative · test ON | 57 | -1.000 | 0/57 | +0.035 | -0.368 | 57/57 |

### Table 5.14: Net headline CA diagnostic change by category and factorial arm

| Arm | Category | Net headline delta |
|---|---|---|
| Ungrounded · single-shot · test OFF | Performance | +8 |
| Ungrounded · single-shot · test ON | Performance | +3 |
| Grounded · single-shot · test OFF | Performance | +8 |
| Grounded · single-shot · test ON | Performance | +11 |
| Ungrounded · iterative · test OFF | Performance | +5 |
| Ungrounded · iterative · test ON | Performance | +4 |
| Grounded · iterative · test OFF | Performance | +5 |
| Grounded · iterative · test ON | Performance | +2 |

### Table 5.15: Private Layer 3 behavioral preservation by anti-pattern and arm

| Anti-pattern | Arm | Preserved | Regressions | Preservation rate |
|---|---|---|---|---|
| God Class | Ungrounded · single-shot · test OFF | 30/30 | 0 | 100.0% |
| God Class | Ungrounded · single-shot · test ON | 30/30 | 0 | 100.0% |
| God Class | Grounded · single-shot · test OFF | 30/30 | 0 | 100.0% |
| God Class | Grounded · single-shot · test ON | 30/30 | 0 | 100.0% |
| God Class | Ungrounded · iterative · test OFF | 30/30 | 0 | 100.0% |
| God Class | Ungrounded · iterative · test ON | 30/30 | 0 | 100.0% |
| God Class | Grounded · iterative · test OFF | 30/30 | 0 | 100.0% |
| God Class | Grounded · iterative · test ON | 30/30 | 0 | 100.0% |
| Long Method | Ungrounded · single-shot · test OFF | 27/27 | 0 | 100.0% |
| Long Method | Ungrounded · single-shot · test ON | 27/27 | 0 | 100.0% |
| Long Method | Grounded · single-shot · test OFF | 27/27 | 0 | 100.0% |
| Long Method | Grounded · single-shot · test ON | 27/27 | 0 | 100.0% |
| Long Method | Ungrounded · iterative · test OFF | 24/27 | 3 | 88.9% |
| Long Method | Ungrounded · iterative · test ON | 24/27 | 3 | 88.9% |
| Long Method | Grounded · iterative · test OFF | 24/27 | 3 | 88.9% |
| Long Method | Grounded · iterative · test ON | 27/27 | 0 | 100.0% |
