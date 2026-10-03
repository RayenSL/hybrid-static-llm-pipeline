# Experimental complexity mapping

Rule identifier: `experimental.cc.named-definition.v0`. This is a feasibility implementation, not a claim of equivalence with HybridLens's existing `LongMethod` rule.

Every named definition with a body starts at complexity 1. Python functions, including methods and nested named functions, are eligible. Java methods and constructors with bodies are eligible. C/C++ function definitions are eligible; macros and header language/configuration semantics remain unresolved. Abstract signatures and anonymous functions are not denominators. Nested callable and class bodies do not contribute decisions to their enclosing callable. They may produce their own eligible named definitions.

Syntax nodes counted by the Tree-sitter adapter are listed explicitly in `DECISIONS` and the switch/short-circuit handling in `syntax_probe.py`. If/elif, loops, catch/except, ternary expressions and short-circuit operators contribute decisions. Python comprehension clauses are included. A non-default switch/case clause contributes a decision; this is not yet validated for all pattern alternatives or guards. Threshold > 10 produces an experimental finding; > 15 and > 20 counts are retained for planned sensitivity analysis. No severity claim is inferred from the resulting count.

The legacy Python adapter has an independently expressed CST mapping for equivalent supported constructs. Historical Python soft keywords, exec statements and source encodings are supported without rewriting source. The Python 2 versus early Python 3 mode is recorded in the scope. It requires CPython 3.12's lib2to3 package, which is not guaranteed to exist in later Python runtimes. Grammar and adapter hashes are included in result provenance.

The current C# detector enumerates `MethodDeclarationSyntax`, excluding constructors, and traverses descendant nodes when calculating complexity. This adapter includes Java constructors and excludes nested callable bodies from enclosing counts. Consequently, the existing Json.NET numbers and these experimental values must not be pooled or labelled identical measures. A common admitted rule will need a separately validated C# mapping if Json.NET is ever included in the cross-language study.

Evidence coordinates: byte offsets are zero-based, end-exclusive, relative to the original source file. Lines are one-based. Columns are zero-based byte offsets within a line. A finding carries the entire source-file digest, snippet digest and symbol kind. Its identifier is stable for the same file/span/language but does not identify a finding across edits or renames.

The tests cover selected construct semantics, byte-span preservation for Latin-1 Python source, malformed input, null versus zero prevalence, and tampered envelopes. An empirical validation sample, independent measurement comparison, complete native preprocessing support, God Class and obsolete-API modules remain future work before a broader admitted campaign.


The separate three-rule suite is now implemented; see `SEMANTIC_RULES.md` for its source-semantic mappings and outstanding coverage limitations. This document and contract 0.1 describe the original syntax probe only.
