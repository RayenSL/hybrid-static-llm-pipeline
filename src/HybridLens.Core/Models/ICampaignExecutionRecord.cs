namespace HybridLens.Core.Models;

/// <summary>Identity and trace contract shared by persisted campaign ledger rows.</summary>
public interface ICampaignExecutionRecord
{
    string CampaignId { get; }
    string AssignmentId { get; }
    bool Completed { get; }
    string TraceFile { get; }
}
