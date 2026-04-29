using HybridLens.Core.Configuration;
using Microsoft.Build.Locator;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp.Formatting;
using Microsoft.CodeAnalysis.MSBuild;

namespace HybridLens.StaticAnalysis.Workspace;

public sealed class WorkspaceLoader : IDisposable
{
    private static readonly string[] TestProjectSuffixes =
    [
        ".Tests", ".IntegrationTests", ".EndToEndTests", ".EndToEndTestsSharding",
        ".TestInfrastructure", ".Specs"
    ];

    // Diagnostics that are purely noise — they don't affect whether a project loads
    private static readonly string[] SilentFragments =
    [
        "vulnerability data",
        "Unable to load the service index",
        "401 (Unauthorized)",
        "is not associated with a language"
    ];

    private readonly MSBuildWorkspace _workspace;
    private readonly WorkspaceConfig _config;
    private readonly List<string> _warnings = [];

    /// <summary>Non-fatal diagnostics collected during the last <see cref="LoadAsync"/> call.</summary>
    public IReadOnlyList<string> Warnings => _warnings;

    static WorkspaceLoader()
    {
        if (!MSBuildLocator.IsRegistered)
            MSBuildLocator.RegisterDefaults();

        // Force Microsoft.CodeAnalysis.CSharp.Workspaces to load so MSBuildWorkspace
        // can discover the C# language services via MEF. Without this the runtime never
        // loads the assembly and the workspace throws "language 'C#' is not supported".
        _ = typeof(CSharpFormattingOptions);
    }

    public WorkspaceLoader(WorkspaceConfig config)
    {
        _config = config;
        _workspace = MSBuildWorkspace.Create();
        _workspace.WorkspaceFailed += OnWorkspaceFailed;
    }

    /// <summary>
    /// Loads all C# projects from a .sln or .csproj and returns their compilations.
    /// Projects that fail to load or are excluded by config are skipped.
    /// Skipped projects due to failures are recorded in <see cref="Warnings"/>.
    /// </summary>
    public async Task<IReadOnlyList<Compilation>> LoadAsync(
        string path,
        CancellationToken cancellationToken = default)
    {
        _warnings.Clear();

        var extension = Path.GetExtension(path).ToLowerInvariant();

        return extension switch
        {
            ".sln"    => await LoadSolutionAsync(path, cancellationToken),
            ".csproj" => await LoadProjectAsync(path, cancellationToken),
            _ => throw new ArgumentException(
                $"Unsupported file type '{extension}'. Expected .sln or .csproj.", nameof(path))
        };
    }

    private async Task<IReadOnlyList<Compilation>> LoadSolutionAsync(
        string path,
        CancellationToken cancellationToken)
    {
        var solution = await _workspace.OpenSolutionAsync(path, cancellationToken: cancellationToken);
        var compilations = new List<Compilation>();

        foreach (var project in solution.Projects)
        {
            if (!IsIncluded(project.Name))
                continue;

            var compilation = await project.GetCompilationAsync(cancellationToken);
            if (compilation is not null)
                compilations.Add(compilation);
        }

        return compilations;
    }

    private async Task<IReadOnlyList<Compilation>> LoadProjectAsync(
        string path,
        CancellationToken cancellationToken)
    {
        var project = await _workspace.OpenProjectAsync(path, cancellationToken: cancellationToken);

        if (!IsIncluded(project.Name))
            return [];

        var compilation = await project.GetCompilationAsync(cancellationToken);
        return compilation is not null ? [compilation] : [];
    }

    private bool IsIncluded(string projectName)
    {
        if (_config.ExcludeTestProjects &&
            TestProjectSuffixes.Any(suffix => projectName.EndsWith(suffix, StringComparison.OrdinalIgnoreCase)))
            return false;

        if (_config.ExcludePatterns.Any(pattern => Matches(projectName, pattern)))
            return false;

        if (_config.IncludePatterns.Count > 0 &&
            !_config.IncludePatterns.Any(pattern => Matches(projectName, pattern)))
            return false;

        return true;
    }

    private static bool Matches(string name, string pattern)
    {
        // Translate wildcard pattern (* and ?) into a simple character-by-character match
        return WildcardMatch(name, pattern, StringComparison.OrdinalIgnoreCase);
    }

    private static bool WildcardMatch(string input, string pattern, StringComparison comparison)
    {
        // dp[i][j] = input[0..i-1] matches pattern[0..j-1]
        var dp = new bool[input.Length + 1, pattern.Length + 1];
        dp[0, 0] = true;

        for (var j = 1; j <= pattern.Length; j++)
            if (pattern[j - 1] == '*')
                dp[0, j] = dp[0, j - 1];

        for (var i = 1; i <= input.Length; i++)
        for (var j = 1; j <= pattern.Length; j++)
        {
            if (pattern[j - 1] == '*')
                dp[i, j] = dp[i - 1, j] || dp[i, j - 1];
            else if (pattern[j - 1] == '?' ||
                     string.Compare(input, i - 1, pattern, j - 1, 1, comparison) == 0)
                dp[i, j] = dp[i - 1, j - 1];
        }

        return dp[input.Length, pattern.Length];
    }

    private void OnWorkspaceFailed(object? sender, WorkspaceDiagnosticEventArgs e)
    {
        var message = e.Diagnostic.Message;

        if (SilentFragments.Any(f => message.Contains(f, StringComparison.OrdinalIgnoreCase)))
            return;

        _warnings.Add($"[{e.Diagnostic.Kind}] {message}");
    }

    public void Dispose()
    {
        _workspace.WorkspaceFailed -= OnWorkspaceFailed;
        _workspace.Dispose();
    }
}
