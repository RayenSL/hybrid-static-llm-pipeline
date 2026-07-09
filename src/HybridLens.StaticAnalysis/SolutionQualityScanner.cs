using System.Text.Json;
using HybridLens.Core.Abstractions;
using HybridLens.Core.Configuration;
using HybridLens.Core.Models;
using HybridLens.StaticAnalysis.Abstractions;
using HybridLens.StaticAnalysis.Detectors;
using HybridLens.StaticAnalysis.Workspace;

namespace HybridLens.StaticAnalysis;

/// <summary>
/// Whole-solution code-quality instrument for the quality-impact measurement. Produces a
/// <see cref="SolutionQualityScan"/> for one state of the solution using two independent instruments:
///
///  • <b>Layer 1</b> — re-runs the study's own three detectors (God Class / Long Method / Obsolete API)
///    over the WHOLE solution via Roslyn, giving per-category smell counts + per-finding identities so a
///    before→after diff can surface collateral (a smell created or resolved in a different file/category
///    than the one the repair targeted).
///
///  • <b>Layer 2</b> — parses the per-project SARIF v2.1 logs that a <c>8.0-all</c> build emits (via the
///    injected <see cref="DirectoryBuildPropsContent"/>) as an INDEPENDENT instrument. Rules that are
///    enabled-by-default form the low-noise <i>headline</i> tier (empirically identical to an
///    <c>8.0-recommended</c> build on the corpus); the full fired set is the <i>all</i> sensitivity tier.
///    Compiler obsolete warnings (CS0618/CS0619) are counted separately.
///
/// The scanner never builds — it consumes SARIF the caller's build already emitted, so the repair build
/// gate and the Layer-2 capture are the same build. The frozen corpus is never mutated; scans run on
/// working copies with the props injected.
/// </summary>
public sealed class SolutionQualityScanner(DetectorConfig detectorConfig, WorkspaceConfig workspaceConfig)
    : ISolutionQualityScanner
{
    /// <summary>
    /// CA maintainability-metric rules that overlap our own Layer-1 detector (cyclomatic complexity,
    /// class coupling, inheritance/maintainability). Excluded from Layer 2 so the same smell is not
    /// double-counted across the two instruments.
    /// </summary>
    private static readonly HashSet<string> ExcludedRules =
        new(StringComparer.OrdinalIgnoreCase) { "CA1501", "CA1502", "CA1505", "CA1506", "CA1509" };

    /// <summary>Compiler diagnostics that flag consumption of [Obsolete] API — the independent corroboration of the Obsolete-API detector.</summary>
    private static readonly HashSet<string> CompilerObsoleteRules =
        new(StringComparer.OrdinalIgnoreCase) { "CS0618", "CS0619" };

    /// <summary>
    /// Content of the <c>Directory.Build.props</c> injected at the working-copy root to turn on the full CA
    /// analyzer set and emit a per-project SARIF v2.1 log from the build. Per-project SARIF (keyed on
    /// <c>$(MSBuildProjectName)</c>) is required — a single shared ErrorLog is overwritten per project and
    /// captures only the last project's diagnostics; and <c>,version=2.1</c> must be set here (not via
    /// <c>-p:ErrorLog</c>, which silently emits SARIF v1.0 without rule categories). Both validated empirically.
    /// </summary>
    public const string DirectoryBuildPropsContent =
        "<Project>\n" +
        "  <!-- Injected by the HybridLens quality-impact measurement (Layer 2). Do not commit into the frozen corpus. -->\n" +
        "  <PropertyGroup>\n" +
        "    <EnableNETAnalyzers>true</EnableNETAnalyzers>\n" +
        "    <AnalysisLevel>8.0-all</AnalysisLevel>\n" +
        "    <ErrorLog>$(MSBuildProjectDirectory)\\$(MSBuildProjectName).sarif,version=2.1</ErrorLog>\n" +
        "  </PropertyGroup>\n" +
        "</Project>\n";

    /// <summary>
    /// Scans one state of the solution. <paramref name="solutionPath"/> is the .sln (or .csproj) to load for
    /// Layer 1; <paramref name="sarifRoot"/> is the directory tree under which the build's per-project
    /// <c>*.sarif</c> logs live (normally the working-copy root, same as the solution directory).
    /// </summary>
    public async Task<SolutionQualityScan> ScanAsync(
        string solutionPath, string sarifRoot, CancellationToken ct = default)
    {
        var (smellCounts, smellKeys, layer1Note) = await ScanLayer1Async(solutionPath, sarifRoot, ct);
        var (diagnostics, compilerObsolete, caAvailable, layer2Note) = ParseLayer2(sarifRoot);

        var headline = diagnostics.Where(d => d.EnabledByDefault).ToList();

        var note = string.Join(" | ", new[] { layer1Note, layer2Note }.Where(s => !string.IsNullOrEmpty(s)));

        return new SolutionQualityScan
        {
            SmellCountsByType    = smellCounts,
            SmellTotal           = smellCounts.Values.Sum(),
            SmellKeys            = smellKeys,

            CaHeadlineByRule     = CountBy(headline,    d => d.RuleId),
            CaHeadlineByCategory = CountBy(headline,    d => d.Category),
            CaHeadlineTotal      = headline.Count,

            CaAllByRule          = CountBy(diagnostics, d => d.RuleId),
            CaAllByCategory      = CountBy(diagnostics, d => d.Category),
            CaAllTotal           = diagnostics.Count,

            CompilerObsoleteCount = compilerObsolete,
            Diagnostics           = diagnostics,
            CaAvailable           = caAvailable,
            Note                  = string.IsNullOrEmpty(note) ? null : note
        };
    }

    /// <summary>
    /// Captures a full quality scan of whatever state is currently materialised in the working tree, using
    /// a DEDICATED analyzer build so the caller's own gate/loop builds can stay analyzer-free and remain the
    /// authoritative <c>dotnet build</c> gate. Injects <see cref="DirectoryBuildPropsContent"/> at
    /// <paramref name="workingRoot"/>, runs <paramref name="build"/> purely to emit SARIF (its pass/fail is
    /// ignored — the verified-repair ladder is measured elsewhere), scans, then removes the props so the next
    /// gate/loop build is unaffected. Any pre-existing <c>Directory.Build.props</c> is restored afterward.
    /// </summary>
    public async Task<SolutionQualityScan> BuildAndScanAsync(
        string solutionPath, string workingRoot,
        Func<string, int, CancellationToken, Task<(bool Ok, string Output)>> build,
        int buildTimeoutSeconds, CancellationToken ct = default)
    {
        var propsPath = Path.Combine(workingRoot, "Directory.Build.props");
        var hadProps  = File.Exists(propsPath);
        var saved     = hadProps ? await File.ReadAllTextAsync(propsPath, ct) : null;

        await File.WriteAllTextAsync(propsPath, DirectoryBuildPropsContent, ct);
        try
        {
            // The build is only to regenerate the per-project SARIF logs for the current state.
            await build(solutionPath, buildTimeoutSeconds, ct);
            return await ScanAsync(solutionPath, workingRoot, ct);
        }
        finally
        {
            try
            {
                if (hadProps) await File.WriteAllTextAsync(propsPath, saved!, ct);
                else File.Delete(propsPath);
            }
            catch { /* best effort — working tree is a temp copy */ }
        }
    }

    // ── Layer 1: custom detector over the whole solution ─────────────────────
    private async Task<(IReadOnlyDictionary<string, int> Counts, IReadOnlyList<string> Keys, string Note)>
        ScanLayer1Async(string solutionPath, string sarifRoot, CancellationToken ct)
    {
        using var loader = new WorkspaceLoader(workspaceConfig);
        var compilations = await loader.LoadAsync(solutionPath, ct);

        var detectors = new IDetector[]
        {
            new GodClassDetector(detectorConfig.GodClass),
            new LongMethodDetector(detectorConfig.LongMethod),
            new ObsoleteApiDetector(detectorConfig.ObsoleteApi)
        };

        var findings = compilations
            .SelectMany(c => detectors.SelectMany(d => d.Detect(c)))
            .ToList();

        var counts = findings
            .GroupBy(f => f.Type.ToString())
            .ToDictionary(g => g.Key, g => g.Count(), StringComparer.Ordinal);

        // Distinct per-finding identity so the before→after diff can localise collateral.
        var keys = findings
            .Select(f => $"{f.Type}|{Relativise(f.FilePath, sarifRoot)}|{f.SymbolName}")
            .Distinct(StringComparer.Ordinal)
            .OrderBy(k => k, StringComparer.Ordinal)
            .ToList();

        var note = loader.Warnings.Count > 0
            ? $"layer1: {loader.Warnings.Count} workspace warning(s)"
            : compilations.Count == 0 ? "layer1: no projects loaded" : "";

        return (counts, keys, note);
    }

    // ── Layer 2: parse per-project SARIF logs ────────────────────────────────
    private static (List<CaDiagnostic> Diags, int CompilerObsolete, bool Available, string Note)
        ParseLayer2(string sarifRoot)
    {
        if (!Directory.Exists(sarifRoot))
            return ([], 0, false, "layer2: sarif root missing");

        var sarifFiles = Directory
            .EnumerateFiles(sarifRoot, "*.sarif", SearchOption.AllDirectories)
            .Where(p => !IsUnderSkippedDir(p, sarifRoot))
            .ToList();

        if (sarifFiles.Count == 0)
            return ([], 0, false, "layer2: no SARIF emitted (build produced no analyzer log)");

        // Dedup identical diagnostics that appear when a file is compiled into more than one project.
        var seen = new HashSet<string>(StringComparer.Ordinal);
        var diags = new List<CaDiagnostic>();
        var compilerObsolete = 0;

        foreach (var file in sarifFiles)
        {
            JsonDocument doc;
            try { doc = JsonDocument.Parse(File.ReadAllText(file)); }
            catch { continue; }
            using (doc)
            {
                if (!doc.RootElement.TryGetProperty("runs", out var runs)) continue;
                foreach (var run in runs.EnumerateArray())
                {
                    var ruleMeta = BuildRuleMeta(run);
                    if (!run.TryGetProperty("results", out var results)) continue;

                    foreach (var res in results.EnumerateArray())
                    {
                        var ruleId = res.TryGetProperty("ruleId", out var rid) ? rid.GetString() ?? "" : "";
                        if (ruleId.Length == 0 || ExcludedRules.Contains(ruleId)) continue;

                        var (relFile, line, member) = ReadLocation(res, sarifRoot);

                        if (CompilerObsoleteRules.Contains(ruleId))
                        {
                            if (seen.Add($"{ruleId}|{relFile}|{line}")) compilerObsolete++;
                            continue;
                        }

                        // Headline/all tiers are CA-only (§ locked spec); IDE style rules and other
                        // compiler warnings are out of scope for the codebase-quality instrument.
                        if (!ruleId.StartsWith("CA", StringComparison.Ordinal)) continue;

                        var level = res.TryGetProperty("level", out var lv) ? lv.GetString() ?? "warning" : "warning";
                        var meta = ruleMeta.GetValueOrDefault(ruleId);

                        var dedupKey = $"{ruleId}|{relFile}|{line}|{(res.TryGetProperty("locations", out _) ? StartColumn(res) : 0)}";
                        if (!seen.Add(dedupKey)) continue;

                        diags.Add(new CaDiagnostic
                        {
                            RuleId           = ruleId,
                            Category         = meta.Category ?? "Other",
                            Level            = level,
                            EnabledByDefault = meta.EnabledByDefault,
                            File             = relFile,
                            Line             = line,
                            Member           = member
                        });
                    }
                }
            }
        }

        return (diags, compilerObsolete, true, "");
    }

    private static Dictionary<string, (bool EnabledByDefault, string? Category)> BuildRuleMeta(JsonElement run)
    {
        var map = new Dictionary<string, (bool, string?)>(StringComparer.Ordinal);
        if (!run.TryGetProperty("tool", out var tool) ||
            !tool.TryGetProperty("driver", out var driver) ||
            !driver.TryGetProperty("rules", out var rules))
            return map;

        foreach (var rule in rules.EnumerateArray())
        {
            var id = rule.TryGetProperty("id", out var idEl) ? idEl.GetString() : null;
            if (id is null) continue;

            // enabled: absent ⇒ enabled-by-default (true); present-and-false ⇒ opt-in ("all"-only) rule.
            var enabled = true;
            if (rule.TryGetProperty("defaultConfiguration", out var dc) &&
                dc.TryGetProperty("enabled", out var en) &&
                en.ValueKind is JsonValueKind.False)
                enabled = false;

            string? category = null;
            if (rule.TryGetProperty("properties", out var props) &&
                props.TryGetProperty("category", out var cat))
                category = cat.GetString();

            map[id] = (enabled, category);
        }
        return map;
    }

    private static (string File, int Line, string? Member) ReadLocation(JsonElement result, string sarifRoot)
    {
        if (!result.TryGetProperty("locations", out var locs) || locs.GetArrayLength() == 0)
            return ("", 0, null);

        var loc = locs[0];
        var relFile = "";
        var line = 0;

        if (loc.TryGetProperty("physicalLocation", out var phys))
        {
            if (phys.TryGetProperty("artifactLocation", out var art) &&
                art.TryGetProperty("uri", out var uri))
                relFile = Relativise(UriToPath(uri.GetString()), sarifRoot);

            if (phys.TryGetProperty("region", out var region) &&
                region.TryGetProperty("startLine", out var sl))
                line = sl.GetInt32();
        }

        string? member = null;
        if (loc.TryGetProperty("logicalLocations", out var logs) && logs.GetArrayLength() > 0 &&
            logs[0].TryGetProperty("fullyQualifiedName", out var fqn))
            member = fqn.GetString();

        return (relFile, line, member);
    }

    private static int StartColumn(JsonElement result)
    {
        if (result.TryGetProperty("locations", out var locs) && locs.GetArrayLength() > 0 &&
            locs[0].TryGetProperty("physicalLocation", out var phys) &&
            phys.TryGetProperty("region", out var region) &&
            region.TryGetProperty("startColumn", out var sc))
            return sc.GetInt32();
        return 0;
    }

    // ── Helpers ─────────────────────────────────────────────────────────────

    private static IReadOnlyDictionary<string, int> CountBy(
        IEnumerable<CaDiagnostic> diags, Func<CaDiagnostic, string> key)
        => diags.GroupBy(key, StringComparer.Ordinal)
                .ToDictionary(g => g.Key, g => g.Count(), StringComparer.Ordinal);

    private static readonly string[] SkipDirs = ["bin", "obj", ".git", ".vs", ".idea"];

    private static bool IsUnderSkippedDir(string fullPath, string root)
    {
        var rel = Path.GetRelativePath(root, fullPath);
        return rel.Split(['\\', '/'], StringSplitOptions.RemoveEmptyEntries)
                  .Any(part => SkipDirs.Contains(part, StringComparer.OrdinalIgnoreCase));
    }

    private static string UriToPath(string? uri)
    {
        if (string.IsNullOrEmpty(uri)) return "";
        if (uri.StartsWith("file:///", StringComparison.OrdinalIgnoreCase))
            uri = uri["file:///".Length..];
        else if (uri.StartsWith("file://", StringComparison.OrdinalIgnoreCase))
            uri = uri["file://".Length..];
        return Uri.UnescapeDataString(uri);
    }

    /// <summary>Makes an absolute path solution-relative with forward slashes; falls back to the normalised input when it is not under <paramref name="root"/>.</summary>
    private static string Relativise(string path, string root)
    {
        if (string.IsNullOrEmpty(path)) return "";
        try
        {
            var full = Path.GetFullPath(path.Replace('/', Path.DirectorySeparatorChar));
            var rel = Path.GetRelativePath(Path.GetFullPath(root), full);
            return rel.StartsWith("..", StringComparison.Ordinal) ? Normalise(path) : Normalise(rel);
        }
        catch { return Normalise(path); }
    }

    private static string Normalise(string p) => p.Replace('\\', '/').TrimStart('/');
}
