using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using HybridLens.ContextBuilder;
using HybridLens.Core.Models;

namespace HybridLens.Pipeline;

public sealed record FactorialCampaignSeed(KnownInstance Known, Finding Finding);

/// <summary>Creates and validates a deterministic, blocked 2 x 2 x 2 campaign schedule.</summary>
public static class FactorialCampaignPlanner
{
    public const string Version = "1.1.0";
    private static readonly (bool Grounded, string Control, bool Tests)[] Conditions =
    [
        (false, "single_shot", false),
        (false, "single_shot", true),
        (true,  "single_shot", false),
        (true,  "single_shot", true),
        (false, "iterative", false),
        (false, "iterative", true),
        (true,  "iterative", false),
        (true,  "iterative", true)
    ];

    public static FactorialCampaignManifest Create(
        IReadOnlyList<FactorialCampaignSeed> seeds,
        IReadOnlyDictionary<string, LoadedGeneratedTest> visibleTestsByFile,
        string targetSolution,
        string baselineSource,
        string modelName,
        string codeRevision,
        int repetitions,
        int iterationBudget,
        int buildTimeoutSeconds,
        int maxInputTokenGuard,
        int randomizationSeed)
    {
        if (seeds.Count == 0) throw new ArgumentException("at least one campaign seed is required", nameof(seeds));
        if (repetitions < 1) throw new ArgumentOutOfRangeException(nameof(repetitions));
        if (iterationBudget < 1) throw new ArgumentOutOfRangeException(nameof(iterationBudget));
        if (buildTimeoutSeconds < 1) throw new ArgumentOutOfRangeException(nameof(buildTimeoutSeconds));
        if (maxInputTokenGuard < 1) throw new ArgumentOutOfRangeException(nameof(maxInputTokenGuard));
        if (string.IsNullOrWhiteSpace(modelName)) throw new ArgumentException("model name is required", nameof(modelName));
        if (string.IsNullOrWhiteSpace(codeRevision)) throw new ArgumentException("a frozen code revision is required", nameof(codeRevision));

        var solutionFull = Path.GetFullPath(targetSolution);
        var baselineFull = Path.GetFullPath(baselineSource);
        if (!File.Exists(solutionFull)) throw new FileNotFoundException("target solution not found", solutionFull);
        if (!File.Exists(baselineFull)) throw new FileNotFoundException("baseline JSONL not found", baselineFull);

        var orderedSeeds = seeds.OrderBy(s => s.Known.InstanceKey, StringComparer.Ordinal).ToList();
        var duplicate = orderedSeeds.GroupBy(s => s.Known.InstanceKey, StringComparer.Ordinal).FirstOrDefault(g => g.Count() > 1);
        if (duplicate is not null) throw new InvalidDataException($"duplicate campaign seed: {duplicate.Key}");
        var sharedFile = orderedSeeds
            .GroupBy(s => Path.GetFullPath(s.Known.FilePath), StringComparer.OrdinalIgnoreCase)
            .FirstOrDefault(group => group.Count() > 1);
        if (sharedFile is not null)
            throw new InvalidDataException(
                $"the current per-instance treatment contract requires one included instance per source file: {sharedFile.Key}");
        if (orderedSeeds.Any(s => s.Known.Type is not (AntiPatternType.LongMethod or AntiPatternType.GodClass)))
            throw new InvalidDataException("factorial campaigns may contain only Long Method and God Class instances");

        var baselineHash = Sha256File(baselineFull);
        var identity = string.Join("|",
            Version, codeRevision.Trim(), modelName.Trim(), randomizationSeed, repetitions, iterationBudget,
            buildTimeoutSeconds, maxInputTokenGuard, baselineHash,
            string.Join(";", orderedSeeds.Select(s => s.Known.InstanceKey)));
        var campaignId = Sha256(identity)[..24];
        var random = new Random(randomizationSeed);
        var blocks = orderedSeeds
            .SelectMany(seed => Enumerable.Range(1, repetitions).Select(run => (Seed: seed, Run: run)))
            .ToList();
        Shuffle(blocks, random);

        var assignments = new List<FactorialCampaignAssignment>(blocks.Count * Conditions.Length);
        foreach (var block in blocks)
        {
            var sourceFile = Path.GetFullPath(block.Seed.Known.FilePath);
            if (!File.Exists(sourceFile)) throw new FileNotFoundException("campaign source file not found", sourceFile);
            var sourceHash = SourceSha256(sourceFile);
            visibleTestsByFile.TryGetValue(sourceFile, out var visibleTest);
            if (visibleTest is not null)
            {
                GeneratedTestArtifactLoader.VerifyUnchanged(visibleTest);
                if (!Path.GetFullPath(visibleTest.Artifact.SourceFile).Equals(sourceFile, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("visible test was mapped to a different source file");
                if (!string.Equals(sourceHash, visibleTest.Artifact.SourceSha256, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("visible test was generated from a different pristine source revision");
                if (!string.Equals(visibleTest.Artifact.TargetSymbolName, block.Seed.Known.SymbolName, StringComparison.Ordinal) ||
                    visibleTest.Artifact.TargetStartLine != block.Seed.Known.Line ||
                    visibleTest.Artifact.TargetEndLine != block.Seed.Known.EndLine)
                    throw new InvalidDataException("visible test was generated for a different target declaration");
            }

            var blockId = Sha256($"{campaignId}|{block.Seed.Known.InstanceKey}|{block.Run}")[..24];
            var conditions = Conditions.ToList();
            Shuffle(conditions, random);
            foreach (var condition in conditions)
            {
                var availableVisible = condition.Tests ? visibleTest : null;
                var promptVersion = condition.Control == "single_shot"
                    ? FactorialSingleShotPrompt.Version
                    : PromptTemplate.AgenticPromptVersion(availableVisible is not null);
                var signature = $"{condition.Grounded}|{condition.Control}|{condition.Tests}";
                assignments.Add(new FactorialCampaignAssignment
                {
                    Order = assignments.Count + 1,
                    AssignmentId = Sha256($"{blockId}|{signature}")[..24],
                    BlockId = blockId,
                    RunNumber = block.Run,
                    AntiPatternType = block.Seed.Known.Type,
                    FilePath = sourceFile,
                    SymbolName = block.Seed.Known.SymbolName,
                    Line = block.Seed.Known.Line,
                    TargetEndLine = block.Seed.Known.EndLine,
                    Severity = block.Seed.Known.Severity,
                    Snippet = block.Seed.Known.Snippet,
                    Metrics = new Dictionary<string, double>(block.Seed.Finding.Metrics, StringComparer.Ordinal),
                    PristineSourceSha256 = sourceHash,
                    GroundingEnabled = condition.Grounded,
                    ControlStructure = condition.Control,
                    VisibleTestsEnabled = condition.Tests,
                    VisibleTestArtifactRef = availableVisible is null
                        ? null
                        : Path.GetFullPath(availableVisible.Artifact.ArtifactRef),
                    VisibleTestSha256 = availableVisible?.Artifact.TestSha256,
                    PromptVersion = promptVersion
                });
            }
        }

        var manifest = new FactorialCampaignManifest
        {
            Version = Version,
            CampaignId = campaignId,
            CreatedAt = DateTimeOffset.UtcNow,
            CodeRevision = codeRevision.Trim(),
            RandomizationSeed = randomizationSeed,
            ModelName = modelName.Trim(),
            Repetitions = repetitions,
            IterationBudget = iterationBudget,
            BuildTimeoutSeconds = buildTimeoutSeconds,
            MaxInputTokenGuard = maxInputTokenGuard,
            TargetSolution = solutionFull,
            BaselineSource = baselineFull,
            BaselineSha256 = baselineHash,
            Assignments = assignments
        };
        Validate(manifest, verifyFiles: true);
        return manifest;
    }

    public static void Validate(FactorialCampaignManifest manifest, bool verifyFiles)
    {
        if (manifest.Version != Version) throw new InvalidDataException($"unsupported campaign manifest version: {manifest.Version}");
        if (manifest.Assignments.Count == 0) throw new InvalidDataException("campaign manifest has no assignments");
        if (manifest.Repetitions < 1 || manifest.IterationBudget < 1 || manifest.BuildTimeoutSeconds < 1 || manifest.MaxInputTokenGuard < 1)
            throw new InvalidDataException("campaign manifest contains an invalid positive limit");
        if (string.IsNullOrWhiteSpace(manifest.CodeRevision) || string.IsNullOrWhiteSpace(manifest.ModelName))
            throw new InvalidDataException("campaign manifest has no frozen model or code revision");

        var ordered = manifest.Assignments.OrderBy(a => a.Order).ToList();
        if (!ordered.Select(a => a.Order).SequenceEqual(Enumerable.Range(1, ordered.Count)))
            throw new InvalidDataException("campaign assignment order must be contiguous and unique");
        if (ordered.Select(a => a.AssignmentId).Distinct(StringComparer.Ordinal).Count() != ordered.Count)
            throw new InvalidDataException("campaign assignment IDs are not unique");

        foreach (var block in ordered.GroupBy(a => a.BlockId, StringComparer.Ordinal))
        {
            if (block.Count() != Conditions.Length) throw new InvalidDataException($"campaign block {block.Key} does not have eight conditions");
            var signatures = block.Select(a => $"{a.GroundingEnabled}|{a.ControlStructure}|{a.VisibleTestsEnabled}")
                .ToHashSet(StringComparer.Ordinal);
            var expected = Conditions.Select(c => $"{c.Grounded}|{c.Control}|{c.Tests}").ToHashSet(StringComparer.Ordinal);
            if (!signatures.SetEquals(expected)) throw new InvalidDataException($"campaign block {block.Key} does not contain the full factorial");
            if (block.Select(a => (a.FilePath, a.SymbolName, a.Line, a.TargetEndLine, a.RunNumber)).Distinct().Count() != 1)
                throw new InvalidDataException($"campaign block {block.Key} mixes instances or repetitions");
        }

        foreach (var assignment in ordered)
        {
            if (assignment.AntiPatternType is not (AntiPatternType.LongMethod or AntiPatternType.GodClass))
                throw new InvalidDataException("campaign assignment is outside the Long Method/God Class scope");
            if (assignment.ControlStructure is not ("single_shot" or "iterative"))
                throw new InvalidDataException($"unknown control structure: {assignment.ControlStructure}");
            if (string.IsNullOrWhiteSpace(assignment.SymbolName) || assignment.Line < 1 ||
                assignment.TargetEndLine < assignment.Line)
                throw new InvalidDataException("campaign assignment has an invalid blinded target descriptor");
            if (!assignment.VisibleTestsEnabled &&
                (!string.IsNullOrWhiteSpace(assignment.VisibleTestArtifactRef) || !string.IsNullOrWhiteSpace(assignment.VisibleTestSha256)))
                throw new InvalidDataException("test-disabled assignment contains a visible-test artefact");
            if (!string.IsNullOrWhiteSpace(assignment.VisibleTestArtifactRef) && string.IsNullOrWhiteSpace(assignment.VisibleTestSha256))
                throw new InvalidDataException("visible-test assignment has no frozen test hash");
            var expectedPrompt = assignment.ControlStructure == "single_shot"
                ? FactorialSingleShotPrompt.Version
                : PromptTemplate.AgenticPromptVersion(!string.IsNullOrWhiteSpace(assignment.VisibleTestArtifactRef));
            if (assignment.PromptVersion != expectedPrompt)
                throw new InvalidDataException($"assignment {assignment.AssignmentId} has an unexpected prompt version");
        }

        if (!verifyFiles) return;
        if (!File.Exists(manifest.TargetSolution)) throw new FileNotFoundException("manifest target solution not found", manifest.TargetSolution);
        if (!File.Exists(manifest.BaselineSource)) throw new FileNotFoundException("manifest baseline not found", manifest.BaselineSource);
        if (!string.Equals(Sha256File(manifest.BaselineSource), manifest.BaselineSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("baseline JSONL changed after the campaign manifest was frozen");
        foreach (var source in ordered.GroupBy(a => Path.GetFullPath(a.FilePath), StringComparer.OrdinalIgnoreCase))
        {
            if (!File.Exists(source.Key)) throw new FileNotFoundException("manifest source file not found", source.Key);
            var expectedHashes = source.Select(a => a.PristineSourceSha256).Distinct(StringComparer.OrdinalIgnoreCase).ToList();
            if (expectedHashes.Count != 1 || !string.Equals(SourceSha256(source.Key), expectedHashes[0], StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException($"pristine source changed after manifest freeze: {source.Key}");
        }
    }

    public static string SourceSha256(string path) =>
        MaterializedSourceArtifactWriter.Sha256(File.ReadAllText(path));

    public static string Sha256File(string path) =>
        Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(path)));

    private static string Sha256(string value) =>
        Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(value)));

    private static void Shuffle<T>(IList<T> values, Random random)
    {
        for (var i = values.Count - 1; i > 0; i--)
        {
            var j = random.Next(i + 1);
            (values[i], values[j]) = (values[j], values[i]);
        }
    }
}

/// <summary>Snake-case JSON persistence for frozen campaign manifests.</summary>
public static class FactorialCampaignManifestStore
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower) },
        WriteIndented = true
    };

    public static async Task SaveAsync(
        string path,
        FactorialCampaignManifest manifest,
        CancellationToken cancellationToken = default)
    {
        FactorialCampaignPlanner.Validate(manifest, verifyFiles: true);
        var full = Path.GetFullPath(path);
        Directory.CreateDirectory(Path.GetDirectoryName(full)!);
        await File.WriteAllTextAsync(
            full,
            JsonSerializer.Serialize(manifest, JsonOptions),
            new UTF8Encoding(false),
            cancellationToken);
    }

    public static async Task<FactorialCampaignManifest> LoadAsync(
        string path,
        bool verifyFiles = true,
        CancellationToken cancellationToken = default)
    {
        var json = await File.ReadAllTextAsync(path, cancellationToken);
        var manifest = JsonSerializer.Deserialize<FactorialCampaignManifest>(json, JsonOptions)
            ?? throw new InvalidDataException("campaign manifest is empty or invalid");
        FactorialCampaignPlanner.Validate(manifest, verifyFiles);
        return manifest;
    }
}
