using HybridLens.Core.Models;

namespace HybridLens.Core.Configuration;

public sealed class ContextConfig
{
    public ContextStrategy Strategy { get; set; } = ContextStrategy.PerFinding;

    /// <summary>Controls how much context is injected into each LLM prompt.</summary>
    public ContextLevel Level { get; set; } = ContextLevel.Structural;

    /// <summary>Maximum tokens to use for context per LLM request.</summary>
    public int TokenBudget { get; set; } = 2000;

    /// <summary>Number of surrounding lines to include around a finding snippet.</summary>
    public int SnippetContextLines { get; set; } = 10;

    /// <summary>Path to prompt template directory. Templates are named by AntiPatternType (e.g. LongMethod.txt).</summary>
    public string TemplateDirectory { get; set; } = "templates";

    /// <summary>Arbitrary key-value pairs injected into every prompt (e.g. project name, framework version).</summary>
    public IDictionary<string, string> Metadata { get; set; } = new Dictionary<string, string>();

    /// <summary>
    /// The ladder that defines what <see cref="Level"/> means. Defaults to the sealed supplement's
    /// ladder so existing callers keep their exact behaviour; the direct-editing campaign selects
    /// <see cref="ContextLadder.V2"/>, whose Full rung is cross-file rather than metadata-only.
    /// </summary>
    public IReadOnlyList<ContextLevelSpec> Ladder { get; set; } = ContextLadder.V1;

    /// <summary>
    /// Declaring sources resolved during preflight and frozen into the manifest. Only rendered when
    /// the level's spec asks for cross-file scope; empty everywhere in the sealed supplement.
    /// </summary>
    public IReadOnlyList<CrossFileDeclaration> CrossFileDeclarations { get; set; } = [];
}

public enum ContextStrategy
{
    PerFinding,
    PerFile,
    PerClass
}
