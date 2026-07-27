using HybridLens.Core.Models;

namespace HybridLens.ContextBuilder;

/// <summary>
/// Versioned prompt for the separate, pre-repair visible characterization-test generator.
/// Deliberately contains no anti-pattern label, detector finding, metric, truth record, or repair.
/// </summary>
public static class CharacterizationTestPrompt
{
    public const string Version = "v1.1.0";

    public const string SystemPrompt = """
        You are authoring a regression characterization test for existing C# production code.
        Capture observable behaviour through the public interface exactly as it exists. Do not
        improve, refactor, repair, or diagnose the production code. Do not infer intended behaviour
        that is not observable from the supplied pristine source.

        The pipeline owns the test project and provides a static Check helper with these methods:
        Check.True(bool), Check.False(bool), Check.NotNull(object?),
        Check.Equal<T>(T expected, T actual), and
        Check.SequenceEqual<T>(IEnumerable<T> expected, IEnumerable<T> actual).

        Return ONLY one JSON object in this exact shape, with no markdown fences:
        {
          "test_name": "<short descriptive name that does not mention code smells or anti-patterns>",
          "using_directives": ["using Namespace;"],
          "test_body": "<C# statements for one public-behaviour characterization scenario>"
        }

        Requirements:
        - Exercise observable behaviour through the supplied target declaration.
        - Treat its symbol and source line range only as neutral coordinates, not as a diagnosis.
        - Instantiate or invoke the supplied production code through public members.
        - Derive expected values from the pristine behaviour shown in the source.
        - Include at least one meaningful Check assertion over a production result.
        - Do not assert constants against themselves and do not use Check.True(true).
        - Do not use reflection, file or network I/O, processes, environment variables, clocks,
          sleeps, randomness, package installation, mocks, or external state.
        - Do not declare namespaces, classes, helper types, or a Main method.
        - Do not modify production code or project configuration.
        """;

    public static string BuildUserPrompt(
        string relativePath,
        string projectName,
        string pristineSource,
        BlindedTargetDescriptor target) =>
        $"""
        ## Production project
        {projectName}

        ## Target declaration
        Symbol: {target.SymbolName}
        Source lines: {target.StartLine}-{target.EndLine}

        Characterise existing observable behaviour exercised through this declaration.
        The target coordinates do not state why the declaration was selected.

        ## Pristine source file
        {relativePath}

        ```csharp
        {pristineSource}
        ```
        """;
}
