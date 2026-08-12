# Confirmatory v2 run preparation

This directory is the pre-run package for the full rerun on the balanced v2
corpus. It is pinned to corpus revision
`cc26ad1e78bc84198baf867c4292ab092df6c8d5` and pipeline implementation
revision `20aff5b332bd8576e08a0069b01397c238d17bef`.

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
- R1 and blind R2 semantic review: pending;
- visible-test generation: pending;
- factorial manifest: pending until the review and visible-test gates pass.

After the two reviewers have independently completed their worksheets, run
`GENERATE_VISIBLE_TESTS.ps1` once. It is restart-safe: a target with a persisted
artefact is skipped, so a rejected suite is retained as its intention-to-treat
outcome rather than regenerated. Then run `FREEZE_CAMPAIGN.ps1`; it refuses to
create a manifest while any review, baseline or artefact gate is closed and
verifies the final assignment count is exactly 624.

There is deliberately no launch script. Executing `factorial-campaign` is a
separate, explicit decision after the frozen manifest and readiness report have
been inspected.
