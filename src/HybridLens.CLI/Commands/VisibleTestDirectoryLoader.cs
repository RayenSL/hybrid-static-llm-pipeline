using HybridLens.Pipeline;

namespace HybridLens.CLI.Commands;

/// <summary>
/// Loads only admitted, hash-valid generated tests. Rejected, malformed, and missing artefacts remain
/// unavailable inside an assigned test-enabled cell, preserving intention-to-treat analysis.
/// </summary>
internal static class VisibleTestDirectoryLoader
{
    public static async Task<Dictionary<string, LoadedGeneratedTest>> LoadAsync(
        string directory,
        CancellationToken cancellationToken)
    {
        var result = new Dictionary<string, LoadedGeneratedTest>(StringComparer.OrdinalIgnoreCase);
        foreach (var path in Directory.EnumerateFiles(directory, "*.json", SearchOption.TopDirectoryOnly))
        {
            try
            {
                var loaded = await GeneratedTestArtifactLoader.LoadAdmittedAsync(path, cancellationToken);
                result[Path.GetFullPath(loaded.Artifact.SourceFile)] = loaded;
            }
            catch (InvalidDataException)
            {
                // Persisted rejections and malformed artefacts are expected unavailable-test outcomes.
            }
        }
        return result;
    }
}
