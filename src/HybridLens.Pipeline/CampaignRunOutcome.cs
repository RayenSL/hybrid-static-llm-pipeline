namespace HybridLens.Pipeline;

/// <summary>Campaign execution outcome; the CLI maps it to an exit status.</summary>
public enum CampaignRunOutcome
{
    Completed,
    InvalidResumeState,
    AssignmentFailed
}
