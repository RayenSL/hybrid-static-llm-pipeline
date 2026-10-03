# Annual syntax coverage

These are feasibility results under provisional source filters. They are not admitted anti-pattern prevalence measurements.

| Case | Domain | Preserved years | Complete annual parses | Missing observations |
|---|---|---:|---:|---|
| Odoo | Business applications | 19.8 | 21/21 | None |
| Jenkins | Development automation | 19.9 | 20/21 | endpoint-2026 |
| Apache Tomcat | Application-server infrastructure | 20.5 | 19/21 | 2025, endpoint-2026 |

All cases meet the numerical 15-year/maximum-two-gap feasibility gate only if `numerical_feasibility_gate` is true in the companion JSON. Scope validation, rule validation, current build/smoke checks and independent replay remain required before scientific admission.

The CSV and evidence JSON link every observation to its immutable commit, full result digest, source-scope digest and adapter digest. No anti-pattern count is used to rank candidates.
