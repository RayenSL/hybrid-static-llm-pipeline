namespace HybridLens.Core.Configuration;

public sealed class WorkspaceConfig
{
    /// <summary>
    /// When true, projects whose names match common test project suffixes are excluded.
    /// Matches: *.Tests, *.IntegrationTests, *.EndToEndTests, *.TestInfrastructure
    /// </summary>
    public bool ExcludeTestProjects { get; set; } = true;

    /// <summary>
    /// Wildcard patterns for project assembly names to explicitly exclude.
    /// Example: ["*.Client", "*.Client.*", "AppHost"]
    /// </summary>
    public IList<string> ExcludePatterns { get; set; } = [];

    /// <summary>
    /// Wildcard patterns for project assembly names to include.
    /// When non-empty, only projects matching at least one pattern are analysed.
    /// Example: ["Ibis.MKI.*.Core", "Ibis.MKI.*.Server"]
    /// </summary>
    public IList<string> IncludePatterns { get; set; } = [];
}
