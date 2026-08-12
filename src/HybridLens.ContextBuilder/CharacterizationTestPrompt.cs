using System.Text.Json;
using System.Text.Json.Serialization;
using HybridLens.Core.Models;

namespace HybridLens.ContextBuilder;

/// <summary>
/// Versioned, diagnosis-blind prompts for planning and implementing a pre-repair behavioural suite.
/// The optional third call is restricted to compiler diagnostics and cannot observe test execution.
/// </summary>
public static class CharacterizationTestPrompt
{
    public const string Version = "v2.0.0";
    public const string PlanVersion = Version + ".plan";
    public const string ImplementationVersion = Version + ".implementation";
    public const string CompileCorrectionVersion = Version + ".compile-correction";

    public const string PlanSystemPrompt = """
        You are planning regression characterisation tests for existing C# production code.
        Work only from observable public behaviour in the pristine source and neutral dependency
        context. Do not diagnose, improve, refactor or repair the production code.

        Return ONLY one JSON object with suite_name and exactly five cases. Use these identifiers
        and categories once each, in this order:
        - H1 / happy_path: one representative valid end-to-end flow.
        - E1 / empty_or_invalid: the most relevant empty, minimal, null or invalid-input flow.
        - B1 / boundary_values: below, at and above one source-supported boundary. Put all three
          stimuli in inputs. If there is no numeric threshold, use the closest three-point
          cardinality or ordering boundary supported by the public contract.
        - A1 / alternative_path: a materially different valid branch, mode or input partition.
        - D1 / dependency_or_state: a deterministic dependency outcome, repeated invocation,
          duplicate input or state transition, choosing the first applicable option in that order.

        Each case must contain case_id, category, source_evidence, input_partition, inputs and
        expected_observation. Every input partition must differ. Evidence and expected observations
        must describe behaviour visible in the supplied pristine code; do not invent requirements.
        Do not include C# test code in this planning response.
        """;

    public const string SystemPrompt = """
        You are implementing a frozen regression characterisation-test plan for existing C# code.
        Capture observable behaviour through public members exactly as it exists. Do not improve,
        refactor, repair or diagnose production code, and do not infer intended behaviour.

        The pipeline supplies Check.True, Check.False, Check.Null, Check.NotNull, Check.Equal,
        Check.SequenceEqual and Check.Throws<TException>(Action). Return ONLY one JSON object:
        {
          "suite_name": "short neutral name",
          "using_directives": ["using Namespace;"],
          "helper_code": "optional deterministic in-memory fake types",
          "cases": [
            {"case_id":"H1","category":"happy_path","test_name":"...","test_body":"..."},
            {"case_id":"E1","category":"empty_or_invalid","test_name":"...","test_body":"..."},
            {"case_id":"B1","category":"boundary_values","test_name":"...","test_body":"..."},
            {"case_id":"A1","category":"alternative_path","test_name":"...","test_body":"..."},
            {"case_id":"D1","category":"dependency_or_state","test_name":"...","test_body":"..."}
          ]
        }

        Requirements:
        - Implement exactly five cases and preserve the plan identifiers and categories.
        - Give each case fresh setup, invoke production code and include a meaningful assertion.
        - B1 must exercise the plan's below, at and above stimuli in the same case.
        - helper_code may declare only deterministic in-memory fakes needed by these cases.
        - Fakes may record calls and return fixed values; do not use mocking packages.
        - Do not assert constants against themselves or use Check.True(true).
        - Do not use reflection, file or network I/O, processes, environment variables, clocks,
          sleeps, randomness, package installation or mutable external state.
        - Do not declare a namespace or Main method and do not modify production code or projects.
        """;

    public const string CompileCorrectionSystemPrompt = """
        Correct compilation errors in a generated C# characterisation suite. You receive the
        frozen plan, previous structured suite and compiler diagnostics only. Return the complete
        suite in the same JSON schema. Preserve all five case identifiers, categories, test names
        and test bodies exactly.
        You may change only using directives and deterministic helper code needed for compilation.
        Do not add, remove or weaken an assertion. Do not infer expected values
        from the diagnostics. Return JSON only.
        """;

    public static string BuildPlanUserPrompt(
        string relativePath,
        string projectName,
        string pristineSource,
        string dependencyContext,
        BlindedTargetDescriptor target) =>
        BuildSourceContext(relativePath, projectName, pristineSource, dependencyContext, target);

    public static string BuildImplementationUserPrompt(
        string relativePath,
        string projectName,
        string pristineSource,
        string dependencyContext,
        BlindedTargetDescriptor target,
        GeneratedTestPlan plan) =>
        BuildSourceContext(relativePath, projectName, pristineSource, dependencyContext, target) +
        "\n\n## Frozen five-case plan\n" + JsonSerializer.Serialize(plan, JsonOptions);

    public static string BuildCompileCorrectionUserPrompt(
        GeneratedTestPlan plan,
        string previousSuiteJson,
        string compilerDiagnostics) =>
        $"""
        ## Frozen plan
        {JsonSerializer.Serialize(plan, JsonOptions)}

        ## Previous suite
        {previousSuiteJson}

        ## Compiler diagnostics
        {compilerDiagnostics}
        """;

    // Retained as a source-compatible alias for callers outside the generator.
    public static string BuildUserPrompt(
        string relativePath,
        string projectName,
        string pristineSource,
        BlindedTargetDescriptor target) =>
        BuildPlanUserPrompt(relativePath, projectName, pristineSource, string.Empty, target);

    private static string BuildSourceContext(
        string relativePath,
        string projectName,
        string pristineSource,
        string dependencyContext,
        BlindedTargetDescriptor target) =>
        $"""
        ## Production project
        {projectName}

        ## Target declaration
        Symbol: {target.SymbolName}
        Source lines: {target.StartLine}-{target.EndLine}
        These coordinates identify the common test unit but contain no diagnosis.

        ## Pristine source file: {relativePath}
        ```csharp
        {pristineSource}
        ```

        ## Neutral public dependency context
        {dependencyContext}
        """;

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower) },
        WriteIndented = true
    };
}
