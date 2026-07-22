using System.CommandLine;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using HybridLens.Core.Abstractions;
using HybridLens.Core.Models;
using HybridLens.Pipeline;
using Microsoft.Extensions.DependencyInjection;

namespace HybridLens.CLI.Commands;

/// <summary>
/// Offline whole-solution quality-impact re-score for the iterative arms (agentic, grounded-iterative).
/// Their applied source is preserved in the frozen trajectories (<c>final_source</c>), so the before→after
/// quality delta can be recomputed with NO LLM call and NO re-run of the agent: the pristine corpus is the
/// shared baseline, and each trajectory's final source is materialised into a working copy and scanned with
/// the same <see cref="ISolutionQualityScanner"/> the live <c>--quality-diff</c> path uses. Emits the input
/// verified rows augmented with a <c>quality_delta</c> object, so the output feeds
/// <c>analyse_results.py --verified</c> exactly like a live quality-diff run.
/// </summary>
public static class QualityRescoreCommand
{
    private static readonly string[] SkipDirs = ["bin", "obj", ".git", ".vs", ".idea"];

    private static readonly JsonSerializerOptions Snake = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        WriteIndented = false
    };

    public static Command Build(IServiceProvider services)
    {
        var verifiedOption = new Option<FileInfo>("--verified") { Description = "Agentic/grounded runs JSONL (its final-snapshot rows are augmented).", Required = true };
        var trajOption     = new Option<DirectoryInfo>("--trajectories") { Description = "Trajectory artefact directory for that run (holds final_source).", Required = true };
        var targetOption   = new Option<FileInfo>("--target") { Description = "The corpus solution (Corpus.sln) — its directory is the shared baseline.", Required = true };
        var outOption      = new Option<FileInfo>("--out") { Description = "Output JSONL (verified rows + quality_delta).", Required = true };
        var timeoutOption  = new Option<int>("--build-timeout") { Description = "Per-build timeout in seconds (default 300)." };
        var limitOption    = new Option<int>("--limit") { Description = "Score at most N built finals (0 = all; use a small value to smoke-test)." };

        var command = new Command("quality-rescore",
            "Offline whole-solution quality-impact re-score of an iterative arm from its frozen trajectories (no LLM).")
        {
            verifiedOption, trajOption, targetOption, outOption, timeoutOption, limitOption
        };

        command.SetAction(async (parseResult, ct) =>
        {
            var verified = parseResult.GetValue(verifiedOption)!;
            var trajDir  = parseResult.GetValue(trajOption)!;
            var target   = parseResult.GetValue(targetOption)!;
            var outFile  = parseResult.GetValue(outOption)!;
            var timeout  = parseResult.GetValue(timeoutOption) is > 0 and var t ? t : 300;
            var limit    = parseResult.GetValue(limitOption);

            if (!verified.Exists) { await Console.Error.WriteLineAsync($"error: --verified not found: {verified.FullName}"); return 2; }
            if (!trajDir.Exists)  { await Console.Error.WriteLineAsync($"error: --trajectories not found: {trajDir.FullName}"); return 2; }
            if (!target.Exists)   { await Console.Error.WriteLineAsync($"error: --target not found: {target.FullName}"); return 2; }

            var scanner     = services.GetRequiredService<ISolutionQualityScanner>();
            var corpusRoot  = Path.GetDirectoryName(Path.GetFullPath(target.FullName))!;
            var workingRoot = Path.Combine(Path.GetTempPath(), $"hybridlens-qrescore-{Guid.NewGuid():N}");
            var workingSln  = Path.Combine(workingRoot, Path.GetFileName(target.FullName));

            // Index trajectories by (file basename, run) → (final_source, build_passed_final).
            var traj = new Dictionary<(string, string), (string Src, bool Built)>();
            foreach (var f in Directory.EnumerateFiles(trajDir.FullName, "*.json"))
            {
                try
                {
                    using var d = JsonDocument.Parse(await File.ReadAllTextAsync(f, ct));
                    var r = d.RootElement;
                    var file = r.TryGetProperty("file", out var fe) ? fe.GetString() ?? "" : "";
                    var run  = r.TryGetProperty("run", out var re) ? re.GetRawText() : "";
                    var src  = r.TryGetProperty("final_source", out var se) ? se.GetString() ?? "" : "";
                    var built = r.TryGetProperty("build_passed_final", out var be) && be.ValueKind == JsonValueKind.True;
                    if (file.Length > 0 && src.Length > 0)
                        traj[(Path.GetFileName(file), run)] = (src, built);
                }
                catch { /* skip unreadable artefact */ }
            }

            Console.Error.WriteLine($"quality-rescore: {traj.Count} trajectory final(s) indexed; working copy {workingRoot}");
            outFile.Directory?.Create();
            await using var writer = new StreamWriter(outFile.FullName, append: false, new UTF8Encoding(false)) { AutoFlush = false };

            async Task Emit(JsonObject row) { await writer.WriteLineAsync(row.ToJsonString(Snake)); }

            CopyTree(corpusRoot, workingRoot);
            var scored = 0; var skipped = 0; var emitted = 0;
            try
            {
                Console.Error.WriteLine("  capturing shared pristine baseline (dedicated 8.0-all analyzer build)…");
                var baseline = await scanner.BuildAndScanAsync(workingSln, workingRoot, DotnetBuilder.BuildAsync, timeout, ct);
                Console.Error.WriteLine(
                    $"  baseline: {baseline.SmellTotal} smell(s); CA headline {baseline.CaHeadlineTotal}, all {baseline.CaAllTotal}, " +
                    $"obsolete {baseline.CompilerObsoleteCount} (CA available={baseline.CaAvailable})");

                foreach (var rawLine in File.ReadLines(verified.FullName))
                {
                    ct.ThrowIfCancellationRequested();
                    if (string.IsNullOrWhiteSpace(rawLine)) continue;

                    JsonNode? node;
                    try { node = JsonNode.Parse(rawLine); } catch { continue; }
                    if (node is not JsonObject row) continue;

                    // Only augment iterative-arm final-snapshot rows; everything else passes through untouched.
                    if ((string?)row["agentic_snapshot"] != "final") { await Emit(row); emitted++; continue; }

                    var typeStr  = (string?)row["anti_pattern_type"];
                    var filePath = (string?)row["file_path"];
                    var runNum   = row["run_number"]?.ToJsonString() ?? "";
                    var type     = ParseType(typeStr);
                    if (type is null || filePath is null) { await Emit(row); emitted++; continue; }

                    var baseName = Path.GetFileName(filePath.Replace('\\', '/'));
                    if (!traj.TryGetValue((baseName, runNum), out var tj) || !tj.Built)
                    {
                        await Emit(row); emitted++; skipped++; continue;   // build failed / no final source → no meaningful after
                    }
                    if (limit > 0 && scored >= limit) { await Emit(row); emitted++; continue; }

                    var rel = Path.GetRelativePath(corpusRoot, Path.GetFullPath(filePath));
                    var workingTarget = Path.Combine(workingRoot, rel);
                    var original = await File.ReadAllTextAsync(Path.Combine(corpusRoot, rel), ct);
                    try
                    {
                        Directory.CreateDirectory(Path.GetDirectoryName(workingTarget)!);
                        await File.WriteAllTextAsync(workingTarget, tj.Src, ct);
                        var after = await scanner.BuildAndScanAsync(workingSln, workingRoot, DotnetBuilder.BuildAsync, timeout, ct);
                        var delta = QualityDelta.Between(baseline, after, type.Value, rel.Replace('\\', '/'));
                        row["quality_delta"] = JsonSerializer.SerializeToNode(delta, Snake);
                        scored++;
                        Console.Error.WriteLine(
                            $"  [{scored}] {typeStr} {baseName} run{runNum}: smellΔ={delta.SmellTotalDelta} " +
                            $"ca_headlineΔ={delta.CaHeadlineTotalDelta} ca_allΔ={delta.CaAllTotalDelta} collateral={delta.SmellCollateral}");
                    }
                    finally
                    {
                        try { await File.WriteAllTextAsync(workingTarget, original, ct); } catch { /* best effort */ }
                    }

                    await Emit(row); emitted++;
                }
                await writer.FlushAsync(ct);
            }
            finally
            {
                TryDeleteTree(workingRoot);
            }

            Console.Error.WriteLine($"quality-rescore complete: {emitted} row(s) written, {scored} scored, {skipped} passed through (no built final). → {outFile.FullName}");
            return 0;
        });

        return command;
    }

    private static AntiPatternType? ParseType(string? raw)
    {
        var t = (raw ?? "").Replace(" ", "").Replace("_", "").Replace("-", "").ToLowerInvariant();
        return t switch
        {
            "godclass" => AntiPatternType.GodClass,
            "longmethod" => AntiPatternType.LongMethod,
            "obsoleteapiusage" or "obsoleteapi" => AntiPatternType.ObsoleteApiUsage,
            _ => null
        };
    }

    private static void CopyTree(string src, string dst)
    {
        src = Path.GetFullPath(src);
        Directory.CreateDirectory(dst);
        foreach (var file in Directory.EnumerateFiles(src, "*", SearchOption.AllDirectories))
        {
            var rel = Path.GetRelativePath(src, file);
            if (rel.Split(['\\', '/'], StringSplitOptions.RemoveEmptyEntries).Any(p => SkipDirs.Contains(p, StringComparer.OrdinalIgnoreCase))) continue;
            var tgt = Path.Combine(dst, rel);
            Directory.CreateDirectory(Path.GetDirectoryName(tgt)!);
            File.Copy(file, tgt, overwrite: true);
        }
    }

    private static void TryDeleteTree(string path)
    {
        try { if (Directory.Exists(path)) Directory.Delete(path, recursive: true); } catch { /* temp */ }
    }
}
