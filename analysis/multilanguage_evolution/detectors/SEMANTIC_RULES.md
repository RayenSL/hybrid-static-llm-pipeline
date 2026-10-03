# Three-rule mappings and limits

The modular suite emits `evolution.multi-rule/0.2`. It is an experimental research implementation. A module being implemented is different from a repository having a complete, validated historical measurement. The existing C# detectors and repair pipeline are not changed.

## Long Method

The primary gate is cyclomatic complexity greater than 10. A finding with more than 50 physical lines has critical rather than warning severity; length alone does not trigger a finding. The existing syntax adapter supplies the definition inventory and complexity values. Failed syntax coverage makes the primary count unavailable.

The cross-language population consists of named definitions with bodies, including Java constructors and Python nested functions. Nested callable bodies do not contribute decisions to their enclosing callable. These choices differ from the C# method-declaration population and descendant traversal. Equal thresholds therefore do not establish numerical equivalence with the earlier Json.NET results. See `RULE_MAPPING.md` for the syntax-node mapping.

The legacy Python counter now handles both typed and bare exception clauses. A bare `except:` becomes a leaf rather than an `except_clause` node in lib2to3; ignoring that distinction previously undercounted complexity. Existing feasibility artefacts are historical evidence and are not silently rewritten.

## God Class

A class triggers the composite rule only when all conditions hold:

- ATFD > 4;
- WMC ≥ 47;
- TCC < 1/3.

WMC sums the complexities of declared methods. Java constructors and Python `__init__`/`__new__` are excluded from WMC. TCC is the fraction of eligible public-method pairs sharing an own instance attribute; fewer than two eligible public methods gives TCC = 1. Java uses explicit public visibility. Python uses method names without a leading underscore.

The Java adapter uses javac attribution. Its WMC counter uses compiler-tree decisions, including individual switch labels and explicit pattern guards. The Long Method probe counts syntax-parser switch-label nodes; modern multi-label and pattern constructs still require cross-rule empirical validation. ATFD counts distinct resolved fields owned by other source-defined types, excluding the analysed class and its ancestors. TCC uses resolved shared own, non-static fields. Java has no C# property construct; accessor methods are not relabelled as properties. Nested classes are measured separately, although the foreign-field traversal includes descendant source accesses as in the existing C# implementation. As in the existing Roslyn implementation, unresolved bindings are skipped rather than imputed. Their counts and compiler diagnostics remain in the evidence, but they do not invalidate metrics produced by a complete parser walk.

The Python adapter indexes explicit source declarations, imports, annotated receivers and own-instance assignments. It distinguishes inherited and foreign fields where the source binding is known and skips unresolved bindings under the same best-effort rule. Historical Python 2 syntax is converted with a restricted syntax-only fixer set after encoding, indentation and line-ending normalisation; the adapter rejects any conversion that changes the number of source lines. Descriptors, decorators, metaclasses, unknown receivers and dynamic mutation remain diagnostic limitations. A complete primary count is complete for this declared static model and must not be described as a validated substitute for Odoo's runtime object model.

`findings` contains threshold combinations produced by the declared best-effort static model. `candidates` is reserved for classes without a complete WMC measurement; candidates are never added to the primary count. Findings remain detector outputs rather than independently confirmed design defects.

## Obsolete API Usage

The unit is a distinct `(source file, deprecated API)` pair, following the existing C# detector's per-file symbol deduplication. Repeated calls to the same API in one file produce one representative finding. This unit must not be added to class or method counts to produce a combined anti-pattern total.

Java uses compiler deprecation metadata for source-defined symbols, including standard annotations and recognised Javadoc deprecation metadata. A containing type's deprecation also applies to its referenced members, except self-use inside that same type. A deprecated type and one of its deprecated constructors are distinct referenced symbols. Method overloads retain compiler symbol identity.

Python resolves imported aliases for `warnings.deprecated` and `typing_extensions.deprecated`, and recognises direct function-body `warnings.warn(..., DeprecationWarning)` statements. A warning nested inside an `if` does not deprecate the entire API under this mapping. Calls shadowed by parameters or local assignments are not resolved through the corresponding module import. Calls with unknown dynamic receivers are skipped and remain visible in the diagnostic coverage fields. Project-specific decorator conventions and non-call references are outside this operational definition.

The primary population is the distinct `(source file, source-declared API)` pairs resolved in the analysed revision, and the numerator is the subset whose declaration is deprecated. The modules deliberately do **not** apply the current JDK or current Python packages' deprecation status retrospectively. Third-party dependency deprecations are outside this primary measurement unless a separate versioned historical catalogue is supplied in future work. This narrower source-declared trajectory is reproducible across languages and must be labelled as such in figures and prose.

## Compiler profiles and reproducibility

`protocols/java-release-profiles.json` records the selected commit, descriptor hashes, versioned parent POM evidence, declared release and compiler compatibility release. JDK 21 cannot emulate source levels below its supported release range; earlier declarations use release 8 for source-metric compatibility. This does not establish historical build equivalence. Where an early inherited/default setting was unavailable, the Java 8 compatibility assumption is explicit.

The JDK archive, Python parser wheels and legacy grammar distribution have separate checksum locks. Annotation processing and implicit class generation are disabled in the Java scanner; target application code is not executed. Classpath inputs, when supplied to the adapter, are content-hashed. The default annual campaign supplies no external classpath, so unresolved dependencies remain visible. Root build release settings do not fully describe mixed-level optional modules; those syntax and attribution failures remain explicit until per-module build configurations are supported. Runtime compilation of the adapter is not a build or smoke test of Jenkins, Tomcat or Odoo.

Each campaign observation regenerates the syntax report and semantic report twice when `--replay` is selected. Canonical equality covers findings, inventories, metrics, diagnostics and tool provenance. Java uses a fresh extraction directory for each pass. This demonstrates computational repeatability from the same sealed Git source archives, not independent repository acquisition or independent algorithm validation.

`admitted` remains false. A complete rule measurement is not automatically thesis-admitted. Missing values are null, and incomplete observed counts must not be plotted as whole-repository prevalence.

## Primary references

- Existing definitions: `src/HybridLens.StaticAnalysis/Detectors/` and `Metrics/ClassMetrics.cs`.
- [JavacTask compiler attribution API](https://docs.oracle.com/javase/8/docs/jdk/api/javac/tree/com/sun/source/util/JavacTask.html).
- [PEP 702: marking deprecations using the type system](https://peps.python.org/pep-0702/).
- [Python 3.13 warning and deprecation documentation](https://docs.python.org/3.13/library/warnings.html).

These references explain the underlying mechanisms. They do not constitute validation of the custom language mappings or the resulting prevalence estimates.
