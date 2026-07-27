using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using HybridLens.ContextBuilder;
using HybridLens.Core.Abstractions;
using HybridLens.Core.Models;

namespace HybridLens.Pipeline;

public sealed record GeneratedTestGenerationResult(
    GeneratedTestArtifact Artifact,
    string ArtifactPath);

/// <summary>
/// Executes one separate, stateless pre-repair test-authoring call, admits the returned test against
/// the pristine production project, and freezes the complete artefact as JSON.
/// </summary>
public sealed class CharacterizationTestGenerator(
    ILlmAdapter adapter,
    string modelName,
    Func<GeneratedTestSource, string, int, int, CancellationToken, Task<GeneratedTestAdmissionResult>>? admit = null)
{
    private readonly Func<GeneratedTestSource, string, int, int, CancellationToken, Task<GeneratedTestAdmissionResult>> _admit
        = admit ?? GeneratedTestAdmissionRunner.RunAsync;

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        DefaultIgnoreCondition = JsonIgnoreCondition.Never,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower) },
        WriteIndented = true
    };

    public async Task<GeneratedTestGenerationResult> GenerateAsync(
        string sourceFile,
        string solutionPath,
        string outputDirectory,
        BlindedTargetDescriptor target,
        int baselineRuns,
        int timeoutSeconds,
        CancellationToken cancellationToken)
    {
        var sourceFull = Path.GetFullPath(sourceFile);
        var solutionFull = Path.GetFullPath(solutionPath);
        var solutionRoot = Path.GetDirectoryName(solutionFull)!;
        if (!File.Exists(sourceFull)) throw new FileNotFoundException("source file not found", sourceFull);
        if (!File.Exists(solutionFull)) throw new FileNotFoundException("solution file not found", solutionFull);
        var relative = Path.GetRelativePath(solutionRoot, sourceFull);
        if (relative.StartsWith("..", StringComparison.Ordinal) || Path.IsPathRooted(relative))
            throw new ArgumentException("source file must be under the solution root", nameof(sourceFile));

        var projectFile = FindContainingProject(sourceFull, solutionRoot)
            ?? throw new InvalidOperationException($"no containing .csproj found for {sourceFull}");
        var pristineSource = await File.ReadAllTextAsync(sourceFull, cancellationToken);
        ValidateTarget(target, pristineSource);
        var sourceHash = Sha256(pristineSource);
        var artifactId = Guid.NewGuid().ToString("N");
        Directory.CreateDirectory(outputDirectory);
        var artifactPath = Path.Combine(outputDirectory, $"{SafeName(relative)}--{artifactId}.json");
        var systemPrompt = CharacterizationTestPrompt.SystemPrompt;
        var userPrompt = CharacterizationTestPrompt.BuildUserPrompt(
            relative.Replace('\\', '/'),
            Path.GetFileNameWithoutExtension(projectFile),
            pristineSource,
            target);

        var sw = Stopwatch.StartNew();
        LlmResponse? response = null;
        GeneratedTestSource? parsed = null;
        GeneratedTestAdmissionResult? admission = null;
        string? failure = null;
        var status = GeneratedTestAdmissionStatus.GenerationFailed;
        try
        {
            response = await adapter.CompleteAsync(new LlmRequest
            {
                SystemPrompt = systemPrompt,
                UserPrompt = userPrompt,
                PromptVersion = CharacterizationTestPrompt.Version
            }, cancellationToken);

            parsed = Parse(response.Content, out failure);
            if (parsed is null)
            {
                status = GeneratedTestAdmissionStatus.ParseFailed;
            }
            else
            {
                admission = await _admit(parsed, projectFile, baselineRuns, timeoutSeconds, cancellationToken);
                status = admission.Status;
                failure = admission.Reason;
            }
        }
        catch (OperationCanceledException) { throw; }
        catch (Exception ex)
        {
            status = GeneratedTestAdmissionStatus.GenerationFailed;
            failure = ex.Message;
        }
        sw.Stop();

        var testHash = parsed is null
            ? null
            : Sha256(string.Join("\n", parsed.UsingDirectives) + "\n" + parsed.TestBody);
        var artifact = new GeneratedTestArtifact
        {
            ArtifactId = artifactId,
            ArtifactRef = Path.GetFullPath(artifactPath),
            Timestamp = DateTimeOffset.UtcNow,
            SourceFile = sourceFull,
            SourceSha256 = sourceHash,
            TargetSymbolName = target.SymbolName,
            TargetStartLine = target.StartLine,
            TargetEndLine = target.EndLine,
            ProjectFile = projectFile,
            ModelName = modelName,
            PromptVersion = CharacterizationTestPrompt.Version,
            RawSystemPrompt = systemPrompt,
            RawUserPrompt = userPrompt,
            RawLlmOutput = response?.Content,
            InputTokens = response?.InputTokens ?? 0,
            OutputTokens = response?.OutputTokens ?? 0,
            DurationMs = sw.Elapsed.TotalMilliseconds,
            TestName = parsed?.TestName,
            UsingDirectives = parsed?.UsingDirectives ?? [],
            TestBody = parsed?.TestBody,
            TestSha256 = testHash,
            AdmissionStatus = status,
            AdmissionReason = failure,
            ParsePassed = parsed is not null,
            AssertionGatePassed = admission?.AssertionGatePassed ?? false,
            BuildPassed = admission?.BuildPassed,
            BaselineRunsPassed = admission?.BaselineRunsPassed ?? [],
            AdmissionOutputTail = admission?.OutputTail
        };

        var json = JsonSerializer.Serialize(artifact, JsonOptions);
        await File.WriteAllTextAsync(artifactPath, json, new UTF8Encoding(false), cancellationToken);
        return new GeneratedTestGenerationResult(artifact, Path.GetFullPath(artifactPath));
    }

    public static GeneratedTestSource? Parse(string raw, out string? reason)
    {
        var json = raw.Trim();
        if (json.StartsWith("```", StringComparison.Ordinal))
        {
            json = string.Join('\n', json.Split('\n').Skip(1));
            var fence = json.LastIndexOf("```", StringComparison.Ordinal);
            if (fence >= 0) json = json[..fence].Trim();
        }
        try
        {
            using var document = JsonDocument.Parse(json);
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object)
            {
                reason = "generated-test output is not a JSON object";
                return null;
            }
            var name = root.TryGetProperty("test_name", out var n) ? n.GetString() : null;
            var body = root.TryGetProperty("test_body", out var b) ? b.GetString() : null;
            var usings = new List<string>();
            if (root.TryGetProperty("using_directives", out var u) && u.ValueKind == JsonValueKind.Array)
                foreach (var item in u.EnumerateArray())
                    if (item.ValueKind == JsonValueKind.String && item.GetString() is { } value)
                        usings.Add(value.Trim());

            if (string.IsNullOrWhiteSpace(name) || string.IsNullOrWhiteSpace(body))
            {
                reason = "generated-test output is missing test_name or test_body";
                return null;
            }
            if (usings.Any(x => !x.StartsWith("using ", StringComparison.Ordinal) || !x.EndsWith(';')))
            {
                reason = "using_directives contains an invalid directive";
                return null;
            }
            reason = null;
            return new GeneratedTestSource(name.Trim(), usings, body);
        }
        catch (JsonException ex)
        {
            reason = $"generated-test JSON parse failed: {ex.Message}";
            return null;
        }
    }

    private static void ValidateTarget(BlindedTargetDescriptor target, string pristineSource)
    {
        if (string.IsNullOrWhiteSpace(target.SymbolName) || target.StartLine < 1 || target.EndLine < target.StartLine)
            throw new ArgumentException("invalid blinded target descriptor", nameof(target));
        var lineCount = pristineSource.Replace("\r\n", "\n").Split('\n').Length;
        if (target.EndLine > lineCount)
            throw new ArgumentException("target line range is outside the pristine source file", nameof(target));
    }

    private static string? FindContainingProject(string sourceFile, string solutionRoot)
    {
        var current = Directory.GetParent(sourceFile);
        var root = Path.GetFullPath(solutionRoot).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        while (current is not null)
        {
            var candidate = Directory.EnumerateFiles(current.FullName, "*.csproj", SearchOption.TopDirectoryOnly)
                .OrderBy(x => x, StringComparer.OrdinalIgnoreCase)
                .FirstOrDefault();
            if (candidate is not null) return candidate;
            var path = current.FullName.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            if (string.Equals(path, root, StringComparison.OrdinalIgnoreCase)) break;
            current = current.Parent;
        }
        return null;
    }

    private static string SafeName(string relativePath)
    {
        var invalid = Path.GetInvalidFileNameChars().ToHashSet();
        return new string(relativePath.Select(c => invalid.Contains(c) || c is '/' or '\\' ? '_' : c).ToArray());
    }

    private static string Sha256(string value) =>
        Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(value)));
}
