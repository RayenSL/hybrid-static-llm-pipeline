# Cross-language anti-pattern evolution study: design and selection brief

Initial design recorded on 14 September 2026. The selection discussion below preserves the original plan; consult README.md and results/THREE_RULE_ANALYSIS.md for current implementation and campaign status. Existing Json.NET findings and the .NET repair pipeline remain separate.

## Objective

Provide a compact background illustration of continued aggregate prevalence in three established open-source systems from distinct application domains. Require at least 15 years of preserved source history and at most two inadmissible annual observations per selected case. Product age alone does not establish preserved history. Findings are detector-defined conditions, not independently confirmed defects or evidence that particular instances remained unresolved.

Domain takes precedence over language diversity. Reopen selection completely; Json.NET has no reserved place. Select before inspecting prevalence magnitudes. Repository substitution is permitted for documented provenance, scope or measurement failures, never to obtain more findings or a stronger-looking trajectory.

## Initial inventory

| Domain | Candidates | Source and initial rationale | Questions remaining |
|---|---|---|---|
| Business applications | Odoo Community; Apache OFBiz | Odoo documents its TinyERP/OpenERP origins; OFBiz documents ERP/CRM applications and Apache status since 2006 | Earliest preserved ancestry, repository splits, first-party module boundaries, historical syntax and adoption evidence |
| Systems infrastructure | VirtualBox; QEMU | VirtualBox publishes its source and build guidance; QEMU publishes system-emulation documentation | Imported code, macros and preprocessing, native configuration coverage, earliest preserved source and adoption evidence |
| Creative desktop software | Blender | Official history dates open-source release to 2002; previous-version documentation points to historical source | C/C++ transitions, generated code, dependencies and interpretation of language composition shifts |
| Developer infrastructure (alternative domain) | Jenkins | Official changelogs preserve Hudson-era references and long release history | Hudson/Jenkins lineage, plugin boundary, source history depth and historical Java syntax |

This is an inventory, not an approved final trio. First assess Odoo, VirtualBox and Blender for the desired domain spread, with OFBiz, QEMU and Jenkins as explicit alternatives. Language diversity alone must not displace a stronger domain case. A third domain can be developer infrastructure if the creative-desktop candidate fails the gates.

Sources consulted:

- Odoo project history: https://www.odoo.com/blog/odoo-news-5/the-odoo-story-56
- Apache OFBiz application scope and Apache history: https://ofbiz.apache.org/
- VirtualBox source: https://github.com/VirtualBox/virtualbox
- VirtualBox development FAQ: https://www.virtualbox.org/wiki/Developer_FAQ
- QEMU documentation: https://www.qemu.org/documentation/
- Blender history: https://www.blender.org/about/history/
- Blender historical source availability: https://www.blender.org/download/previous-versions/
- Jenkins historical changelog: https://www.jenkins.io/changelog-old/
- PMD Java design-rule documentation (capability reference, not a frozen executable version): https://pmd.github.io/pmd/pmd_rules_java_design.html

Verify adopted usage indicators separately: official deployments, package dependencies/downloads or project reports, with retrieval date and limitations. Stars alone cannot establish usage. Do not present a product's founding date as an audited Git root.

## Production scope

Inventory all tracked first-party production source across the delivered system, not an arbitrarily chosen small module. Freeze repository-specific inclusion/exclusion rules before measurement. Exclude tests, benchmarks, examples, generated artefacts and vendored dependencies by documented paths and provenance. Include first-party optional modules shipped in the selected open-source distribution; external plugins and proprietary editions are outside the case.

Choose principal implementation language(s) after measuring the source inventory, and label every result with its analysed language scope. Report eligible source footprint and excluded/unanalysed language footprint at every snapshot. A Python-only Odoo result is a Python production-layer result, not a claim about all Odoo source. Keep language strata separate when composition changes. Do not hide a shrinking analysed fraction behind a clean parsing rate.

## Detector choice and construct validity

The current C# LongMethod detector flags CC > 10. LOC > 50 only increases severity. Its GodClass strategy uses ATFD > 4, WMC >= 47 and TCC < 1/3. Existing implementations are authoritative for old results and remain intact.

The shared cross-language measure will be the proportion of named function/method definitions exceeding a specified cyclomatic-complexity threshold. Call this complexity-based detection explicitly; do not label a length-only rule as equivalent to the C# rule. Record physical function length separately. Freeze decision-point mappings for every language, including short-circuit expressions, comprehensions, pattern matching, exceptions, switch cases, nested definitions and local functions. Count each definition once and specify whether constructors, operators, anonymous functions and accessors are eligible. Language mappings and exclusions are part of the rule version.

CC > 10 is the primary continuity threshold. Report predeclared sensitivity at > 15 and > 20 and the underlying complexity distribution. These checks assess dependence on the threshold; they do not establish universal cross-language validity. Do not infer language or project quality rankings from these percentages.

God Class is supplementary in object-oriented strata only. Use a documented ATFD/WMC/TCC implementation where adequate semantic resolution is available. A large-class or many-methods heuristic must have a different rule identifier and name. For Python's dynamic attribute accesses or C's lack of language-level classes, unsupported or unresolved God Class measurements are unavailable, not zero. Obsolete API Usage is supplementary only when historical dependency metadata and reference resolution support its meaning.

