namespace Characterization;

internal static class PrivateCaseCatalog
{
    private static readonly string[] CaseIds =
    [
        "P01-happy-flow",
        "P02-empty-or-minimal",
        "P03-invalid-input",
        "P04-below-boundary",
        "P05-at-boundary",
        "P06-above-boundary",
        "P07-alternate-valid-mode",
        "P08-collaborator-outcome",
        "P09-repeat-or-state-transition",
        "P10-compound-ordering",
    ];

    private static readonly IReadOnlyDictionary<string, string> EvaluatedIds =
        new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["Ordering.OrderProcessor"] = "GC-01",
            ["Ordering.CheckoutCoordinator"] = "GC-02",
            ["Ordering.ReturnsHandler"] = "GC-03",
            ["Invoicing.BillingManager"] = "GC-04",
            ["Invoicing.StatementBuilder"] = "GC-05",
            ["Inventory.StockController"] = "GC-06",
            ["Inventory.CycleCountService"] = "GC-07",
            ["Scheduling.ScheduleManager"] = "GC-08",
            ["Scheduling.RecurrenceEngine"] = "GC-09",
            ["Notifications.NotificationCenter"] = "GC-10",
            ["Fulfilment.FulfilmentCoordinator"] = "GC-11",
            ["Subscriptions.SubscriptionAccountService"] = "GC-12",
            ["ServiceDesk.CaseOperationsManager"] = "GC-13",
            ["OrderImporter.ImportBatch"] = "LM-01",
            ["PricingRules.ApplyAdjustments"] = "LM-02",
            ["InvoiceRenderer.Render"] = "LM-03",
            ["VatResolver.Resolve"] = "LM-04",
            ["ReplenishmentPlanner.BuildPlan"] = "LM-05",
            ["AllocationCalculator.Allocate"] = "LM-06",
            ["Scheduler.PlaceJobs"] = "LM-07",
            ["SlotFinder.FindFirstFit"] = "LM-08",
            ["DispatchPipeline.Run"] = "LM-09",
            ["RetryPolicy.NextDelay"] = "LM-10",
            ["Claims.ClaimAdjudicator.Evaluate"] = "LM-11",
            ["Payments.SettlementBatchProcessor.Process"] = "LM-12",
            ["AccessControl.AccessDecisionEngine.Decide"] = "LM-13",
        };

    public static IReadOnlyList<(string Key, Func<string> Drive)> Expand(
        IEnumerable<(string Key, Func<string> Drive)> rawDrivers)
    {
        var expanded = new List<(string Key, Func<string> Drive)>();
        foreach (var raw in rawDrivers)
        {
            if (!EvaluatedIds.TryGetValue(raw.Key, out var instanceId))
            {
                expanded.Add(raw);
                continue;
            }

            for (var caseIndex = 0; caseIndex < CaseIds.Length; caseIndex++)
            {
                var capturedIndex = caseIndex;
                expanded.Add(($"{instanceId}.{CaseIds[caseIndex]}", () => SelectObservation(raw, capturedIndex)));
            }
        }

        return expanded;
    }

    private static string SelectObservation((string Key, Func<string> Drive) raw, int caseIndex)
    {
        var lines = raw.Drive()
            .Replace("\r", "")
            .Split('\n', StringSplitOptions.RemoveEmptyEntries);
        if (lines.Length < CaseIds.Length)
            throw new InvalidOperationException($"{raw.Key} exposes {lines.Length} observations; ten are required.");

        var selected = caseIndex == CaseIds.Length - 1
            ? lines.Length - 1
            : (int)Math.Round(caseIndex * (lines.Length - 1d) / (CaseIds.Length - 1d), MidpointRounding.AwayFromZero);
        return lines[selected];
    }
}
