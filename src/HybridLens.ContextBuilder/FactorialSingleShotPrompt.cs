using HybridLens.Core.Models;

namespace HybridLens.ContextBuilder;

/// <summary>Independent one-call direct-edit prompt for the grounding x visible-test factorial cells.</summary>
public static class FactorialSingleShotPrompt
{
    public const string Version = "v1.1.0";

    public const string GroundedSystemPrompt = """
        You are repairing a supplied, already-located Long Method or God Class finding in one C# file.
        Return one complete edited production file. Preserve observable behaviour and the public contract.
        You have one response and receive no build or test feedback. When a characterization test is
        supplied it is immutable evidence of existing behaviour: do not rewrite, weaken, or work around it.

        Respond ONLY with one JSON object:
        {
          "edited_file": "<full edited C# source>",
          "findings": [{"anti_pattern":"<GodClass|LongMethod>","symbol":"<symbol>","line":<int>,"remediation":"<what changed>"}]
        }
        """;

    public const string UngroundedSystemPrompt = """
        You are given one complete C# file and neutral coordinates for one target declaration. Diagnose
        whether that target is a Long Method or God Class and repair that target by returning one complete
        edited production file. The target coordinates are not a static-analysis diagnosis. Preserve observable behaviour and
        the public contract. You have one response and receive no build or test feedback. When a
        characterization test is supplied it is immutable evidence of existing behaviour: do not rewrite,
        weaken, or work around it.

        Respond ONLY with one JSON object:
        {
          "edited_file": "<full edited C# source, or the original source when no occurrence is found>",
          "findings": [{"anti_pattern":"<GodClass|LongMethod>","symbol":"<symbol>","line":<int>,"remediation":"<what changed>"}]
        }
        Use an empty findings array when no occurrence is found.
        """;

    public static string BuildUserPrompt(
        string relativePath,
        string pristineSource,
        BlindedTargetDescriptor target,
        string? groundingBlock,
        LoadedVisibleTestPrompt? visibleTest)
    {
        var grounding = string.IsNullOrWhiteSpace(groundingBlock)
            ? string.Empty
            : $"## Static-analysis finding (repair this occurrence)\n{groundingBlock.TrimEnd()}\n\n";
        var prompt = $$"""
            ## Neutral target declaration
            Symbol: {{target.SymbolName}}
            Source lines: {{target.StartLine}}-{{target.EndLine}}
            These coordinates identify the common repair unit but provide no anti-pattern label or metrics.

            {{grounding}}## Pristine source file: {{relativePath}}
            ```csharp
            {{pristineSource}}
            ```
            """;
        return PromptTemplate.AppendImmutableVisibleTest(prompt, visibleTest);
    }
}

public sealed record LoadedVisibleTestPrompt(
    string Name,
    IReadOnlyList<string> UsingDirectives,
    string Body,
    string Sha256);
