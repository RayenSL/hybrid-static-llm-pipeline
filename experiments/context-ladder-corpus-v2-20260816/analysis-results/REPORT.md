# Context-ladder corpus v2 outcomes

Cochran Q=68.3394, df=3, p=9.67774e-15.

## Levels

| level | n | build_fails | builds_unresolved | resolved | layer3_pass | layer3_fail | detector_resolved_and_layer3_pass | quality_scored_n | smell_delta_mean | ca_headline_delta_mean | ca_all_delta_mean | prompt_characters_mean | input_tokens | output_tokens | nominal_cost_usd | cross_file_truncated |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| minimal | 108 | 6 | 23 | 79 | 98 | 4 | 75 | 102 | -0.7156862745098039 | 0.029411764705882353 | 0.049019607843137254 | 5787.666666666667 | 157458 | 162921 | 5.67492 | 0 |
| structural | 108 | 8 | 23 | 77 | 98 | 2 | 75 | 100 | -0.77 | -0.56 | -3.13 | 6063.222222222223 | 166653 | 172073 | 5.995455 | 0 |
| relational | 108 | 6 | 19 | 83 | 102 | 0 | 83 | 102 | -0.8137254901960784 | -0.18627450980392157 | -2.0294117647058822 | 7177.5 | 195753 | 174213 | 6.205155 | 0 |
| full | 108 | 0 | 0 | 108 | 104 | 4 | 104 | 108 | -1.0 | -1.0555555555555556 | -5.37037037037037 | 8366.305555555555 | 225909 | 152229 | 5.696415 | 0 |

## Adjacent contrasts

| contrast | lower_only | higher_only | risk_difference_pp | p | holm_p |
|---|---|---|---|---|---|
| structural-minimal | 4 | 2 | -1.8518518518518519 | 0.6875 | 0.6875 |
| relational-structural | 1 | 7 | 5.555555555555555 | 0.0703125 | 0.140625 |
| full-relational | 0 | 25 | 23.14814814814815 | 5.960464477539063e-08 | 1.7881393432617188e-07 |

## Successor-available Obsolete API subset (n = 4 targets)

| level | resolved | migrated | n |
|---|---|---|---|
| relational | 1 | 0 | 12 |
| full | 12 | 12 | 12 |

## Obsolete API grading

{'migrated': 30, 'evaded': 9}

The sharpest successor-availability mechanism claim has n = 4 targets. Detector resolution is not behaviour preservation; Obsolete API Layer 3 is a smoke oracle.
