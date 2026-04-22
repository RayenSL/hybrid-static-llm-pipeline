namespace HybridLens.Core.Configuration;

public sealed class DetectorConfig
{
    public GodClassConfig GodClass { get; set; } = new();
    public LongMethodConfig LongMethod { get; set; } = new();
    public ObsoleteApiConfig ObsoleteApi { get; set; } = new();
}

public sealed class GodClassConfig
{
    public int MaxMethods { get; set; } = 20;
    public int MaxFields { get; set; } = 15;
    public int MaxLinesOfCode { get; set; } = 500;
}

public sealed class LongMethodConfig
{
    public int MaxLinesOfCode { get; set; } = 50;
    public int MaxCyclomaticComplexity { get; set; } = 10;
}

public sealed class ObsoleteApiConfig
{
    /// <summary>Additional namespace prefixes to flag beyond [Obsolete] attribute detection.</summary>
    public IList<string> DeprecatedNamespacePrefixes { get; set; } = [];
}
