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
    /// <summary>The raw code excerpt from the detector — what the rater sees in the blinded viewer.</summary>
    public          string?          Snippet          { get; init; }

    /// <summary>
    /// Detector-computed metric values that triggered the detection — the structured
    /// criterion record promised in thesis §5.1.2 / §5.2.7. For God Class:
    /// ATFD / WMC / TCC (+ thresholds); for Long Method: CyclomaticComplexity / LinesOfCode.
    /// Dictionary keys are preserved verbatim (not snake-cased) for direct analysis.
    /// </summary>
    public          IReadOnlyDictionary<string, double>? Metrics { get; init; }

    // ── Independent variables ────────────────────────────────────────────────
    public required ContextLevel     ContextLevel     { get; init; }
    public required string           ModelName        { get; init; }
    public required string           PromptVersion    { get; init; }

    /// <summary>Architecture arm: "analyser_only", "hybrid", or "llm_only" (§4.4.1).</summary>
    public          string?          Architecture     { get; init; }

    // ── LLM-only detection fields (null for analyser/hybrid rows) ────────────
    /// <summary>Symbol the LLM-only model reported for this self-detected finding.</summary>
    public          string?          LlmReportedSymbol { get; init; }
    /// <summary>Line the LLM-only model reported.</summary>
    public          int?             LlmReportedLine   { get; init; }
    /// <summary>RunId of the known instance this LLM-only finding matched, or null if spurious.</summary>
    public          string?          MatchedInstanceId { get; init; }
    /// <summary>True when an LLM-only finding matched no known instance (extra/spurious detection).</summary>
    public          bool?            IsSpurious        { get; init; }
    /// <summary>True when the prompt input was likely truncated by the model's context window (§4.8).</summary>
    public          bool?            ContextTruncated  { get; init; }

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

    // ── Verified-repair outcome (objective; §4.5.1, §4.7.1) ──────────────────
    // Populated only on verification rows produced by the verify-repair step;
    // null on every generation row, so the addition is backward-compatible.
    /// <summary>RunId of the generation row whose repair this row verifies (links back to the hybrid / llm-only run).</summary>
    public          string?          SourceRunId              { get; init; }
    /// <summary>Non-evaluated Claude-family model that applied the repair strict-literally (§4.3, §4.7.1).</summary>
    public          string?          ApplierModel             { get; init; }
    /// <summary>Frozen applier prompt version (Appendix A.1).</summary>
    public          string?          ApplierPromptVersion     { get; init; }
    /// <summary>True/false the applier could apply the repair literally; null when this is not a verification row.</summary>
    public          bool?            RepairApplicable         { get; init; }
    /// <summary>Applier's reason when the repair was too vague to apply literally; null otherwise.</summary>
    public          string?          RepairUnapplicableReason { get; init; }
    /// <summary>True when the applied solution compiled (the build gate). Null when unapplicable or not a verification row.</summary>
    public          bool?            BuildPassed              { get; init; }
    /// <summary>Triggering metric re-measured on the applied source. Null when the build failed, the repair was unapplicable, or the instance resolved away.</summary>
    public          IReadOnlyDictionary<string, double>? RemeasuredMetrics { get; init; }
    /// <summary>Ordinal ladder: unapplicable &lt; build_fails &lt; builds_unresolved &lt; resolved (§4.5.1).</summary>
    public          VerifiedRepairOutcome? VerifiedRepairLadder { get; init; }
    /// <summary>Binary headline outcome = applies ∧ builds ∧ metric-resolved.</summary>
    public          bool?            VerifiedRepairSuccess    { get; init; }

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

/// <summary>
/// Ordinal verified-repair ladder (§4.5.1). Higher is better; declared in ascending order
/// so the values sort naturally. The binary headline outcome <c>verified_repair_success</c>
/// is true only at <see cref="Resolved"/>. Serialised snake_case (e.g. "builds_unresolved").
/// </summary>
public enum VerifiedRepairOutcome
{
    /// <summary>Applier judged the repair too vague to apply literally.</summary>
    Unapplicable,
    /// <summary>Repair applied, but the resulting solution did not compile.</summary>
    BuildFails,
    /// <summary>Applied and compiled, but the triggering metric still fires.</summary>
    BuildsUnresolved,
    /// <summary>Applied, compiled, and the triggering metric no longer fires.</summary>
    Resolved
}
