**Repository selection for the anti-pattern evolution background study**

> Generated results, figures and publication manifests were removed from this checkout.
> Paths and historical results described below refer to outputs that must be regenerated
> or restored before downstream analysis. Source code, protocols and dependency locks remain.

Research date: 4 September 2026. This report concerns repository selection and technical feasibility. It is not the longitudinal study and contains no claim that individual smell instances persisted.

**Recommendation: use Json.NET (`JamesNK/Newtonsoft.Json`).** It best combines recognisable adoption, a long and uncomplicated preserved history, a small production scope, and a clean current compilation inside HybridLens. Use OpenRA if a complete application is preferable to a library. Keep nopCommerce as the strongest business-application alternative.

The recommendation is conditional on resolving the historical MSBuild workspace-loading problem found during this investigation. No candidate has yet passed an end-to-end, earliest-to-present longitudinal scan. Json.NET is demonstrably buildable and runnable here; its earliest version builds, but its earliest version does not currently load through HybridLens's unchanged workspace loader.

**What was investigated**

Twelve established C# repositories were screened using live GitHub metadata, source-controlled build definitions, and official documentation. Nine complete default-branch commit histories were cloned without an initial source checkout. For six repositories, source trees and build definitions were inspected at the root, the first source-bearing commit where relevant, the ends of 2012, 2016 and 2020 when available, and a pinned current commit. Additional ancestry checks were performed for ILSpy, Jellyfin and OpenRA. Build probes covered Json.NET, nopCommerce, ShareX and OpenRA. All three existing HybridLens detectors were executed in the compatibility probes; the number of findings was not used to rank candidates.

Evidence is stored in [evidence.json](evidence.json). The [compatibility probe](compatibility_probe/Program.cs) calls the repository's WorkspaceLoader and detectors without changing their implementation, and records loaded files, compilation errors and diagnostic examples. Representative [logs](logs/) record successful builds and failures. These are reconnaissance probes: final production, generated-code, vendor and counting exclusions have not been applied to their findings.

The comparative criteria were:

- **Recognition:** current stars and forks, supplemented with ecosystem adoption where available. Stars are an indicator of recognition, not a count of active users.
- **Preserved history:** actual roots and source-bearing commits, imports, forks and discontinuities. GitHub repository creation dates were not treated as project birth dates.
- **Measurement fit:** ordinary C# classes and methods that the existing declaration-level detectors can measure, with resolvable historical references.
- **Practical reproducibility:** a manageable project/dependency graph, recoverable framework references, understandable build transitions, and executable current code.
- **Scope stability:** the ability to consistently separate first-party production code from tests, generated code and imported components.

No weighted score was manufactured. The ranking below is a reasoned judgement from these criteria and the stated background-subsection scope, not an empirical performance ranking of the projects.

**Screening comparison**

Stars are live GitHub API observations collected on the research date; historical dates refer to preserved ancestry, with qualifications below. The first API pagination result was checked against cloned ancestry where available, since it can belong to an imported dependency.

