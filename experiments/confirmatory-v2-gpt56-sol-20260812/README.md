# Confirmatory v2 run preparation

This directory is the pre-run package for the full rerun on the balanced v2
corpus. It is pinned to corpus revision
`20e22649fe8276507c2e760c9d3e48f40e111241` and pipeline implementation
revision `62955d325db8abb43d5d71c093cf8580f795b44c`.

The fixed design contains 26 evaluated targets, three repetitions and eight
factorial conditions (624 repair assignments). The Hybrid comparator is
planned separately as 156 attempts. Visible suites contain exactly five cases
per target; the private oracle contains ten cases per evaluated target plus ten
Obsolete-API smoke cases (270 total).

Current state:

- detector-only baseline frozen: 36 findings, including 13 God Class and 13
  Long Method targets;
- corpus band agreement: 36/36;
- private oracle: 270/270 on the pristine candidate;
- repair model calls: not started;
- R1 and blind automated R2 semantic review: complete, with 6/6 agreement;
- visible-test generation: complete, with 25/26 suites admitted and the first
  outcome retained for the rejected suite;
- factorial manifest: pending final freeze and dry-run validation.

`GENERATE_VISIBLE_TESTS.ps1` is restart-safe: a target with a persisted artefact
is skipped, so a rejected suite is retained as its intention-to-treat outcome
rather than regenerated. Run `FREEZE_CAMPAIGN.ps1` once; it refuses to create a
manifest while any review, baseline or artefact gate is closed and verifies the
final assignment count is exactly 624.

There is deliberately no launch script. Executing `factorial-campaign` is a
separate, explicit decision after the frozen manifest and readiness report have
been inspected.
