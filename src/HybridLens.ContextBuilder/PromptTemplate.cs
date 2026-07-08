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

    // ── Agentic condition (§4.4.1, Appendix E, prompt v2.0.0) ────────────────
    //
    // v2.0.0 replaces the single-shot whole-file prompt with an AUTONOMOUS LOOP. It differs
    // from the hybrid prompt in four ways: the model must DETECT occurrences before repairing;
    // it receives NO finding header/metrics/label; it sees the WHOLE source file; and it is
    // granted exactly one tool — a compiler it may invoke repeatedly, observing build results
    // between calls, until it declares completion or the iteration budget is exhausted. Each
    // turn is a JSON OBJECT carrying an action, the full edited file, and the located findings.
    // The detector is never exposed (only the compiler), keeping the arm ungrounded.

    public const string AgenticVersion = "v2.0.0";

    /// <summary>
    /// The agentic system prompt (Appendix E.1). Contains the literal token
    /// <c>{ITERATION_BUDGET}</c>; <see cref="BuildAgenticSystemPrompt"/> substitutes the frozen budget.
    /// </summary>
    public const string AgenticSystemPromptTemplate = """
        You are a .NET code quality expert operating as an autonomous agent. You are given a
        complete C# source file. Your task is to (1) identify every occurrence of the following
        anti-patterns in the file, and (2) repair them by editing the source:

        - God Class
        - Long Method
        - Obsolete API usage

        You work in a loop. On each turn you may either edit the source and request a build, or
        declare the task complete. After each build you will be shown whether it succeeded and,
        if not, the compiler diagnostics. Use this feedback to revise your edits. You have at most
        {ITERATION_BUDGET} build attempts. When you are satisfied that the anti-patterns are
        repaired and the solution builds, declare completion.

        You have exactly one tool: a compiler that builds the current state of the file and returns
        success or the diagnostic errors. You have no other tools and no access to static-analysis
        output.

        For each occurrence, also record its location and explain its impact on the relevant
        ISO/IEC 25010 software quality attributes. Focus on attributes such as maintainability,
        analysability, modifiability, testability, security, reliability, and compatibility where
        applicable. Only mention attributes that are genuinely relevant. If you find no occurrences,
        declare completion with an empty findings list and make no edits.

        Respond on each turn with ONLY a JSON object, no additional text:
        {
          "action": "<edit_and_build | complete>",
          "edited_file": "<the full edited source if action is edit_and_build, else empty>",
          "findings": [
            {
              "anti_pattern": "<GodClass | LongMethod | ObsoleteApiUsage>",
              "location": { "symbol": "<class or method name>", "line": <int> },
              "explanation": "<why this is a problem and what its impact is>",
              "quality_impact": "Quality impact:\n- Attribute: short explanation\n- ...",
              "remediation": "<what you changed and why>"
            }
          ]
        }
        """;

    /// <summary>The agentic system prompt with the frozen iteration budget substituted (Appendix E.1).</summary>
    public static string BuildAgenticSystemPrompt(int iterationBudget) =>
        AgenticSystemPromptTemplate.Replace("{ITERATION_BUDGET}", iterationBudget.ToString());

    /// <summary>Wraps the whole, unannotated source file as the opening agentic user prompt (Appendix E.2).</summary>
    public static string BuildAgenticUserPrompt(string relativePath, string fileContent) =>
        $"## Source file: {relativePath}\n```csharp\n{fileContent}\n```";

    /// <summary>
    /// Opening user prompt for the grounded-iterative arm (§4.4.1, §5.1.5). Identical to the ungrounded
    /// agentic prompt except that it is preceded by the analyser's Structural-level finding block(s)
    /// (rendered by <c>ContextBuilder</c> at <see cref="ContextLevel.Structural"/>), so the detector's
    /// output is routed into the loop rather than withheld. The system prompt, loop, compiler-only tool,
    /// and iteration budget are unchanged — this arm differs from the ungrounded one only here, which is
    /// what lets the H1c contrast vary grounding alone (and, as a consequence, relieves it of detection).
    /// </summary>
    public static string BuildGroundedIterativeUserPrompt(string relativePath, string fileContent, string findingBlock) =>
        $"## Static-analysis findings (already located by the analyser — repair these occurrences)\n{findingBlock.TrimEnd()}\n\n## Source file: {relativePath}\n```csharp\n{fileContent}\n```";

    /// <summary>
    /// Build-result feedback fed back as the next user turn after an <c>edit_and_build</c> action.
    /// On success the agent is invited to declare completion; on failure it is shown the diagnostics.
    /// </summary>
    public static string BuildAgenticBuildFeedback(int attempt, int budget, bool ok, string diagnostics)
        => ok
            ? $"## Build result (attempt {attempt}/{budget}): SUCCESS\n" +
              "The solution compiles. If every targeted anti-pattern is now repaired, respond with " +
              "action \"complete\" and your final findings. Otherwise continue editing."
            : $"## Build result (attempt {attempt}/{budget}): FAILED\n```\n{diagnostics}\n```\n" +
              "Revise the edited file to fix these compiler errors, or declare completion.";

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
