namespace HybridLens.Core.Models;

public sealed record LadderExecutionRecord : ICampaignExecutionRecord
{
    public required string CampaignId { get; init; }
    public required string AssignmentId { get; init; }
    public required int Order { get; init; }
    public required ContextLevel ContextLevel { get; init; }
    public required DateTimeOffset Timestamp { get; init; }
    public required bool Completed { get; init; }
    public required string TraceFile { get; init; }
    public required string TraceSha256 { get; init; }
    public required List<string> RunIds { get; init; }
    public required int EvaluatedModelCalls { get; init; }
    public required int CrossFileFiles { get; init; }
    public required bool CrossFileTruncated { get; init; }
    public required int InputTokens { get; init; }
    public required int OutputTokens { get; init; }
    public string? Error { get; init; }
}
