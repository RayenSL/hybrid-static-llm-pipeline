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
/// Plans and implements one diagnosis-blind five-case suite before repair, admits it against the
/// pristine project, and permits at most one correction based solely on compiler diagnostics.
/// </summary>
public sealed class CharacterizationTestGenerator(
    ILlmAdapter adapter,
    string modelName,
    Func<GeneratedTestSource, string, int, int, CancellationToken, Task<GeneratedTestAdmissionResult>>? admit = null)
{
    private readonly Func<GeneratedTestSource, string, int, int, CancellationToken, Task<GeneratedTestAdmissionResult>> _admit
        = admit ?? GeneratedTestAdmissionRunner.RunAsync;

    private static readonly (string Id, GeneratedTestCaseCategory Category)[] RequiredCases =
    [
        ("H1", GeneratedTestCaseCategory.HappyPath),
        ("E1", GeneratedTestCaseCategory.EmptyOrInvalid),
        ("B1", GeneratedTestCaseCategory.BoundaryValues),
        ("A1", GeneratedTestCaseCategory.AlternativePath),
        ("D1", GeneratedTestCaseCategory.DependencyOrState)
    ];

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
        var dependencyContext = await NeutralDependencyContextBuilder.BuildAsync(
            sourceFull, projectFile, pristineSource, cancellationToken);
        var projectName = Path.GetFileNameWithoutExtension(projectFile);
        var relativeUnix = relative.Replace('\\', '/');
        var planUserPrompt = CharacterizationTestPrompt.BuildPlanUserPrompt(
            relativeUnix, projectName, pristineSource, dependencyContext, target);

        var sourceHash = Sha256(pristineSource);
        var artifactId = Guid.NewGuid().ToString("N");
        Directory.CreateDirectory(outputDirectory);
        var artifactPath = Path.Combine(outputDirectory, $"{SafeName(relative)}--{artifactId}.json");

        var stopwatch = Stopwatch.StartNew();
        LlmResponse? planResponse = null;
        LlmResponse? implementationResponse = null;
        LlmResponse? correctionResponse = null;
        GeneratedTestPlan? plan = null;
        GeneratedTestSource? parsed = null;
        GeneratedTestAdmissionResult? admission = null;
        string? implementationUserPrompt = null;
        string? correctionPrompt = null;
        string? failure = null;
        var status = GeneratedTestAdmissionStatus.GenerationFailed;

        try
        {
            planResponse = await adapter.CompleteAsync(new LlmRequest
            {
                SystemPrompt = CharacterizationTestPrompt.PlanSystemPrompt,
                UserPrompt = planUserPrompt,
                PromptVersion = CharacterizationTestPrompt.PlanVersion
            }, cancellationToken);
            plan = ParsePlan(planResponse.Content, out failure);
            if (plan is null)
            {
                status = GeneratedTestAdmissionStatus.ParseFailed;
            }
            else
            {
                implementationUserPrompt = CharacterizationTestPrompt.BuildImplementationUserPrompt(
                    relativeUnix, projectName, pristineSource, dependencyContext, target, plan);
                implementationResponse = await adapter.CompleteAsync(new LlmRequest
                {
                    SystemPrompt = CharacterizationTestPrompt.SystemPrompt,
                    UserPrompt = implementationUserPrompt,
                    PromptVersion = CharacterizationTestPrompt.ImplementationVersion
                }, cancellationToken);
                parsed = Parse(implementationResponse.Content, out failure);
                if (parsed is null || !MatchesPlan(parsed, plan, out failure))
                {
                    parsed = null;
                    status = GeneratedTestAdmissionStatus.ParseFailed;
                }
                else
                {
                    admission = await _admit(parsed, projectFile, baselineRuns, timeoutSeconds, cancellationToken);
                    status = admission.Status;
                    failure = admission.Reason;

                    if (admission.Status == GeneratedTestAdmissionStatus.BuildFailed)
                    {
                        correctionPrompt = CharacterizationTestPrompt.BuildCompileCorrectionUserPrompt(
                            plan, implementationResponse.Content, admission.OutputTail);
                        correctionResponse = await adapter.CompleteAsync(new LlmRequest
                        {
                            SystemPrompt = CharacterizationTestPrompt.CompileCorrectionSystemPrompt,
                            UserPrompt = correctionPrompt,
                            PromptVersion = CharacterizationTestPrompt.CompileCorrectionVersion
                        }, cancellationToken);
                        var corrected = Parse(correctionResponse.Content, out failure);
                        if (corrected is null || !MatchesPlan(corrected, plan, out failure) ||
                            !PreservesCases(parsed, corrected, out failure))
                        {
                            status = GeneratedTestAdmissionStatus.ParseFailed;
                        }
                        else
                        {
                            parsed = corrected;
                            admission = await _admit(parsed, projectFile, baselineRuns, timeoutSeconds, cancellationToken);
                            status = admission.Status;
                            failure = admission.Reason;
                        }
                    }
                }
            }
        }
        catch (OperationCanceledException) { throw; }
        catch (Exception ex)
        {
            status = GeneratedTestAdmissionStatus.GenerationFailed;
            failure = ex.Message;
        }
        stopwatch.Stop();

        var testHash = parsed is null ? null : GeneratedTestSourceCanonicalizer.Hash(parsed);
        var responses = new[] { planResponse, implementationResponse, correctionResponse }.Where(r => r is not null).ToList();
        var artifact = new GeneratedTestArtifact
        {
            ArtifactId = artifactId,
            ArtifactRef = Path.GetFullPath(artifactPath),
            Timestamp = DateTimeOffset.UtcNow,
            SourceFile = sourceFull,
            SourceSha256 = sourceHash,
            DependencyContextSha256 = Sha256(dependencyContext),
            TargetSymbolName = target.SymbolName,
            TargetStartLine = target.StartLine,
            TargetEndLine = target.EndLine,
            ProjectFile = projectFile,
            ModelName = modelName,
            PromptVersion = CharacterizationTestPrompt.Version,
            RawSystemPrompt = CharacterizationTestPrompt.SystemPrompt,
            RawUserPrompt = implementationUserPrompt ?? planUserPrompt,
            RawLlmOutput = implementationResponse?.Content,
            RawPlanSystemPrompt = CharacterizationTestPrompt.PlanSystemPrompt,
            RawPlanUserPrompt = planUserPrompt,
            RawPlanLlmOutput = planResponse?.Content,
            RawCorrectionPrompt = correctionPrompt,
            RawCorrectionLlmOutput = correctionResponse?.Content,
            InputTokens = responses.Sum(r => r!.InputTokens),
            OutputTokens = responses.Sum(r => r!.OutputTokens),
            GenerationCallCount = responses.Count,
            PlanInputTokens = planResponse?.InputTokens ?? 0,
            PlanOutputTokens = planResponse?.OutputTokens ?? 0,
            ImplementationInputTokens = implementationResponse?.InputTokens ?? 0,
            ImplementationOutputTokens = implementationResponse?.OutputTokens ?? 0,
            CorrectionInputTokens = correctionResponse?.InputTokens ?? 0,
            CorrectionOutputTokens = correctionResponse?.OutputTokens ?? 0,
            DurationMs = stopwatch.Elapsed.TotalMilliseconds,
            TestName = parsed?.TestName,
            UsingDirectives = parsed?.UsingDirectives ?? [],
            TestBody = parsed?.TestBody,
            HelperCode = parsed?.HelperCode ?? string.Empty,
            TestCases = parsed?.Cases ?? [],
            TestPlan = plan,
            TestSha256 = testHash,
            AdmissionStatus = status,
            AdmissionReason = failure,
            ParsePassed = parsed is not null,
            AssertionGatePassed = admission?.AssertionGatePassed ?? false,
            BuildPassed = admission?.BuildPassed,
            BaselineRunsPassed = admission?.BaselineRunsPassed ?? [],
            AdmissionOutputTail = admission?.OutputTail
        };

        await File.WriteAllTextAsync(
            artifactPath,
            JsonSerializer.Serialize(artifact, JsonOptions),
            new UTF8Encoding(false),
            cancellationToken);
        return new GeneratedTestGenerationResult(artifact, Path.GetFullPath(artifactPath));
    }

    public static GeneratedTestPlan? ParsePlan(string raw, out string? reason)
    {
        try
        {
            using var document = JsonDocument.Parse(Unfence(raw));
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object)
            {
                reason = "test plan is not a JSON object";
                return null;
            }
            var name = StringProperty(root, "suite_name");
            if (string.IsNullOrWhiteSpace(name) || !root.TryGetProperty("cases", out var casesElement) ||
                casesElement.ValueKind != JsonValueKind.Array)
            {
                reason = "test plan is missing suite_name or cases";
                return null;
            }

            var cases = new List<GeneratedTestPlanCase>();
            foreach (var element in casesElement.EnumerateArray())
            {
                if (!TryReadIdentity(element, out var id, out var category, out reason)) return null;
                var inputs = StringArray(element, "inputs");
                var item = new GeneratedTestPlanCase(
                    id!, category,
                    StringProperty(element, "source_evidence") ?? string.Empty,
                    StringProperty(element, "input_partition") ?? string.Empty,
                    inputs,
                    StringProperty(element, "expected_observation") ?? string.Empty);
                if (string.IsNullOrWhiteSpace(item.SourceEvidence) || string.IsNullOrWhiteSpace(item.InputPartition) ||
                    string.IsNullOrWhiteSpace(item.ExpectedObservation) || item.Inputs.Count == 0)
                {
                    reason = $"plan case {item.CaseId} has incomplete evidence, partition, inputs or observation";
                    return null;
                }
                cases.Add(item);
            }
            if (!ValidateRequiredCases(cases.Select(c => (c.CaseId, c.Category)).ToList(), out reason)) return null;
            if (cases.Single(c => c.CaseId == "B1").Inputs.Count < 3)
            {
                reason = "B1 must specify below, at and above inputs";
                return null;
            }
            if (cases.Select(c => c.InputPartition.Trim()).Distinct(StringComparer.OrdinalIgnoreCase).Count() != 5)
            {
                reason = "all five plan cases must use distinct input partitions";
                return null;
            }
            reason = null;
            return new GeneratedTestPlan(name.Trim(), cases);
        }
        catch (JsonException ex)
        {
            reason = $"test-plan JSON parse failed: {ex.Message}";
            return null;
        }
    }

    public static GeneratedTestSource? Parse(string raw, out string? reason)
    {
        try
        {
            using var document = JsonDocument.Parse(Unfence(raw));
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object)
            {
                reason = "generated-test output is not a JSON object";
                return null;
            }
            var usings = StringArray(root, "using_directives");
            if (usings.Any(x => !x.StartsWith("using ", StringComparison.Ordinal) || !x.EndsWith(';')))
            {
                reason = "using_directives contains an invalid directive";
                return null;
            }
            var suiteName = StringProperty(root, "suite_name");
            if (string.IsNullOrWhiteSpace(suiteName) || !root.TryGetProperty("cases", out var casesElement) ||
                casesElement.ValueKind != JsonValueKind.Array)
            {
                reason = "generated-test output is missing suite_name or cases";
                return null;
            }

            var cases = new List<GeneratedTestCase>();
            foreach (var element in casesElement.EnumerateArray())
            {
                if (!TryReadIdentity(element, out var id, out var category, out reason)) return null;
                var testName = StringProperty(element, "test_name");
                var body = StringProperty(element, "test_body");
                if (string.IsNullOrWhiteSpace(testName) || string.IsNullOrWhiteSpace(body))
                {
                    reason = $"suite case {id} is missing test_name or test_body";
                    return null;
                }
                cases.Add(new GeneratedTestCase(id!, category, testName.Trim(), body));
            }
            if (!ValidateRequiredCases(cases.Select(c => (c.CaseId, c.Category)).ToList(), out reason)) return null;
            if (cases.Select(c => c.TestName).Distinct(StringComparer.OrdinalIgnoreCase).Count() != 5)
            {
                reason = "all five suite cases must have distinct test names";
                return null;
            }

            var helper = StringProperty(root, "helper_code") ?? string.Empty;
            var inlineBody = RenderInlineBody(cases);
            reason = null;
            return new GeneratedTestSource(suiteName.Trim(), usings, inlineBody)
            {
                HelperCode = helper,
                Cases = cases
            };
        }
        catch (JsonException ex)
        {
            reason = $"generated-test JSON parse failed: {ex.Message}";
            return null;
        }
    }

    private static bool MatchesPlan(GeneratedTestSource source, GeneratedTestPlan plan, out string? reason)
    {
        if (!string.Equals(source.TestName, plan.SuiteName, StringComparison.Ordinal))
        {
            reason = "implemented suite_name does not match the frozen plan";
            return false;
        }
        for (var i = 0; i < RequiredCases.Length; i++)
        {
            if (source.Cases[i].CaseId != plan.Cases[i].CaseId || source.Cases[i].Category != plan.Cases[i].Category)
            {
                reason = "implemented cases do not match the frozen plan";
                return false;
            }
        }
        reason = null;
        return true;
    }

    private static bool PreservesCases(GeneratedTestSource original, GeneratedTestSource corrected, out string? reason)
    {
        if (!original.Cases.SequenceEqual(corrected.Cases))
        {
            reason = "compile-only correction changed a frozen test case";
            return false;
        }
        reason = null;
        return true;
    }

    private static bool ValidateRequiredCases(
        IReadOnlyList<(string Id, GeneratedTestCaseCategory Category)> cases,
        out string? reason)
    {
        if (cases.Count != RequiredCases.Length)
        {
            reason = "generated suite must contain exactly five cases";
            return false;
        }
        for (var i = 0; i < RequiredCases.Length; i++)
        {
            if (cases[i] != RequiredCases[i])
            {
                reason = $"case {i + 1} must be {RequiredCases[i].Id}/{CategoryName(RequiredCases[i].Category)}";
                return false;
            }
        }
        reason = null;
        return true;
    }

    private static bool TryReadIdentity(
        JsonElement element,
        out string? id,
        out GeneratedTestCaseCategory category,
        out string? reason)
    {
        id = StringProperty(element, "case_id")?.Trim();
        var rawCategory = StringProperty(element, "category");
        category = default;
        if (string.IsNullOrWhiteSpace(id) || !TryParseCategory(rawCategory, out category))
        {
            reason = "case is missing a valid case_id or category";
            return false;
        }
        reason = null;
        return true;
    }

    private static bool TryParseCategory(string? value, out GeneratedTestCaseCategory category)
    {
        category = value switch
        {
            "happy_path" => GeneratedTestCaseCategory.HappyPath,
            "empty_or_invalid" => GeneratedTestCaseCategory.EmptyOrInvalid,
            "boundary_values" => GeneratedTestCaseCategory.BoundaryValues,
            "alternative_path" => GeneratedTestCaseCategory.AlternativePath,
            "dependency_or_state" => GeneratedTestCaseCategory.DependencyOrState,
            _ => (GeneratedTestCaseCategory)(-1)
        };
        return (int)category >= 0;
    }

    private static string CategoryName(GeneratedTestCaseCategory category) => category switch
    {
        GeneratedTestCaseCategory.HappyPath => "happy_path",
        GeneratedTestCaseCategory.EmptyOrInvalid => "empty_or_invalid",
        GeneratedTestCaseCategory.BoundaryValues => "boundary_values",
        GeneratedTestCaseCategory.AlternativePath => "alternative_path",
        GeneratedTestCaseCategory.DependencyOrState => "dependency_or_state",
        _ => throw new ArgumentOutOfRangeException(nameof(category))
    };

    private static string RenderInlineBody(IEnumerable<GeneratedTestCase> cases) => string.Join(
        Environment.NewLine,
        cases.Select(test => $"{{ // {test.CaseId}: {test.TestName}\n{test.TestBody}\n}}"));

    private static string Unfence(string raw)
    {
        var json = raw.Trim();
        if (!json.StartsWith("```", StringComparison.Ordinal)) return json;
        json = string.Join('\n', json.Split('\n').Skip(1));
        var fence = json.LastIndexOf("```", StringComparison.Ordinal);
        return fence >= 0 ? json[..fence].Trim() : json;
    }

    private static string? StringProperty(JsonElement element, string name) =>
        element.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString()
            : null;

    private static List<string> StringArray(JsonElement element, string name)
    {
        var values = new List<string>();
        if (!element.TryGetProperty(name, out var array) || array.ValueKind != JsonValueKind.Array) return values;
        foreach (var item in array.EnumerateArray())
            if (item.ValueKind == JsonValueKind.String && item.GetString() is { } value)
                values.Add(value.Trim());
        return values;
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