Prefer established parsers and transparent rule implementations over handwritten text matching. Pin released versions and dependencies. PMD is a Java candidate, not a declaration of equivalence: inspect its source and metric semantics before accepting a mapping. Native-language adapters must specify preprocessing/configuration semantics. A parser accepting tokens does not prove complete recognition of executable functions under macros.

Validate each mapping using construct fixtures, a stratified manual sample of actual historical code (early/middle/late, flagged and unflagged, around thresholds), and comparison with an independent implementation where available. Record disagreements and resolution. Establish validation sample sizes and reviewer procedure before looking at trajectories. Describe single-reviewer validation honestly if independent review is unavailable.

## Admission and reproducibility

Annual design: earliest preserved source-bearing state, last selected-lineage revision before each subsequent year boundary, fixed endpoint. Record UTC committer dates, cutoff timestamps and immutable hashes. Retain duplicate selected states as repeated observations and do not claim independent evidence from them. Audit imports, renames and ancestry timestamp reversals. Never silently backfill an unrelated fork or omit early source to meet the coverage requirement.

Completeness is rule-specific. Syntax-only complexity measurements require successful parsing and auditable enumeration of all eligible definitions within the declared language/configuration scope. Any unhandled relevant source invalidates the primary observation unless an exclusion was justified independently and frozen beforehand. Semantic rules additionally require adequate symbol/reference resolution. Build and runtime status are separate evidence fields; a successful syntax scan is not labelled a successful build. Confirm that a current revision can be built and exercised through a minimal smoke check for case feasibility, while historical build success is required only for rules that actually need it.

Two independent clean extractions plus offline replay must reproduce canonical findings, metrics, denominators and input hashes. Keep raw command lines separately from canonical evidence. Normalise only enumerated machine-local paths/times; preserve content hashes and meaningful options. The earlier nopCommerce path-normalisation failures motivate explicit handling, not post-hoc deletion of inconvenient differences.

At most two primary annual gaps per repository, counting every scheduled year including earliest state and endpoint. Do not interpolate or move timestamps to hide failures. Supplementary semantic series may have lower coverage and are labelled independently; they cannot be presented as satisfying the primary completeness gate.

## Modular architecture

Proposed layout:

- analysis/multilanguage_evolution/contracts/: versioned JSON schemas and canonicalisation specification.
- analysis/multilanguage_evolution/detectors/<language>/: isolated adapters, parser dependencies, rule mappings and fixtures.
- analysis/multilanguage_evolution/ingest/: schema validation, import and aggregation.
- analysis/multilanguage_evolution/protocols/: frozen case scope, sampling and detector configurations.
- analysis/multilanguage_evolution/results/: manifests, coverage, measurements and canonical evidence.
- analysis/multilanguage_evolution/figures/: generated data, SVG/PDF and captions.

Adapters consume a frozen snapshot manifest and emit a versioned result envelope. Ingestion serves the Python evolution analysis only. Existing .NET repair execution is unchanged. Future repair support would require separate language-specific build/test and patch-validation adapters; accepting a finding must never imply that such support exists.

Required envelope fields: schema version; repository URL and commit/tree hashes; sample label, cutoff and actual commit time; protocol/configuration hashes; tool and parser identities; language/version/configuration; declared and measured scope; source inventory hashes; exclusion reasons; rule-specific completeness; parse, semantic, build and runtime statuses; denominator definitions/counts; findings; replay provenance.

Required finding fields: snapshot-local identifier; rule identifier/version; anti-pattern concept; language; relative file path; source hash; symbol and symbol kind; line/column and byte span with encoding conventions; observed metrics and units; thresholds; severity and its mapping; supporting source span or snippet hash. Identifier stability across history is not guaranteed and must not be mistaken for lineage tracking.

Missing metrics use null with a reason, never zero. A valid zero has a positive eligible denominator and a successful rule-specific completeness status. Record raw counts even when reporting prevalence. Derive aggregates from findings and a definition inventory; never sum project percentages. Deduplicate shared source files/definitions explicitly across projects and native compilation units.

## Figure and inference

Use one publication figure with three aligned case columns. Within each column show the common complexity prevalence, raw finding count and eligible-definition count, followed by production size/coverage. Use shared calendar-year axes and a common prevalence scale. Avoid dual y axes: counts and size belong in separate aligned panels. Preserve gaps, annotate source-language or scope transitions, and use the same rule legend throughout. Export vector PDF and SVG with exact plotted CSV.

Supplementary class or API findings belong in an appendix or secondary figure if they cannot support all three cases. No pooled anti-pattern total across unlike units. No language ranking, no causal trend test, and no individual-survival claim. A background paragraph can report continued detection at sampled revisions and motivate the repair experiment; the detailed protocol and validation evidence belong in a reproducibility appendix.

## Execution gates

1. Audit source histories and adoption for the inventory; freeze a ranked domain shortlist before viewing findings.
2. Inventory early, middle, transition and current source; measure scope and test parser feasibility.
3. Implement and validate the common result contract and necessary isolated adapters.
4. Freeze rule mappings, thresholds, cutoffs and exclusions; run all annual snapshots with independent reproduction.
5. Admit exactly three cases only after each meets the 15-year and maximum-two-gap criteria. Record rejected cases and reasons.
6. Generate figures, audit all plotted values, and revise the background text using admitted evidence.

No annual campaign, final case admission or new cross-language result is asserted by this design document.
