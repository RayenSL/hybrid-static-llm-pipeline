using HybridLens.Core.Models;

namespace HybridLens.Pipeline;

public static class FactorialCampaignPreflight
{
    public static async Task<Dictionary<string, LoadedGeneratedTest>> LoadVisibleTestsAsync(
        FactorialCampaignManifest manifest,
        CancellationToken cancellationToken)
    {
        var result = new Dictionary<string, LoadedGeneratedTest>(StringComparer.OrdinalIgnoreCase);
        foreach (var assignment in manifest.Assignments.Where(a => a.VisibleTestArtifactRef is not null))
        {
            var path = Path.GetFullPath(assignment.VisibleTestArtifactRef!);
            if (result.ContainsKey(path)) continue;
            var loaded = await GeneratedTestArtifactLoader.LoadAdmittedAsync(path, cancellationToken);
            if (!Path.GetFullPath(loaded.Artifact.ArtifactRef).Equals(path, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException($"visible-test artifact_ref does not identify its manifest file: {path}");
            if (!Path.GetFullPath(loaded.Artifact.SourceFile)
                    .Equals(Path.GetFullPath(assignment.FilePath), StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException($"visible test is mapped to a different source file: {path}");
            if (!string.Equals(loaded.Artifact.TestSha256, assignment.VisibleTestSha256, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException($"visible-test hash changed after manifest freeze: {path}");
            if (!string.Equals(loaded.Artifact.SourceSha256, assignment.PristineSourceSha256, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException($"visible test is bound to a different source revision: {path}");
            if (!string.Equals(loaded.Artifact.TargetSymbolName, assignment.SymbolName, StringComparison.Ordinal) ||
                loaded.Artifact.TargetStartLine != assignment.Line ||
                loaded.Artifact.TargetEndLine != assignment.TargetEndLine)
                throw new InvalidDataException($"visible test is bound to a different target declaration: {path}");
            result[path] = loaded;
        }
        return result;
    }

}
