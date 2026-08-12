namespace HybridLens.Core.Models;

/// <summary>
/// One immutable, visible characterization-test artefact generated from pristine production code
/// before repair. It is repair feedback, not the independent Layer-3 correctness oracle.
/// </summary>
public sealed record GeneratedTestArtifact
{
    public required string ArtifactId { get; init; }
    public required string ArtifactRef { get; init; }
    public required DateTimeOffset Timestamp { get; init; }
    public required string SourceFile { get; init; }
    public required string SourceSha256 { get; init; }
    public string? DependencyContextSha256 { get; init; }
    public required string TargetSymbolName { get; init; }
    public required int TargetStartLine { get; init; }
    public required int TargetEndLine { get; init; }
    public required string ProjectFile { get; init; }
    public required string ModelName { get; init; }
    public required string PromptVersion { get; init; }
    public required string RawSystemPrompt { get; init; }
    public required string RawUserPrompt { get; init; }
    public string? RawLlmOutput { get; init; }
    public string? RawPlanSystemPrompt { get; init; }
    public string? RawPlanUserPrompt { get; init; }
    public string? RawPlanLlmOutput { get; init; }
    public string? RawCorrectionPrompt { get; init; }
    public string? RawCorrectionLlmOutput { get; init; }
    public int InputTokens { get; init; }
    public int OutputTokens { get; init; }
    public int GenerationCallCount { get; init; }
    public int PlanInputTokens { get; init; }
    public int PlanOutputTokens { get; init; }
    public int ImplementationInputTokens { get; init; }
    public int ImplementationOutputTokens { get; init; }
    public int CorrectionInputTokens { get; init; }
    public int CorrectionOutputTokens { get; init; }
    public double DurationMs { get; init; }

    public string? TestName { get; init; }
    public IReadOnlyList<string> UsingDirectives { get; init; } = [];
    public string? TestBody { get; init; }
    public string HelperCode { get; init; } = string.Empty;
    public IReadOnlyList<GeneratedTestCase> TestCases { get; init; } = [];
    public GeneratedTestPlan? TestPlan { get; init; }
    public string? TestSha256 { get; init; }

    public required GeneratedTestAdmissionStatus AdmissionStatus { get; init; }
    public string? AdmissionReason { get; init; }
    public bool ParsePassed { get; init; }
    public bool AssertionGatePassed { get; init; }
    public bool? BuildPassed { get; init; }
    public IReadOnlyList<bool> BaselineRunsPassed { get; init; } = [];
    public string? AdmissionOutputTail { get; init; }

    public bool Admitted => AdmissionStatus == GeneratedTestAdmissionStatus.Admitted;
}

public sealed record GeneratedTestSource(
    string TestName,
    IReadOnlyList<string> UsingDirectives,
    string TestBody)
{
    public string HelperCode { get; init; } = string.Empty;
    public IReadOnlyList<GeneratedTestCase> Cases { get; init; } = [];
    public bool IsStructuredSuite => Cases.Count > 0;
}

public sealed record GeneratedTestPlan(
    string SuiteName,
    IReadOnlyList<GeneratedTestPlanCase> Cases);

public sealed record GeneratedTestPlanCase(
    string CaseId,
    GeneratedTestCaseCategory Category,
    string SourceEvidence,
    string InputPartition,
    IReadOnlyList<string> Inputs,
    string ExpectedObservation);

public sealed record GeneratedTestCase(
    string CaseId,
    GeneratedTestCaseCategory Category,
    string TestName,
    string TestBody);

public enum GeneratedTestCaseCategory
{
    HappyPath,
    EmptyOrInvalid,
    BoundaryValues,
    AlternativePath,
    DependencyOrState
}

public sealed record GeneratedTestAdmissionResult(
    GeneratedTestAdmissionStatus Status,
    string? Reason,
    bool AssertionGatePassed,
    bool? BuildPassed,
    IReadOnlyList<bool> BaselineRunsPassed,
    string OutputTail)
{
    public bool Admitted => Status == GeneratedTestAdmissionStatus.Admitted;
}

public sealed record GeneratedTestExecutionResult(
    bool BuildPassed,
    bool TestPassed,
    double DurationMs,
    string OutputTail);

public enum GeneratedTestAdmissionStatus
{
    GenerationFailed,
    ParseFailed,
    AssertionGateFailed,
    BuildFailed,
    BaselineFailed,
    Flaky,
    Admitted
}
