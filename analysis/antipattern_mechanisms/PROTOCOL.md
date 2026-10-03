# Three detector-specific maintenance mechanisms: exploratory protocol v1.0

These separate follow-ups were chosen after inspecting aggregate prevalence, file-change associations and persistence results. They are exploratory. The detectors remain automated, without independent human adjudication. Outcomes are repository records or source transformations, not ISO/IEC 25010 scores or causal effects of an anti-pattern.

## Shared inputs

Use the corrected annual scans of first-party production source in Odoo, Jenkins and Apache Tomcat. Apply the five separately sealed Odoo calendar corrections (2018–2020, 2023–2024). Use only complete rule measurements. Keep repository results separate. Input bundles, source archives, Git commit identities, event databases, parser versions, scripts and outputs are hash-recorded. Never interpret missing coverage as zero.

## God Class: change spread

Question: conditional on a production file being modified in the next 365 days, are its modifying commits more likely to modify other production files when the baseline file contains a God Class finding?

The unit is a baseline file-at-snapshot in the same within-repository, within-year overlapping size and prior-change ranges as the earlier adjusted God Class count analysis. Eligible files have at least one measured class. For each first-parent `M` event in the baseline lineage, after the baseline commit and within 365 recorded timestamp days, count other *baseline-inventory production file lineages* with `M` in the same commit. The binary event outcome is any such co-modification. The file outcome is the fraction of its qualifying modification events with any co-modification; files with no modification have an undefined fraction and are reported separately, not assigned zero. The primary analysis compares file fractions after adjustment for year, baseline PLOC and prior 365-day changes, with file-lineage/year clustered uncertainty. Also report raw event counts, modified-file support, and an all-file co-modification total as a descriptive companion. A sensitivity excludes commits modifying more than 20 baseline-production file lineages. This is a measure of recorded change spread, not effort, coordination time or a required ripple effect.

## Long Method: direct-edit persistence

Question: among baseline Long Method findings whose *named definition's source snippet* differs at the following complete annual scan, what proportion still exceeds cyclomatic complexity 10, and how does complexity change?

The unit is a uniquely matched `(path,symbol)` baseline definition at an adjacent annual pair. Require complete Long Method scans and complete syntax inventories at both endpoints, a unique named definition at each, the same path in production scope, and a different snippet SHA-256. Confirm that the baseline syntax complexity and detector finding agree. Report the denominator of directly changed positive definitions, the number still flagged, and the distribution of next-minus-baseline complexity and physical-line changes. Report unmodified snippets, missing paths, absent/ambiguous symbols and incomplete pairs separately. A snippet that changes and then returns to identical bytes between annual scans will appear unchanged. This is structural persistence after a directly observed edit, not a claim that a refactoring was attempted or that comprehension was costly.

## Obsolete API Usage: caller transitions and migration candidates

Question: when a source file containing a resolved reference to a source-declared deprecated API changes between complete annual scans, does the same `(source path, referenced API)` finding remain detectable?

The unit is a distinct baseline positive source-file/API pair. Require complete obsolete-API scans at both adjacent endpoints. Classify each as redetected, source path absent, source unchanged but finding absent, or source changed but finding absent. For changed-source absences, compare the referenced declaration path's inventory SHA-256 when available. An absence with an unchanged declaration source is a *migration candidate*, not a verified migration: call sites can disappear, binding can change elsewhere, or the resolver can miss a reference. An absence with a changed/missing declaration is an *unresolved cause*. Never convert a detector disappearance automatically into successful migration. Report consecutive positive-detection run lengths as lower bounds, right-censored at the final complete scan and broken at missing scan intervals. Do not estimate time-to-confirmed-migration or breaking-compatibility rates without an independently reconstructed all-reference inventory or exact call-site verification. Odoo's sparse positives remain descriptive.
