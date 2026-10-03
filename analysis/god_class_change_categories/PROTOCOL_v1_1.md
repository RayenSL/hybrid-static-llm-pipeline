# God Class change-category follow-up: audit amendment v1.1

This is an explicitly post-pilot amendment to `PROTOCOL.md`. A fixed stratified inspection of first-parent commit titles, conducted after the v1.0 results, found that a bare `security` token commonly denotes a Java security manager or a dependency name. It also found older Jenkins fixes identified by `HUDSON-<digits>`, which v1.0 placed in the weaker other-fix category. The analysis is exploratory; v1.0 is retained as an audit trail and not presented as confirmatory evidence.

All population, event, modelling, uncertainty and output rules of v1.0 remain unchanged except for these two title rules:

1. `security_labelled` requires `CVE-<digits>`, `CWE-<digits>`, `SECURITY-<digits>`, `vulnerability`, `XSS`, `CSRF`, `XXE`, `exploit`, or a phrase beginning `security fix`, `security advisory`, `security issue`, `security hardening`, or `security patch`. A bare `security` token is insufficient.
2. `issue_linked_fix_labelled` in Jenkins recognises either `JENKINS-<digits>` or `HUDSON-<digits>` together with the same corrective cue. This is a historical project identifier, not a new issue type.

The categories remain **title-cue groups** and cannot certify bug, security or feature work. The amendment was made to improve face validity, not to maximise a ratio or significance. Interpret the resulting category models with the same multiplicity control and uncertainty limits as v1.0.
