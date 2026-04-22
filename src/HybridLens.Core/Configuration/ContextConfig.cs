namespace HybridLens.Core.Configuration;

public sealed class ContextConfig
{
    public ContextStrategy Strategy { get; set; } = ContextStrategy.PerFinding;

    /// <summary>Maximum tokens to use for context per LLM request.</summary>
    public int TokenBudget { get; set; } = 2000;

    /// <summary>Number of surrounding lines to include around a finding snippet.</summary>
    public int SnippetContextLines { get; set; } = 10;

    /// <summary>Path to prompt template directory. Templates are named by AntiPatternType (e.g. LongMethod.txt).</summary>
    public string TemplateDirectory { get; set; } = "templates";

    /// <summary>Arbitrary key-value pairs injected into every prompt (e.g. project name, framework version).</summary>
    public IDictionary<string, string> Metadata { get; set; } = new Dictionary<string, string>();
}

public enum ContextStrategy
{
    PerFinding,
    PerFile,
    PerClass
}
