# Persistence in changing production files (v1.0)

This is a descriptive extension of the sealed three-rule annual campaign. Fix the following rules before inspecting its results.

## Population and observations

- Use Odoo, Jenkins, and Apache Tomcat annual snapshots labelled 2007–2025. The irregular earliest-2006 and partial-year 2026 endpoints are excluded. Each comparison joins consecutive calendar labels only.
- Replace the five chronology-invalid Odoo observations (2018, 2019, 2020, 2023, 2024) with the sealed calendar-frontier v0.2 scans and syntax inventories. Preserve all original campaign outputs.
- Analyse a rule only when it is complete at both ends of an interval. No missing observation is treated as zero or bridged. The unit is a baseline finding at a pair of adjacent annual snapshots, not an independent finding lifetime.
- Match findings on `(repository, rule, path, symbol)`. The detector ID includes line number and is not a longitudinal identity. If that key is repeated at either snapshot, mark it ambiguous and exclude it from the primary matched-identity denominator.

## States and outcomes

- Compare the file SHA-256 hashes in the two sealed production inventories. A file with a different hash at the same path is **changed**; an identical hash is **unchanged**. This detects source-content change, not the number or cause of commits, and does not establish that the flagged entity itself was edited.
- A finding is **redetected** when the same `(path, symbol)` is flagged by the same rule at the next complete snapshot. It is **no longer detected with entity present** for Long Method when a unique named definition with the same key exists in the next complete syntax inventory, or for God Class when a unique class metric with the same key exists in the next complete semantic inventory. This does not establish deliberate refactoring.
- For Obsolete API Usage, absence of the positive finding is **not redetected**, not a verified removal: a complete annual source/API reference inventory is unavailable. Changes to a declaration's deprecation status can also alter the result.
- If the baseline file is absent at its former path, report **path absent**, without calling it repair or deletion; an edited rename or movement may be responsible. If the file exists but the structural entity is absent, report **entity absent**. Do not merge these states with rule cessation.
- The principal descriptive quantity for each repository and rule is the share of baseline findings in changed files that are redetected at the following annual scan. Report numerator and denominator; also give unchanged-file redetection as a consistency diagnostic. For structural rules, report the more specific redetection share among findings whose named entity remains identifiable in a changed file. API shares retain the limited label *redetection*.
- As a secondary description, join consecutive unique-key redetection edges into observed runs. Count runs spanning at least three consecutive annual scans, and among them runs whose file content changed during at least one linked interval. A run is an observed lower bound on detectable presence, not an exact lifetime; gaps, name changes and incomplete scans break it.
- Each baseline finding can occur in several adjacent intervals. These descriptive shares are not independent-binomial estimates and carry no confidence interval or causal interpretation. They cannot be converted into exact finding lifetimes from annual observations.

## Validity and reproduction

Count unique and ambiguous identities, incomplete rule intervals, path absences, entity absences and unchanged-file inconsistencies. Detector decisions were automatically reproduced but not independently reviewed. Same-key matching can conflate overloads and can miss renames. Annual sampling can miss disappearances followed by reintroduction. Code outside the declared production scope is absent.

Read the sealed bundle and corrected five snapshots without modifying them. Record their hashes, the script hash, row counts and output hashes. A second run to a fresh directory must produce byte-identical canonical CSV/JSON/PDF-independent results. Figures are rendered separately from deterministic tables.
