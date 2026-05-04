namespace HybridLens.Core.Models;

/// <summary>
/// One persisted experiment record per (finding × model × context-level × run).
/// Written append-only to a JSONL file by <c>IRunStore</c>.
///
/// This is the unit of analysis for the thesis: every field below is required
/// either by the research questions (Req #2) or to explain a result post-hoc.
///
/// Fields use snake_case property names in JSON so the file can be loaded
/// directly into pandas/R without renaming.
/// </summary>
public sealed record RunRecord
{
    // ── Experiment identity ──────────────────────────────────────────────────
    public required string           RunId            { get; init; }   // unique per RunRecord
    public required DateTimeOffset   Timestamp        { get; init; }
    public required int              RunNumber        { get; init; }   // 1..N for repeated runs

    // ── Subject under analysis ───────────────────────────────────────────────
    public required AntiPatternType  AntiPatternType  { get; init; }
    public required string           FilePath         { get; init; }
    public required string           SymbolName       { get; init; }
    public required int              Line             { get; init; }   // code_location
    public required Severity         Severity         { get; init; }

    // ── Independent variables ────────────────────────────────────────────────
    public required ContextLevel     ContextLevel     { get; init; }
    public required string           ModelName        { get; init; }
    public required string           PromptVersion    { get; init; }

    // ── Raw artefacts (full audit trail) ─────────────────────────────────────
    public required string           RawSystemPrompt  { get; init; }
    public required string           RawUserPrompt    { get; init; }
    public          string?          RawLlmOutput     { get; init; }
    public          int?             InputTokens      { get; init; }
    public          int?             OutputTokens     { get; init; }
    public          double?          DurationMs       { get; init; }

    // ── Parsed dependent variables ───────────────────────────────────────────
    /// <summary>Parsed "explanation" / problem statement.</summary>
    public          string?          ParsedExplanation  { get; init; }
    /// <summary>Parsed quality-impact section. Empty for prompt v1.0.0; populated when prompt is upgraded.</summary>
    public          string?          ParsedQualityImpact { get; init; }
    /// <summary>Parsed remediation / suggested fix.</summary>
    public          string?          ParsedSuggestedFix { get; init; }
    /// <summary>Parsed risks / assumptions section. Empty for prompt v1.0.0.</summary>
    public          string?          ParsedRisks        { get; init; }

    // ── ISO/IEC 25010 quality-attribute evaluation (prompt v1.1.0+) ──────────
    /// <summary>Literature-derived ground truth — attributes this anti-pattern is expected to degrade.</summary>
    public          IReadOnlyList<string>? ExpectedQualityAttributes      { get; init; }
    /// <summary>Attributes the LLM independently mentioned in its output (auto-extracted, lexical).</summary>
    public          IReadOnlyList<string>? LlmQualityAttributesMentioned  { get; init; }
    /// <summary>1 = at least one expected attribute is mentioned; 0 = none mentioned; null = no usable output.</summary>
    public          int?                   QualityAttributeAlignment      { get; init; }
    /// <summary>Free-text rater notes; populated by <c>score_runs.py</c> on second-rater review. Always null at write time.</summary>
    public          string?                QualityAttributeNotes          { get; init; }

    // ── Failure & parse status ───────────────────────────────────────────────
    public required ParseStatus      ParseStatus      { get; init; }
    /// <summary>Null on success. Non-null categorises the failure for honest reporting (Req #8).</summary>
    public          ErrorStatus?     ErrorStatus      { get; init; }
    public          string?          ErrorMessage     { get; init; }
}

public enum ParseStatus
{
    /// <summary>No LLM output available (request failed before parsing).</summary>
    NotAttempted,
    /// <summary>Output parsed cleanly into all expected fields.</summary>
    Ok,
    /// <summary>Output present but did not match the expected structured format.</summary>
    Failed
}

public enum ErrorStatus
{
    ApiFailure,
    EmptyResponse,
    ParseFailure,
    TokenLimitTruncation,
    UnsupportedFile,
    ContextExtractionFailure,
    Cancelled,
    Unknown
}