| Candidate | Stars | Preserved history relevant to selection | Assessment |
|---|---:|---|---|
| [Json.NET](https://github.com/JamesNK/Newtonsoft.Json) | 11,316 | 8 September 2007; one root | **First choice.** Compact library, clean current semantic compilation, verified runtime smoke check. Framework-selection and legacy-loader work remain. |
| [OpenRA](https://github.com/OpenRA/OpenRA) | 17,333 | 19 June 2007; one root | **Best full-application alternative.** Nine production projects scan without compilation errors after a solution-format adapter. Earliest tree contains a C# utility and C++ project; game execution also needs assets/native components. |
| [nopCommerce](https://github.com/nopSolutions/nopCommerce) | 10,139 | 6 July 2010; imported existing product | **Best business-application alternative.** Current web application and earliest business-logic project build. Larger scope and some missing generated methods in the analyser. |
| [ShareX](https://github.com/ShareX/ShareX) | 39,442 | Empty root 8 October 2013; source import 3 November 2013 | Highly recognisable, but current analyser compilations have substantial generated-UI gaps. Earliest source still fails to build after package restoration. |
| [NLog](https://github.com/NLog/NLog) | 6,545 | 11 August 2004; two roots | Strong long-lived library alternative, but earliest projects use pre-MSBuild Visual Studio format and .NET 1.1 references. More historical reconstruction than Json.NET. |
| [Duplicati](https://github.com/duplicati/duplicati) | 14,964 | 2008 root; additional 2013 block-storage root | Real application with long history, but multiple roots, the storage-generation transition, and 109 current C# project files complicate a compact study. |
| [Umbraco](https://github.com/umbraco/Umbraco-CMS) | 5,239 | 19 June 2009 TFS import of a 4.1 branch | Established product, but the beginning is already a mature imported branch, and the source build includes frontend/submodule concerns. Not build-tested here. |
| [Jellyfin](https://github.com/jellyfin/jellyfin) | 56,524 | 2012 ancestor; Jellyfin project begins in 2018 | Excellent recognition, but the early timeline is MediaBrowser/Emby history, not Jellyfin development. Additional runtime components and a larger graph; not build-tested here. |
| [ILSpy](https://github.com/icsharpcode/ILSpy) | 26,010 | ILSpy's own root is 2 February 2011; older 2007 ancestry is imported | Six roots include imported components. Current global.json requests SDK 11, absent here. Less straightforward than the finalists. |
| [Orchard Core](https://github.com/OrchardCMS/OrchardCore) | 8,173 | 19 November 2014 | Early source uses .xproj/project.json; current source has 245 C# projects and requests SDK 10.0.302. High historical infrastructure burden. |
| [NHibernate](https://github.com/nhibernate/nhibernate-core) | 2,174 | 17 February 2003 CVS-to-SVN initialisation | Credible mature alternative. Its age is attractive, but this screening found no reason to prefer it over the more recognisable, smaller Json.NET case. Not build-tested here. |
| [Roslyn](https://github.com/dotnet/roslyn) | 20,645 | 18 March 2014 | Very large compiler/tooling repository, with about 146,000 commits reported by API pagination. Disproportionate scope for this background subsection. Not build-tested here. |

These repositories are not twelve interchangeable samples of the same population. The table records why each was considered and why the final case is purposive rather than statistically representative.

**Why Json.NET is the best fit**

Recognition is supported by more than stars: NuGet's package page lists approximately **51,700 dependent packages**, including Microsoft ASP.NET integration packages. This is evidence of ecosystem reach, although it is not a count of unique installations or users. [NuGet package and dependants](https://www.nuget.org/packages/Newtonsoft.Json)

The cloned history has **1,915 reachable commits**, including **1,577 first-parent commits**, and a single root. The first commit already contains source. That makes the retained timeline easier to explain than histories containing multiple independent roots, an unrelated dependency's older ancestry, or a recent fork of a different product. The study must nevertheless describe the beginning as the **earliest preserved Git source**, rather than asserting that the software was invented on that date. [Pinned root](https://github.com/JamesNK/Newtonsoft.Json/commit/e65bc2becd3ded759b5d5ca42c7d28a631cfc06d)

The production boundary is unusually clear: `Src/Newtonsoft.Json/`, separated from the tests and test-console projects. The tracked production C# file counts at inspected snapshots are 32 at the root, 170 at the end of 2012, 207 at the end of 2016, 230 at the end of 2020, and 240 at the pinned current revision. These are source-footprint checks, not final denominators. They exclude the separately housed test suite and do not imply that every file participates in every target-framework compilation.

Its production code covers parsing, writing, serialization, conversion, contracts and reflection. This supplies ordinary C# implementation structure without requiring a database-backed website, UI session or game installation to exercise the library. The recommendation does not depend on obtaining high smell counts or nonzero counts for all three detectors.

The pinned current production compilation loaded by HybridLens contains **242 syntax trees and zero compilation errors**. All three detectors executed. The small difference between tracked files and syntax trees reinforces the need to define generated-file and conditional-compilation handling before the study. This is clean evidence for the selected current compilation, not proof that every historical target framework loads.

A basic runtime check serialized an object containing a string and an integer, parsed the result, and verified both values using the freshly built Json.NET assembly. It passed. This establishes that the built library executes here; it is not a comprehensive test suite or a behavioural-equivalence claim.

The key tradeoff is that **Json.NET is a library**. It supports a motivating example of anti-pattern prevalence in widely used open-source C# software. It should not be described as representative of enterprise applications or all open-source systems. If the subsection must illustrate a complete application, choose OpenRA; if it must resemble business software, choose nopCommerce.

**What the compatibility probes actually established**

| Probe | Result | Qualification |
|---|---|---|
| Json.NET, earliest source | Build passed with explicit `TargetFrameworkVersion=v2.0` | Uses installed modern MSBuild with the historical framework target. The old project does not explicitly encode that target, so the supplied property must be recorded. |
| Json.NET, current declared build | Failed before compilation | global.json requests 10.0.300; the newest installed system SDK is 10.0.203. |
| Json.NET, current compatibility build | Build passed, zero warnings/errors; runtime smoke passed | Only the scratch copy's SDK selector was temporarily changed to 10.0.203; upstream net8.0 was selected through its existing `LibraryFrameworks` property. Original global.json was restored. |
| Json.NET, current HybridLens compilation | One returned compilation, zero errors | Same temporary SDK selector; other unselected framework evaluations emitted targeting-pack warnings. Explicit target selection is required for the study. |
| Json.NET earliest / ShareX earliest, HybridLens | Both failed before a usable compilation | Shared remote build-host TypeInitializationException involving `Microsoft.Build.Shared.XMakeElements`. This is an unresolved loader/toolchain compatibility problem, not evidence that the source contains no findings. |
| nopCommerce, current web application | Build passed | Public NuGet source isolated from unrelated machine feeds. Application startup/installation was not tested. |
| nopCommerce, earliest business-logic project | Build passed after supplying .NET 4.0 reference assemblies | Reference assemblies were downloaded into scratch storage. This was one substantial project and its referenced build graph, not a complete 2010 website build. |
| nopCommerce, current full-solution scan | 37 projects loaded; 16 compilation errors | Errors involve missing generated regex implementations in four projects. The current analyser's workspace warnings were empty despite these compilation errors. |
| ShareX, current main application | Build passed with zero warnings/errors | Restored from public NuGet; GUI startup was not tested. |
| ShareX, current full-solution scan | 13 projects loaded; 3,173 compilation errors | Many errors involve generated Avalonia/UI/observable members. Some ancillary projects were not part of the main-app build. These findings are unsuitable as clean prevalence evidence without resolving coverage. |
| ShareX, earliest source | Build failed, including after original package restoration | Additional missing types/references remain. The root commit itself has no C# source and must not be reported as a successful zero-findings scan. |
| OpenRA, current server | Build passed with zero warnings/errors | Server/game startup and asset availability were not tested. |
| OpenRA, current production scan | Nine projects loaded; zero errors and zero workspace warnings | A temporary legacy .sln enumerated the nine production projects because HybridLens rejects the upstream .slnx; source and original solution were untouched. |

The comparison does not treat zero, few or many anti-pattern findings as a quality ranking. Compiler errors and recoverability determine measurement feasibility. The snapshots and scopes also differ, so their raw finding counts must not be compared as project-quality scores.

**History and workload implications**

With the proposed rule—root, last first-parent commit before each UTC quarter boundary, and pinned endpoint—the Json.NET history yields **78 observations at 70 unique commits** through the 4 September 2026 cutoff. Eight repeated observations can reuse a scan. They remain repeated source states, not eight independent pieces of evidence. No first-parent committer-date reversal was observed in this history.

For comparison, nopCommerce produces 66 unique snapshots; ShareX 53; OpenRA 79 observations at 74 unique snapshots; Duplicati 75 at 71; NLog 90 at 79; Orchard Core 49 at 49. These are manifest-size estimates, not completed scans or runtime forecasts. Git-tree inspection found committer-date reversals in nopCommerce, ShareX and OpenRA, reinforcing the need to freeze an explicit lineage/time-selection rule rather than sorting arbitrary commits by date.

**Required changes to the study plan**

1. **Select Json.NET provisionally, then pass a historical loading gate.** Demonstrate clean, correctly referenced compilations at the 2007 root and representative legacy, SDK-style and current revisions. A successful command-line build alone is insufficient. If the legacy loader cannot be made reliable, reconsider the start-date requirement or candidate; do not silently report only modern years as the full history.
2. **Freeze an explicit framework-selection policy.** Json.NET targets multiple frameworks. Analyse one declared framework per primary observation, record its conditional symbols and exact resolved references, and avoid counting the same code repeatedly across targets. Framework transitions should be marked. An overlap analysis at transition points can distinguish source changes from reference/profile effects. The policy should be written before looking at trajectories.
3. **Keep historical API meaning.** Do not retarget old code to modern .NET just to make it compile. A different build SDK can be a documented infrastructure accommodation; changing framework/reference APIs changes the obsolescence question and cannot be silently pooled with the primary series.
4. **Make diagnostic coverage a formal gate.** The existing loader can report no workspace warnings while returned compilations contain errors. Record compilation errors and eligible source coverage directly. Distinguish complete, partial, failed, not-applicable and valid-zero observations.
5. **Freeze detector and denominator semantics.** Long Method concerns `MethodDeclarationSyntax` and cyclomatic complexity, not every callable member. God Class currently works per class declaration and does not aggregate all parts of a partial type. Obsolete API Usage is deduplicated per referenced obsolete symbol within a source tree, not counted once per call site. Denominators must match these units, and generated code must be excluded consistently.
6. **Preserve zero-result artefacts.** The existing CLI returns before writing structured results when there are no findings. Address that before relying on its files as a longitudinal dataset.
7. **Keep the inference descriptive.** Present counts and normalised prevalence by type, with coverage and framework transitions. No individual-lifetime, removal, repair, causality or general-population claim follows from these aggregate snapshots.

The subsection can combine this case study's evidence of continued prevalence with literature that actually tracks individual smell instances. Tufano and colleagues' longitudinal work is an appropriate source for the distinct question of smell introduction and survival; our aggregate design does not replicate that instance-tracking methodology. [Author-hosted paper](https://fpalomba.github.io/pdf/Journals/J4.pdf)

**Reproduction and provenance**

The evidence bundle contains repository URLs, API metadata retrieval time, pinned commit hashes, roots, inspected project definitions, sampling estimates, build commands, diagnostic examples and analyser assembly hash. The analyser was rebuilt from the current working tree. The Git commit alone does not fully identify it because unrelated tracked changes already exist; assembly and detector-source hashes should accompany a frozen study build.

The compatibility harness can be built from this repository with:

```powershell
dotnet build analysis/repository_selection/compatibility_probe/Probe.csproj
dotnet analysis/repository_selection/compatibility_probe/bin/Debug/net10.0/Probe.dll <solution-or-project> <diagnostics.json>
```

Select an installed compatible SDK, restore the target's declared references, and use an isolated public NuGet configuration for these public repositories. The harness does not restore the target and does not implement the final exclusions or longitudinal orchestration. Its JSON findings are pilot diagnostics only.

The checked-out source snapshots, downloaded targeting pack, original local logs and runtime smoke project remain in ignored `tmp/repository-selection/` or `/tmp/antipattern-repository-research/`. Original upstream source code was not repaired or refactored. Temporary SDK selectors were restored. No LLM repair calls were made.

**Primary source pointers**

- [Json.NET root](https://github.com/JamesNK/Newtonsoft.Json/commit/e65bc2becd3ded759b5d5ca42c7d28a631cfc06d), [current SDK selector](https://github.com/JamesNK/Newtonsoft.Json/blob/09bb545d72969ad7fb4ea07db0d5c34f4fc07877/Src/global.json), [current production project](https://github.com/JamesNK/Newtonsoft.Json/blob/09bb545d72969ad7fb4ea07db0d5c34f4fc07877/Src/Newtonsoft.Json/Newtonsoft.Json.csproj), [NuGet adoption](https://www.nuget.org/packages/Newtonsoft.Json).
- [nopCommerce root](https://github.com/nopSolutions/nopCommerce/commit/03c6afceb84030c7d2c5d326937b4a97d4fb3ce4), [source organisation](https://docs.nopcommerce.com/en/developer/tutorials/source-code-organization.html).
- [ShareX first source import](https://github.com/ShareX/ShareX/commit/dba0ec79f8d70f684c48c3ed250dacb9570200f8), [current application project](https://github.com/ShareX/ShareX/blob/1c359f3b0a64da2ea9ce3727e5f86bad65621b11/ShareX/ShareX.csproj).
- [OpenRA root](https://github.com/OpenRA/OpenRA/commit/b59ba43934a3a6837410db51cf60157cf854e52d), [pinned prerequisites](https://github.com/OpenRA/OpenRA/blob/8eac2bb69061b02b974beeae8f7feaab860610c0/INSTALL.md).
- [Jellyfin's account of its origins](https://jellyfin.org/docs/general/about/), [Umbraco source-build instructions](https://docs.umbraco.com/contributing/umbraco-cms/contributing/build), [Duplicati source-build instructions](https://docs.duplicati.com/installation-details/developer).
- All additional pinned build-file URLs and commit-origin records are in the evidence bundle; the cloned ancestry evidence takes precedence over an API's apparent oldest commit.
