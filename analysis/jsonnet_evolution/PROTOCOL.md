**Json.NET anti-pattern evolution — protocol 1.0.0**

This freezes the compatibility/reproducibility pilot before its measurements. The authoritative machine-readable specification is `protocol.json`. The study will describe aggregate prevalence in the production Json.NET library from its earliest preserved source through a frozen endpoint. It cannot establish individual smell lifetimes.

**Fixed inputs.** Use the pinned repository endpoint and five pilot commits in the JSON protocol. Quarter-boundary sampling follows the endpoint's first-parent ancestry and reuses duplicate source states. No snapshot is selected because its finding counts are interesting. The full timeline remains gated on the pilot.

**Historical meaning.** Use the historical default production project and its first declared framework if multitargeted. Preserve conditional compilation and reference APIs. Framework transitions are part of the observed system and must be annotated. An explicit .NET 2.0 default is permitted only for the verified early VS2005 project. Do not move old source to a new framework to obtain a successful scan.

**Measurement.** Compile with all semantic support files, but measure only included first-party production source. Exclude generated files by the explicit filename/header rules. Use the unchanged repository detectors and their frozen thresholds. Method and class denominators count exactly the declaration kinds that their detectors inspect. Obsolete-API counts retain the detector's per-symbol-per-file convention. Physical lines include comments and blanks and are supplementary.

**Validity gate.** Record every source/reference hash, effective compiler option, compilation error and excluded file. Errors make a scan partial or failed even if findings are emitted. Empty valid results are explicit. Missing source, missing references and zero eligible code never masquerade as clean zero findings. Generated support code stays in the compilation even when excluded from the counts.

**Reproducibility gate.** Capture the exact analyser source and its compiled runtime, selected references and evaluated compiler command. Build and scan each snapshot in two separate clean directories. Compare canonical findings, denominators, effective parsing/compilation settings and content hashes. Two failures do not count as successful reproduction. Then replay from the archived input bundle without Git/MSBuild/NuGet access. Timestamps, absolute working paths and runtime duration are operational metadata, outside the substantive comparison.

**Compatibility adapter.** The research stage showed a shared legacy MSBuildWorkspace build-host failure. The pilot will use a compiler-command export adapter: MSBuild evaluates the original project, and frozen Roslyn reconstructs its compilation from those exact source files, conditional symbols and references. This changes loading infrastructure, not detector definitions or historical API targets. Every build-property/SDK accommodation is scripted and recorded. If emitted options or required generated declarations cannot be reconstructed, fail visibly.

**Deliverables.** Versioned protocol, frozen snapshot manifest, analyser source/dependency locks, per-snapshot raw measurements and replay inputs, a two-directory comparison, machine-readable pilot status, and commands to rerun the pilot and regenerate its report. Figure generation for the full study will consume archived measurements only.

**Amendments.** Any substantive change to selection, framework policy, exclusions, thresholds or the equality gate requires a new protocol version and a recorded reason. Implementation fixes that bring code into conformance with this frozen protocol are not outcome-driven amendments.
