using Microsoft.Build.Locator;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp.Formatting;
using Microsoft.CodeAnalysis.MSBuild;

namespace HybridLens.StaticAnalysis.Workspace;

public sealed class WorkspaceLoader : IDisposable
{
    // Diagnostics that are purely noise — they don't affect whether a project loads
    private static readonly string[] SilentFragments =
    [
        "vulnerability data",
        "Unable to load the service index",
        "401 (Unauthorized)",
        "is not associated with a language"
    ];

    private readonly MSBuildWorkspace _workspace;
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

    public WorkspaceLoader()
    {
        _workspace = MSBuildWorkspace.Create();
        _workspace.WorkspaceFailed += OnWorkspaceFailed;
    }

    /// <summary>
    /// Loads all C# projects from a .sln or .csproj and returns their compilations.
    /// Projects that fail to load are skipped and recorded in <see cref="Warnings"/>.
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
        var compilation = await project.GetCompilationAsync(cancellationToken);

        return compilation is not null ? [compilation] : [];
    }

    private void OnWorkspaceFailed(object? sender, WorkspaceDiagnosticEventArgs e)
    {
        var message = e.Diagnostic.Message;

        // Completely silent — noise from inaccessible feeds, non-C# projects, etc.
        if (SilentFragments.Any(f => message.Contains(f, StringComparison.OrdinalIgnoreCase)))
            return;

        // Everything else (project config issues, missing SDKs, etc.) is a warning.
        // The affected project will yield a null compilation and be skipped automatically.
        _warnings.Add($"[{e.Diagnostic.Kind}] {message}");
    }

    public void Dispose()
    {
        _workspace.WorkspaceFailed -= OnWorkspaceFailed;
        _workspace.Dispose();
    }
}
