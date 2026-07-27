using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using HybridLens.Core.Models;

namespace HybridLens.Pipeline;

/// <summary>Writes and verifies the common, architecture-neutral final-production-source contract.</summary>
public static class MaterializedSourceArtifactWriter
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower) },
        WriteIndented = true
    };

    public static async Task<string> WriteAsync(
        string directory,
        MaterializedSourceArtifact artifact,
        CancellationToken cancellationToken = default)
    {
        var actualHash = Sha256(artifact.FinalSource);
        if (!string.Equals(actualHash, artifact.SourceSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("materialized-source hash does not match final source");

        Directory.CreateDirectory(directory);
        var path = Path.GetFullPath(Path.Combine(
            directory,
            $"{SafeName(artifact.RelativeFile)}--run{artifact.RunNumber}--{artifact.ArtifactId}.json"));
        await File.WriteAllTextAsync(
            path,
            JsonSerializer.Serialize(artifact, JsonOptions),
            new UTF8Encoding(false),
            cancellationToken);
        return path;
    }

    public static string Sha256(string value) =>
        Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(value)));

    private static string SafeName(string relative)
    {
        var invalid = Path.GetInvalidFileNameChars().ToHashSet();
        return new string(relative.Select(c => invalid.Contains(c) || c is '/' or '\\' ? '_' : c).ToArray());
    }
}
