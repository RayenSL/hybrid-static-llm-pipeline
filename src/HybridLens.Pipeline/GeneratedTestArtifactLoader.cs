using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using HybridLens.Core.Models;

namespace HybridLens.Pipeline;

public sealed record LoadedGeneratedTest(
    GeneratedTestArtifact Artifact,
    GeneratedTestSource Source);

/// <summary>Loads an admitted visible test and verifies its immutable content hash before repair.</summary>
public static class GeneratedTestArtifactLoader
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower) }
    };

    public static async Task<LoadedGeneratedTest> LoadAdmittedAsync(
        string artifactPath,
        CancellationToken cancellationToken = default)
    {
        var json = await File.ReadAllTextAsync(artifactPath, cancellationToken);
        var artifact = JsonSerializer.Deserialize<GeneratedTestArtifact>(json, JsonOptions)
            ?? throw new InvalidDataException("generated-test artefact is empty or invalid");
        if (!artifact.Admitted)
            throw new InvalidDataException($"generated-test artefact is not admitted ({artifact.AdmissionStatus})");
        if (string.IsNullOrWhiteSpace(artifact.TestName) || string.IsNullOrWhiteSpace(artifact.TestBody))
            throw new InvalidDataException("admitted generated-test artefact has no test source");
        if (string.IsNullOrWhiteSpace(artifact.TargetSymbolName) || artifact.TargetStartLine < 1 ||
            artifact.TargetEndLine < artifact.TargetStartLine)
            throw new InvalidDataException("admitted generated-test artefact has no valid blinded target descriptor");

        var source = new GeneratedTestSource(artifact.TestName, artifact.UsingDirectives, artifact.TestBody);
        var actualHash = Sha256(string.Join("\n", source.UsingDirectives) + "\n" + source.TestBody);
        if (!string.Equals(actualHash, artifact.TestSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("generated-test artefact hash does not match its frozen source");
        return new LoadedGeneratedTest(artifact, source);
    }

    public static void VerifyUnchanged(LoadedGeneratedTest loaded)
    {
        var actualHash = Sha256(string.Join("\n", loaded.Source.UsingDirectives) + "\n" + loaded.Source.TestBody);
        if (!string.Equals(actualHash, loaded.Artifact.TestSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("visible generated test changed during repair");
    }

    private static string Sha256(string value) =>
        Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(value)));
}
