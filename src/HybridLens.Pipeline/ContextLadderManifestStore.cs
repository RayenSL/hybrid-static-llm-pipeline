using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using HybridLens.Core.Models;

namespace HybridLens.Pipeline;

/// <summary>Validates frozen ladder definitions, assignments and source hashes before execution.</summary>
public static class ContextLadderManifestStore
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        WriteIndented = true,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower) }
    };

    public static ContextLadderManifest LoadAndValidate(string path)
    {
        if (!File.Exists(path)) throw new FileNotFoundException("manifest not found", path);
        var manifest = JsonSerializer.Deserialize<ContextLadderManifest>(File.ReadAllText(path), JsonOptions)
            ?? throw new InvalidDataException("manifest is empty or invalid");

        if (manifest.SchemaVersion != "2.0.0")
            throw new InvalidDataException("unsupported context ladder manifest schema");

        var ladder = ContextLadder.ForVersion(manifest.LadderVersion);
        var actual = ContextLadder.Sha256(ladder);
        if (!string.Equals(actual, manifest.LadderSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException(
                $"context ladder definition drift: manifest {manifest.LadderSha256}, runtime {actual}. "
                + "The frozen manifest was produced by a different definition of the levels.");

        if (!File.Exists(manifest.TargetSolution) ||
            !Path.GetExtension(manifest.TargetSolution).Equals(".sln", StringComparison.OrdinalIgnoreCase))
            throw new FileNotFoundException("target solution not found", manifest.TargetSolution);
        if (!File.Exists(manifest.BaselineSource) || Sha256File(manifest.BaselineSource) != manifest.BaselineSha256)
            throw new InvalidDataException("frozen analyzer baseline is missing or changed");

        var count = manifest.Assignments.Count;
        if (count == 0) throw new InvalidDataException("manifest contains no assignments");
        if (manifest.Assignments.Select(a => a.AssignmentId).Distinct(StringComparer.Ordinal).Count() != count)
            throw new InvalidDataException("assignment IDs are not unique");
        if (!manifest.Assignments.Select(a => a.Order).Order().SequenceEqual(Enumerable.Range(1, count)))
            throw new InvalidDataException($"assignment order must be exactly 1..{count}");

        var allowed = new HashSet<ContextLevel>
        {
            ContextLevel.Minimal, ContextLevel.Structural, ContextLevel.Relational, ContextLevel.Full
        };
        foreach (var block in manifest.Assignments.GroupBy(a => a.BlockId, StringComparer.Ordinal))
        {
            if (block.Count() != 4 || !block.Select(a => a.ContextLevel).ToHashSet().SetEquals(allowed))
                throw new InvalidDataException(
                    $"block {block.Key} must contain each of the four context levels exactly once");
            if (block.Select(a => a.AntiPatternType).Distinct().Count() != 1)
                throw new InvalidDataException($"block {block.Key} mixes anti-pattern types");
        }

        if (manifest.Assignments.Count(a => a.ContextLevel == ContextLevel.Full) * 4 != count)
            throw new InvalidDataException("levels are not balanced across the campaign");

        foreach (var assignment in manifest.Assignments)
        {
            if (!File.Exists(assignment.FilePath) ||
                Sha256File(assignment.FilePath) != assignment.PristineSourceSha256)
                throw new InvalidDataException($"pristine source missing or changed: {assignment.AssignmentId}");
            if (assignment.TargetEndLine < assignment.Line)
                throw new InvalidDataException($"target end line precedes start: {assignment.AssignmentId}");

            // Cross-file payload is only meaningful where the level's specification asks for it.
            var spec = ContextLadder.For(ladder, assignment.ContextLevel);
            if (spec.CrossFile == CrossFileScope.None && assignment.CrossFileDeclarations.Count > 0)
                throw new InvalidDataException(
                    $"{assignment.AssignmentId} carries cross-file declarations at a level that does not use them");
            foreach (var declaration in assignment.CrossFileDeclarations)
            {
                if (Sha256Text(declaration.Source) != declaration.Sha256)
                    throw new InvalidDataException(
                        $"frozen cross-file source hash mismatch in {assignment.AssignmentId}: {declaration.RelativePath}");
            }
            if (assignment.CrossFileDeclarations.Count > spec.MaxCrossFileFiles && spec.MaxCrossFileFiles > 0)
                throw new InvalidDataException($"{assignment.AssignmentId} exceeds the frozen cross-file file cap");
        }

        return manifest;
    }

    private static string Sha256File(string path)
        => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();

    private static string Sha256Text(string value)
        => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();

}
