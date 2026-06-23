using HybridLens.Core.Abstractions;
using HybridLens.Core.Configuration;
using HybridLens.Core.Models;
using HybridLens.StaticAnalysis.Abstractions;
using HybridLens.StaticAnalysis.Detectors;
using HybridLens.StaticAnalysis.Workspace;

namespace HybridLens.StaticAnalysis;

/// <summary>
/// Roslyn-backed <see cref="IRepairMeasurer"/>. Loads the project that owns the applied file,
/// re-runs the one detector for the instance's anti-pattern, and reports whether a finding of
/// that type still matches the instance at that file — the re-measurement of §4.5.1. Uses the
/// SAME detector implementation and thresholds as the analyser arm, so a metric-resolved verdict
/// means the triggering rule genuinely no longer fires.
/// </summary>
public sealed class RoslynRepairMeasurer(DetectorConfig detectorConfig, WorkspaceConfig workspaceConfig)
    : IRepairMeasurer
{
    public async Task<RemeasureResult> RemeasureAsync(
        AntiPatternType type,
        string workingFilePath,
        string instanceSymbol,
        CancellationToken cancellationToken = default)
    {
        var project = FindProject(workingFilePath)
            ?? throw new FileNotFoundException($"No .csproj found above '{workingFilePath}'.");

        using var loader = new WorkspaceLoader(workspaceConfig);
        var compilations = await loader.LoadAsync(project, cancellationToken);

        IDetector detector = type switch
        {
            AntiPatternType.GodClass         => new GodClassDetector(detectorConfig.GodClass),
            AntiPatternType.LongMethod       => new LongMethodDetector(detectorConfig.LongMethod),
            AntiPatternType.ObsoleteApiUsage => new ObsoleteApiDetector(detectorConfig.ObsoleteApi),
            _ => throw new ArgumentOutOfRangeException(nameof(type), type, "Unknown anti-pattern type.")
        };

        var fileFull = Path.GetFullPath(workingFilePath);

        foreach (var compilation in compilations)
        {
            foreach (var finding in detector.Detect(compilation))
            {
                if (finding.Type != type) continue;
                if (!PathsEqual(finding.FilePath, fileFull)) continue;
                if (!RepairInstanceMatcher.Matches(type, finding.SymbolName, instanceSymbol)) continue;

                // The instance still triggers its detection rule on the applied source.
                return new RemeasureResult(StillTriggers: true, Metrics: finding.Metrics);
            }
        }

        // No matching finding remained — the repair drove the triggering metric below threshold.
        return new RemeasureResult(StillTriggers: false, Metrics: null);
    }

    private static string? FindProject(string filePath)
    {
        var dir = new FileInfo(filePath).Directory;
        while (dir is not null)
        {
            var csproj = dir.GetFiles("*.csproj").FirstOrDefault();
            if (csproj is not null) return csproj.FullName;
            dir = dir.Parent;
        }
        return null;
    }

    private static bool PathsEqual(string a, string b)
        => string.Equals(Path.GetFullPath(a), Path.GetFullPath(b), StringComparison.OrdinalIgnoreCase);
}
