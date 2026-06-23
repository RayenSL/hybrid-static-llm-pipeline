namespace HybridLens.ContextBuilder;

/// <summary>
/// Versioned prompt definition.
///
/// Every persisted <c>RunRecord</c> stores <see cref="Version"/> so that experiments
/// run against different prompt revisions can be separated cleanly during analysis.
///
/// <b>Versioning rule (Req #4)</b>: do not silently change the prompt.
/// Any change to <see cref="SystemPrompt"/> or to the user-prompt structure produced
/// by <c>ContextBuilder</c> must increment <see cref="Version"/>.
///
/// <para>
/// <b>v1.0.0</b> — initial 2-section structured response (explanation + remediation).
/// </para>
/// <para>
/// <b>v1.1.0</b> — adds an explicit ISO/IEC 25010 quality-impact section so the LLM's
/// inferred quality attributes can be evaluated against the literature-derived ground
/// truth in <c>QualityAttributeMap</c>. The expected attributes are <i>not</i> injected
/// into the prompt — the LLM must infer them from the code.
/// </para>
/// </summary>
public static class PromptTemplate
{
    public const string Version = "v1.1.0";

    public const string SystemPrompt = """
        You are a .NET code quality expert. You will be given a code anti-pattern finding.

        Explain the impact of this anti-pattern on relevant ISO/IEC 25010 software
        quality attributes. Focus on attributes such as maintainability, analysability,
        modifiability, testability, security, reliability, and compatibility where
        applicable. Only mention attributes that are genuinely relevant — do not
        enumerate every attribute by default.

        Respond ONLY with a JSON object in this exact format, with no additional text:
        {
          "explanation": "<why this is a problem and what its impact is>",
          "quality_impact": "Quality impact:\n- Attribute: short explanation\n- Attribute: short explanation",
          "remediation": "<concrete refactoring steps; include a short code example where helpful>"
        }
        """;

    // ── LLM-only condition (§4.4.1, Appendix E) ──────────────────────────────
    //
    // v1.2.0 differs from the hybrid prompt in three ways: the model must DETECT
    // occurrences before explaining; it receives NO finding header/metrics/label;
    // and it sees the WHOLE source file. The response is a JSON ARRAY of located
    // findings (0, 1, or many), enabling matching against the known instances.

    public const string LlmOnlyVersion = "v1.2.0";

    public const string LlmOnlySystemPrompt = """
        You are a .NET code quality expert. You will be given a complete C# source file.
        Identify every occurrence of the following anti-patterns in the file:
        - God Class
        - Long Method
        - Obsolete API usage

        For each occurrence you find, report its location and explain its impact on the
        relevant ISO/IEC 25010 software quality attributes, and suggest a repair. Focus
        on attributes such as maintainability, analysability, modifiability, testability,
        security, reliability, and compatibility where applicable. Only mention attributes
        that are genuinely relevant. If you find no occurrences, return an empty list.

        Respond ONLY with a JSON array in this exact format, with no additional text:
        [
          {
            "anti_pattern": "<GodClass | LongMethod | ObsoleteApiUsage>",
            "location": { "symbol": "<class or method name>", "line": <int> },
            "explanation": "<why this is a problem and what its impact is>",
            "quality_impact": "Quality impact:\n- Attribute: short explanation\n- ...",
            "remediation": "<concrete refactoring steps; include a short code example where helpful>"
          }
        ]
        """;

    /// <summary>Wraps a whole source file as the LLM-only user prompt (Appendix E.2).</summary>
    public static string BuildLlmOnlyUserPrompt(string relativePath, string fileContent) =>
        $"## Source file: {relativePath}\n```csharp\n{fileContent}\n```";

    // ── Repair applier (objective repair verification, §4.5.1 / §4.7.1, Appendix A.1) ──
    //
    // A separate, NON-evaluated Claude-family model applies each repair suggestion to the
    // source under this frozen prompt. Strict-literal: it implements only what the repair
    // states, makes no design decisions, and returns a structured unapplicable verdict when
    // the suggestion is too vague. Applier outputs are frozen as artefacts so the apply step
    // is reproducible despite the applier's stochasticity.

    public const string ApplierVersion = "v1.0.0";

    public const string ApplierSystemPrompt = """
        You are a code-editing tool, not a code reviewer. You will be given a C# source
        file, an anti-pattern finding, and a proposed repair. Apply ONLY the changes the
        proposed repair explicitly specifies. Do not add improvements, do not fix
        anything the repair does not mention, and do not make design decisions the repair
        leaves open. If the repair is too vague to apply without inventing specifics
        (e.g. "refactor to follow SRP" with no concrete partition), do not guess.

        Respond ONLY with a JSON object, no additional text:
        {
          "applicable": <true|false>,
          "reason_if_not": "<why the repair cannot be applied literally, or empty>",
          "edited_file": "<the full edited source if applicable, else empty>"
        }
        """;

    /// <summary>
    /// Builds the applier user prompt (Appendix A.1): the finding, the proposed repair, and
    /// the full original source. The applier returns the whole edited file or an unapplicable verdict.
    /// </summary>
    public static string BuildApplierUserPrompt(
        string antiPattern, string symbol, string location,
        string repairText, string relativePath, string originalSource) =>
        $"""
        ## Anti-pattern finding
        Type: {antiPattern}
        Symbol: {symbol}
        Location: {location}

        ## Proposed repair
        {repairText}

        ## Source file: {relativePath}
        ```csharp
        {originalSource}
        ```
        """;
}
