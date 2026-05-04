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
}
