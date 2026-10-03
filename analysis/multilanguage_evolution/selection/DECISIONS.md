# Selection decisions and measurement feasibility

Evidence cutoff: 14 September 2026, 00:00 UTC. This report records source-history and parser feasibility, not final scientific admission. None of these outputs has replaced the existing Json.NET thesis figure.

## Domain selection

The working trio is Odoo Community (business applications), Jenkins (development automation) and Apache Tomcat (application-server infrastructure). This gives two implementation languages and three different application roles. Language count is not the selection objective. The three cases are purposive examples, not a representative sample of all software or a comparison of language quality.

The original native-code candidates were tested first. Blender, QEMU and VirtualBox require stronger handling of native configurations, headers and macros than the initial syntax adapter supplies. A high rate of failed raw-source parses is a limitation of this measurement approach, not evidence that their source is defective. Some native headers are routed through the C grammar in the preliminary probe, which also contributes to failures. They have not been rejected based on anti-pattern counts.

Tomcat and Elasticsearch were added as infrastructure alternatives for that documented reason. Tomcat supplies a long preserved lineage and a comparatively coherent Java production layer. Elasticsearch's current first-parent ancestry terminates at a 2017 import despite older roots elsewhere in the graph. This falls short of the 15-year requirement under the current lineage rule; it does not imply that Elasticsearch itself began in 2017.

Sources for application roles: [Odoo](https://www.odoo.com/blog/odoo-news-5/the-odoo-story-56), [Jenkins historical changelog](https://www.jenkins.io/changelog-old/), [Tomcat](https://tomcat.apache.org/), [OFBiz](https://ofbiz.apache.org/). Recognition indicators are preserved in the two GitHub metadata files; stars are not a count of installations. A dedicated adoption assessment and current build/smoke checks remain outstanding.

## Preserved source histories

| Candidate | Earliest source on selected first-parent lineage | Approximate elapsed years | Qualification |
|---|---|---:|---|
| Odoo | 7 December 2006 | 19.8 | TinyERP/OpenERP/Odoo naming and source-layout changes require explicit scope mapping |
| Jenkins | 5 November 2006 | 19.9 | Includes Hudson-era source; describe the inherited lineage |
| Tomcat | 27 March 2006 | 20.5 | Earlier product history is outside this preserved source lineage |
| OFBiz | 1 July 2006 | 20.2 | Business-domain alternative; complete early/current Java probes |
| Blender | 12 October 2002 | 23.9 | Major C/C++ language-composition change and native preprocessing concerns |
| QEMU | 18 February 2003 | 23.6 | Empty initial commit is distinct from first source-bearing state |
| VirtualBox | Undated source import; first dated successor 15 January 2007 | 19.6 dated years | Import has Unix-epoch timestamp; never plot it as a 1970 observation |
| Elasticsearch | 12 October 2017 | 8.9 | Multiple imported roots; does not pass current first-parent-history requirement |

Every endpoint is an immutable commit at/before the cutoff. Full first-parent histories are deterministically compressed and checksum-linked from the per-repository JSON manifests. Several candidate histories contain timestamp reversals; annual selection follows ancestry order and the frozen cutoff rule rather than sorting arbitrary reachable commits by date.

## Python compatibility and exclusions

The modern Python grammar rejected valid early constructs, including Python 2 `exec code in environment` and soft-keyword `async` identifiers. The historical compatibility adapter uses CPython 3.12's bundled lib2to3 grammar without performing transformations or executing code. Python 2 mode is used through 2016. The 2017 snapshot's `setup.py` declares `python_requires='>=3.5'`; that snapshot uses the compatible grammar with print/exec statements disabled. From 2018 the modern grammar is used. These are explicit snapshot-level parser choices, not per-file fallback based on which result looks preferable.

The 2006 tree bundles ReportLab in `bin/reportlab/`; its copyright header identifies ReportLab Europe Ltd. This directory is excluded as third-party code. The `openerp/cli/templates/` and renamed `odoo/cli/templates/` directories contain scaffolding inputs, including Jinja directives inside files ending in `.py`. They are excluded as templates, not silently repaired to parse. The remaining source filters are provisional and still require a full repository-specific provenance review.

## Requirements before thesis use

1. Complete scope review across all years, including test modules, vendored packages, build tooling, optional modules and source-language composition. A generic directory filter is not a final production boundary.
2. Validate rule semantics and definition enumeration against real source samples and an independent measurement implementation where feasible. Passing construct tests is necessary but does not establish empirical precision or recall.
3. Build and minimally exercise current selected revisions. These checks have not yet been performed for the new working trio.
4. Freeze the admitted-study protocol, run independent A/B scans plus offline replay, and audit hashes and denominators.
5. Generate the three-case figure only from admitted measurements and revise the background subsection with the coverage and scope qualifications.

Contract version 0.1 prohibits scientific admission (`admitted` must be false). The coverage reports therefore cannot accidentally enter a thesis plot as validated prevalence results. The old .NET pipeline and previously published Json.NET artefacts remain separate.
