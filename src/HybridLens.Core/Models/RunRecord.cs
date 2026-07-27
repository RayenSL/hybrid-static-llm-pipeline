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
    /// <summary>The raw code excerpt captured by the detector for downstream generation and audit.</summary>
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

    /// <summary>Architecture arm: "analyser_only", "hybrid", or "agentic" (§4.4.1).</summary>
    public          string?          Architecture     { get; init; }

    // ── Generated-test factorial extension (null on legacy/original-study rows) ──
    /// <summary>True when a static-analysis finding was supplied to the repair model.</summary>
    public          bool?            GroundingEnabled       { get; init; }
    /// <summary>Frozen control-structure factor: "single_shot" or "iterative".</summary>
    public          string?          ControlStructure       { get; init; }
    /// <summary>Assigned generated-test condition, regardless of whether generation/admission succeeded (ITT).</summary>
    public          bool?            VisibleTestsEnabled    { get; init; }
    /// <summary>True only when an admitted visible characterization artefact was available to this repair attempt.</summary>
    public          bool?            VisibleTestAvailable   { get; init; }
    /// <summary>Path to the immutable generated-test artefact supplied to this attempt.</summary>
    public          string?          VisibleTestArtifactRef { get; init; }
    /// <summary>SHA-256 of the admitted visible test; used to prove it was not edited during repair.</summary>
    public          string?          VisibleTestSha256      { get; init; }
    /// <summary>Final execution result of the original frozen visible test. Null when unavailable or not executed.</summary>
    public          bool?            VisibleTestPassed      { get; init; }

    /// <summary>Total evaluated-model calls consumed by the repair attempt.</summary>
    public          int?             LlmCallCount           { get; init; }
    /// <summary>Total production build attempts consumed by the repair attempt.</summary>
    public          int?             BuildAttemptCount      { get; init; }
    /// <summary>Total visible-test executions consumed by the repair attempt.</summary>
    public          int?             TestAttemptCount       { get; init; }
    /// <summary>Cumulative visible-test execution time for this attempt.</summary>
    public          double?          TestDurationMs         { get; init; }

    /// <summary>Common frozen final-source artefact used by whole-solution and private Layer-3 evaluation.</summary>
    public          string?          MaterializedSourceRef  { get; init; }
    /// <summary>SHA-256 of the exact final production source stored in <see cref="MaterializedSourceRef"/>.</summary>
    public          string?          MaterializedSourceSha256 { get; init; }

    // ── Agentic / ungrounded detection fields (null for analyser/hybrid rows) ──
    /// <summary>Symbol the agentic model reported for this self-detected finding.</summary>
    public          string?          LlmReportedSymbol { get; init; }
    /// <summary>Line the agentic model reported.</summary>
    public          int?             LlmReportedLine   { get; init; }
    /// <summary>Anti-pattern type the agent reported (raw). The match is location-based (§4.5.1), so a
    /// mislabelled type does not prevent a match — this field lets type-mislabelling be measured descriptively.</summary>
    public          string?          LlmReportedAntiPattern { get; init; }
    /// <summary>RunId of the known instance this agentic finding matched, or null if spurious.</summary>
    public          string?          MatchedInstanceId { get; init; }
    /// <summary>True when an agentic finding matched no known instance (extra/spurious detection).</summary>
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

    // ── Verified-repair outcome (objective; §4.5.1, §4.7.1) ──────────────────
    // Populated only on verification rows produced by the verify-repair step;
    // null on every generation row, so the addition is backward-compatible.
    /// <summary>RunId of the hybrid generation row whose repair this row verifies (links back to the hybrid run).</summary>
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

    // ── Whole-solution quality impact (opt-in; § quality-impact) ─────────────
    /// <summary>
    /// Before→after whole-solution quality change for this applied repair, measured only on rows whose
    /// applied state built (a meaningful "after" exists). Two instruments: the study's own detector over
    /// the whole solution (Layer 1, self-scored) and Microsoft.CodeAnalysis.NetAnalyzers (Layer 2,
    /// independent — breaks the self-scoring circularity). Null unless the run was invoked with
    /// <c>--quality-diff</c>, and null on generation/detection rows, unapplicable rows, and build-failed
    /// rows. On the iterative arms only the <c>final</c> snapshot carries it (the state a developer would ship).
    /// </summary>
    public          QualityDelta?    QualityDelta             { get; init; }

    // ── Agentic loop fields (§4.4.1, §4.8; null on analyser/hybrid rows) ──────
    /// <summary>Number of edit→build attempts the agentic trajectory consumed.</summary>
    public          int?             AgenticIterations        { get; init; }
    /// <summary>True when the trajectory stopped because the iteration budget was exhausted rather than the agent declaring completion (a distinct outcome, §4.8.1).</summary>
    public          bool?            AgenticBudgetExhausted   { get; init; }
    /// <summary>Path to the frozen trajectory artefact (all turns + build results + final source) — reproducibility at the artefact level (§4.8.5).</summary>
    public          string?          AgenticTrajectoryRef     { get; init; }
    /// <summary>On an agentic verified-repair row: whether the agent reported a finding matching this seeded instance (lets analysis restrict the paired comparison to recovered cases, §4.4.1 H1b). True by construction on the grounded-iterative arm, which is supplied the finding.</summary>
    public          bool?            AgenticRecovered         { get; init; }
    /// <summary>
    /// Which snapshot of the iterative trajectory this verified-repair row scores: "first_build" (the
    /// state submitted at the agent's first build, before any compiler feedback — the single-pass cell of
    /// the §4.4.1 2×2) or "final" (the state when the agent declared completion or exhausted its budget).
    /// Both the ungrounded agentic and grounded-iterative arms emit one row of each per instance, so the
    /// iteration effect (final vs first_build) is read within an arm and the grounding effect across arms.
    /// Null on analyser/hybrid rows and on agentic detection finding rows.
    /// </summary>
    public          string?          AgenticSnapshot          { get; init; }

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
