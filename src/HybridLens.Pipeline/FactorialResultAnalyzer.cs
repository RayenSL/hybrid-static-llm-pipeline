using HybridLens.Core.Models;

namespace HybridLens.Pipeline;

/// <summary>Prespecified Long Method/God Class intention-to-treat derivation and arm summary.</summary>
public static class FactorialResultAnalyzer
{
    public static FactorialAnalysisResult Analyze(
        IReadOnlyList<RunRecord> runRecords,
        IReadOnlyList<PrivateLayer3Result> privateResults)
    {
        var privateByArtifact = new Dictionary<string, PrivateLayer3Result>(StringComparer.OrdinalIgnoreCase);
        foreach (var result in privateResults)
        {
            var key = NormalizePath(result.ArtifactRef);
            if (!privateByArtifact.TryAdd(key, result))
                throw new InvalidDataException($"duplicate private Layer-3 result for artefact: {result.ArtifactRef}");
        }

        var selected = runRecords.Where(IsFactorialFinalAttempt).ToList();
        if (selected.Count == 0)
            throw new InvalidDataException("no final Long Method/God Class factorial attempts were found");
        var duplicateRunId = selected.GroupBy(r => r.RunId, StringComparer.Ordinal).FirstOrDefault(g => g.Count() > 1);
        if (duplicateRunId is not null)
            throw new InvalidDataException($"duplicate assigned attempt RunId: {duplicateRunId.Key}");

        var attempts = new List<FactorialAttemptOutcome>(selected.Count);
        foreach (var record in selected)
        {
            PrivateLayer3Result? privateResult = null;
            if (!string.IsNullOrWhiteSpace(record.MaterializedSourceRef))
            {
                var key = NormalizePath(record.MaterializedSourceRef);
                if (!privateByArtifact.TryGetValue(key, out privateResult))
                    throw new InvalidDataException(
                        $"missing private Layer-3 outcome for materialized attempt {record.RunId}: {record.MaterializedSourceRef}");
                if (record.BuildPassed == true && !privateResult.Evaluated)
                    throw new InvalidDataException($"built attempt {record.RunId} was not evaluated by private Layer 3");
            }

            var materialized = !string.IsNullOrWhiteSpace(record.MaterializedSourceRef);
            var built = record.BuildPassed == true;
            var resolved = record.VerifiedRepairSuccess == true;
            var privatePassed = privateResult?.Passed;
            int? totalTokens = record.InputTokens.HasValue || record.OutputTokens.HasValue
                ? (record.InputTokens ?? 0) + (record.OutputTokens ?? 0)
                : null;
            attempts.Add(new FactorialAttemptOutcome
            {
                RunId = record.RunId,
                InstanceKey = $"{record.FilePath}::{record.SymbolName}::{record.Line}",
                AntiPatternType = record.AntiPatternType,
                GroundingEnabled = record.GroundingEnabled!.Value,
                ControlStructure = record.ControlStructure!,
                VisibleTestsEnabled = record.VisibleTestsEnabled!.Value,
                VisibleTestAvailable = record.VisibleTestAvailable == true,
                Materialized = materialized,
                BuildPassed = built,
                MetricResolved = resolved,
                PrivateTestPassed = privatePassed,
                StrictSuccess = built && resolved && privatePassed == true,
                InputTokens = record.InputTokens,
                OutputTokens = record.OutputTokens,
                TotalTokens = totalTokens,
                LlmCalls = record.LlmCallCount,
                BuildAttempts = record.BuildAttemptCount,
                TestAttempts = record.TestAttemptCount,
                TestDurationMs = record.TestDurationMs,
                RepairDurationMs = record.DurationMs,
                MaterializedSourceRef = record.MaterializedSourceRef
            });
        }

        var arms = attempts
            .GroupBy(a => (a.GroundingEnabled, a.ControlStructure, a.VisibleTestsEnabled))
            .OrderBy(g => g.Key.ControlStructure, StringComparer.Ordinal)
            .ThenBy(g => g.Key.GroundingEnabled)
            .ThenBy(g => g.Key.VisibleTestsEnabled)
            .Select(g => Summarize(g.Key.GroundingEnabled, g.Key.ControlStructure, g.Key.VisibleTestsEnabled, g.ToList()))
            .ToList();
        return new FactorialAnalysisResult(attempts, arms);
    }

    private static bool IsFactorialFinalAttempt(RunRecord record)
    {
        if (record.AntiPatternType is not (AntiPatternType.LongMethod or AntiPatternType.GodClass)) return false;
        if (!record.GroundingEnabled.HasValue || !record.VisibleTestsEnabled.HasValue) return false;
        if (record.ControlStructure is not ("single_shot" or "iterative")) return false;
        if (record.ControlStructure == "iterative")
            return record.AgenticSnapshot == "final" && record.VerifiedRepairLadder is not null;
        return record.AgenticSnapshot is null;
    }

    private static FactorialArmSummary Summarize(
        bool grounded,
        string control,
        bool testEnabled,
        IReadOnlyList<FactorialAttemptOutcome> attempts)
    {
        var tokenObserved = attempts.Where(a => a.TotalTokens.HasValue).ToList();
        return new FactorialArmSummary
        {
            GroundingEnabled = grounded,
            ControlStructure = control,
            VisibleTestsEnabled = testEnabled,
            AssignedAttempts = attempts.Count,
            MaterializedAttempts = attempts.Count(a => a.Materialized),
            BuildPassedAttempts = attempts.Count(a => a.BuildPassed),
            MetricResolvedAttempts = attempts.Count(a => a.MetricResolved),
            PrivatePassedAttempts = attempts.Count(a => a.PrivateTestPassed == true),
            StrictSuccesses = attempts.Count(a => a.StrictSuccess),
            StrictSuccessRate = attempts.Count(a => a.StrictSuccess) / (double)attempts.Count,
            VisibleTestAvailabilityRate = attempts.Count(a => a.VisibleTestAvailable) / (double)attempts.Count,
            TokenObservedAttempts = tokenObserved.Count,
            MeanInputTokens = Mean(attempts.Select(a => a.InputTokens)),
            MeanOutputTokens = Mean(attempts.Select(a => a.OutputTokens)),
            MeanTotalTokens = Mean(attempts.Select(a => a.TotalTokens)),
            TotalTokensConsumed = tokenObserved.Count == 0 ? null : tokenObserved.Sum(a => (long)a.TotalTokens!.Value),
            MeanLlmCalls = Mean(attempts.Select(a => a.LlmCalls)),
            MeanBuildAttempts = Mean(attempts.Select(a => a.BuildAttempts)),
            MeanTestAttempts = Mean(attempts.Select(a => a.TestAttempts)),
            MeanTestDurationMs = Mean(attempts.Select(a => a.TestDurationMs)),
            MeanRepairDurationMs = Mean(attempts.Select(a => a.RepairDurationMs))
        };
    }

    private static double? Mean(IEnumerable<int?> values)
    {
        var observed = values.Where(v => v.HasValue).Select(v => (double)v!.Value).ToList();
        return observed.Count == 0 ? null : observed.Average();
    }

    private static double? Mean(IEnumerable<double?> values)
    {
        var observed = values.Where(v => v.HasValue).Select(v => v!.Value).ToList();
        return observed.Count == 0 ? null : observed.Average();
    }

    private static string NormalizePath(string path) => Path.GetFullPath(path).TrimEnd(Path.DirectorySeparatorChar);
}
