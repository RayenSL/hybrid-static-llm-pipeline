using HybridLens.Pipeline;

namespace HybridLens.CLI.Commands;

internal static class CampaignExitStatus
{
    public static int From(CampaignRunOutcome outcome) => outcome switch
    {
        CampaignRunOutcome.Completed => 0,
        CampaignRunOutcome.AssignmentFailed => 1,
        CampaignRunOutcome.InvalidResumeState => 2,
        _ => throw new ArgumentOutOfRangeException(nameof(outcome), outcome, null)
    };
}
