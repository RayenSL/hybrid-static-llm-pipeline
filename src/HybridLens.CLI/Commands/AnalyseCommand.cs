using System.CommandLine;
using HybridLens.CLI.Output;
using HybridLens.Core.Abstractions;
using HybridLens.Core.Configuration;
using HybridLens.Core.Models;
using HybridLens.Pipeline;
using HybridLens.StaticAnalysis.Abstractions;
using HybridLens.StaticAnalysis.Detectors;
using HybridLens.StaticAnalysis.Workspace;
using Microsoft.Extensions.DependencyInjection;

namespace HybridLens.CLI.Commands;

public static class AnalyseCommand
{
    /// <summary>Exit code returned when at least one finding at or above the severity threshold is found.</summary>
    public const int ExitFindingsFound = 1;

    public static Command Build(IServiceProvider services)
    {
        var targetOption = new Option<FileInfo?>("--target")
        {
            Description = "Path to the .sln or .csproj to analyse (prompted if omitted)"
        };

        var configOption = new Option<FileInfo?>("--config")
        {
            Description = "Path to a hybridlens.json config file (optional)"
        };

        var formatOption = new Option<OutputFormat>("--format")
        {
            Description = "Output format: console (default), json, sarif"
            // OutputFormat.Console == 0, so it is the implicit default
        };

        var outputOption = new Option<FileInfo?>("--output")
        {
            Description = "Write output to file instead of stdout (useful with --format json|sarif)"
        };

        var severityOption = new Option<Severity>("--severity")
        {
            Description = "Minimum severity sent to LLM and used for the exit-code gate (default: Critical)"
            // Severity.Info == 0, so we need a different default — handled below via explicit check
        };
        // Severity enum: Info=0, Warning=1, Critical=2.  We want Critical as the default.
        // System.CommandLine v3 doesn't have SetDefaultValue; we detect the zero-value below.

        var dryRunOption = new Option<bool>("--dry-run")
        {
            Description = "Run static analysis only; skip the LLM pipeline"
        };

        var contextLevelOption = new Option<string?>("--context-level")
        {
            Description = "Context level: minimal, structural, relational, full, or analyser-only (the baseline arm). " +
                          "Hyphens/underscores/casing are tolerated."
        };

        var runsOption = new Option<int>("--runs")
        {
            Description = "Number of repeated LLM runs per (finding × model) — required for thesis variance analysis (default: 1)"
        };

        var maxFindingsOption = new Option<int>("--max-findings")
        {
            Description = "Cap how many findings (after --severity filter) are sent to the LLM. " +
                          "Selection is deterministic: severity desc, then type, file, line. 0 = no cap (default)."
        };

        var maxFindingsPerTypeOption = new Option<int>("--max-findings-per-type")
        {
            Description = "Stratified cap: at most N findings per anti-pattern type are sent to the LLM. " +
                          "Applied AFTER --severity filter and BEFORE --max-findings. " +
                          "Selection within each type is deterministic: severity desc, then file, line. " +
                          "Set to 10 for the thesis sample (30 instances = 10 × 3 types). 0 = no cap (default)."
        };

        var modelOption = new Option<string>("--model")
        {
            Description = "Comma-separated model keys from Llm.Models to use for generation (e.g. gpt-5.4). " +
                          "Default: all configured models. Use this to run a single evaluated model while " +
                          "keeping the verify-repair applier (e.g. DeepSeek-V4-Pro) configured."
        };

        var command = new Command("analyse", "Run the HybridLens analysis pipeline on a .NET codebase")
        {
            targetOption,
            configOption,
            formatOption,
            outputOption,
            severityOption,
            dryRunOption,
            contextLevelOption,
            runsOption,
            maxFindingsOption,
            maxFindingsPerTypeOption,
            modelOption
        };

        command.SetAction(async (parseResult, cancellationToken) =>
        {
            // Interactive when no tokens beyond the command name itself were parsed.
            // parseResult.Tokens contains all matched tokens (command + options + values).
            // If only the "analyse" command is present (or even less), the user supplied
            // no options → enter interactive mode.
            var suppliedTokenCount = parseResult.Tokens.Count;
            var interactive = suppliedTokenCount <= 1;

            // Diagnostic so we can see what System.CommandLine actually parsed.
            if (Environment.GetEnvironmentVariable("HYBRIDLENS_DEBUG") == "1")
            {
                Console.Error.WriteLine($"[debug] tokens parsed: [{string.Join(", ", parseResult.Tokens.Select(t => t.Value))}]");
                Console.Error.WriteLine($"[debug] interactive   : {interactive}");
            }

            FileInfo?     target;
            OutputFormat  format;
            FileInfo?     outputFile;
            bool          dryRun;
            int           runs;
            int           maxFindings;
            int           maxFindingsPerType;
            ContextLevel? contextLevelOverride = null;
            Severity      minSeverity;
            IReadOnlySet<string>? modelFilter = null;

            if (interactive)
            {
                Console.WriteLine("HybridLens — interactive mode");
                Console.WriteLine("Press Enter at any prompt to accept the [default].");
                Console.WriteLine();

                target = PromptForTarget();
                if (target is null) return ExitFindingsFound;

                dryRun               = PromptYesNo("Dry run (skip LLM pipeline)?", false);
                minSeverity          = PromptEnum("Minimum severity sent to LLM", Severity.Critical);
                contextLevelOverride = PromptEnum<ContextLevel>("Context level for prompts", ContextLevel.Structural);
                runs                 = dryRun ? 1 : PromptInt("Repeated runs per (finding × model)", 1, min: 1);
                maxFindingsPerType   = dryRun ? 0 : PromptInt("Max findings per anti-pattern type (10 for thesis, 0 = no cap)", 0, min: 0);
                maxFindings          = dryRun ? 0 : PromptInt("Max findings total (0 = no cap)", 0, min: 0);
                format               = PromptEnum("Output format", OutputFormat.Console);
                outputFile           = format == OutputFormat.Console
                                        ? null
                                        : PromptOptionalFile("Write output to file (blank = stdout)");
                Console.WriteLine();
            }
            else
            {
                target = parseResult.GetValue(targetOption) ?? PromptForTarget();
                if (target is null) return ExitFindingsFound;

                format      = parseResult.GetValue(formatOption);
                outputFile  = parseResult.GetValue(outputOption);
                dryRun      = parseResult.GetValue(dryRunOption);
                runs        = parseResult.GetValue(runsOption);
                if (runs < 1) runs = 1;
                maxFindings = parseResult.GetValue(maxFindingsOption);
                if (maxFindings < 0) maxFindings = 0;
                maxFindingsPerType = parseResult.GetValue(maxFindingsPerTypeOption);
                if (maxFindingsPerType < 0) maxFindingsPerType = 0;
                var ctxRaw = parseResult.GetValue(contextLevelOption);
                if (!string.IsNullOrWhiteSpace(ctxRaw))
                {
                    contextLevelOverride = ParseContextLevel(ctxRaw);
                    if (contextLevelOverride is null)
                    {
                        await Console.Error.WriteLineAsync(
                            $"error: invalid --context-level '{ctxRaw}'. Use: minimal, structural, relational, full, analyser-only.");
                        return 2;
                    }
                }

                // Severity.Info is the enum zero-value; treat it as "not supplied" and default to Critical.
                var rawSeverity = parseResult.GetValue(severityOption);
                minSeverity = rawSeverity == Severity.Info ? Severity.Critical : rawSeverity;

                var modelRaw = parseResult.GetValue(modelOption);
                if (!string.IsNullOrWhiteSpace(modelRaw))
                    modelFilter = new HashSet<string>(
                        modelRaw.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries),
                        StringComparer.OrdinalIgnoreCase);
            }

            // For structured formats progress goes to stderr so it doesn't pollute the output stream.
            var progress = format == OutputFormat.Console ? Console.Out : Console.Error;

            var loader         = services.GetRequiredService<WorkspaceLoader>();
            var detectorConfig = services.GetRequiredService<DetectorConfig>();
            var contextConfig  = services.GetRequiredService<ContextConfig>();
            var pipeline       = services.GetRequiredService<AnalysisPipeline>();

            // Apply CLI override BEFORE pipeline runs so contextConfig.Level is correct
            // when ContextBuilder reads it (and when AnalysisPipeline records it on each RunRecord).
            if (contextLevelOverride is { } lvl)
                contextConfig.Level = lvl;

            // ── 1. Load workspace ────────────────────────────────────────────
            progress.WriteLine($"Loading: {target.FullName}");
            var compilations = await loader.LoadAsync(target.FullName, cancellationToken);

            foreach (var warning in loader.Warnings)
                progress.WriteLine($"  [warn] {warning}");

            progress.WriteLine($"Loaded {compilations.Count} project(s).{Environment.NewLine}");

            // ── 2. Run detectors ─────────────────────────────────────────────
            var detectors = new IDetector[]
            {
                new LongMethodDetector(detectorConfig.LongMethod),
                new GodClassDetector(detectorConfig.GodClass),
                new ObsoleteApiDetector(detectorConfig.ObsoleteApi)
            };

            var findings = compilations
                .SelectMany(c => detectors.SelectMany(d => d.Detect(c)))
                .ToList();

            if (format == OutputFormat.Console)
                PrintStaticFindings(findings, target, Console.Out);
            else
                PrintStaticFindingsSummary(findings, progress);

            if (findings.Count == 0)
                return 0;

            // ── 3. Run LLM pipeline (skipped on --dry-run) ───────────────────
            IReadOnlyList<LlmFinding> llmFindings = [];

            if (!dryRun)
            {
                // Apply --severity filter and optional caps deterministically.
                // Order within each anti-pattern type: severity desc → file → line, so
                // re-runs hit the exact same subset (essential for thesis reproducibility).
                var eligible = findings
                    .Where(f => f.Severity >= minSeverity)
                    .OrderByDescending(f => f.Severity)
                    .ThenBy(f => f.Type.ToString(), StringComparer.Ordinal)
                    .ThenBy(f => f.FilePath,        StringComparer.Ordinal)
                    .ThenBy(f => f.Line)
                    .ToList();
                var totalEligible = eligible.Count;

                // --max-findings-per-type applies the stratified cap (e.g. 10 per type for the thesis).
                IEnumerable<Finding> stratified = eligible;
                if (maxFindingsPerType > 0)
                {
                    stratified = eligible
                        .GroupBy(f => f.Type)
                        .SelectMany(g => g.Take(maxFindingsPerType));
                }
                var llmInput = stratified.ToList();
                var afterPerType = llmInput.Count;

                // --max-findings is the global cap applied after per-type stratification.
                if (maxFindings > 0 && llmInput.Count > maxFindings)
                    llmInput = llmInput.Take(maxFindings).ToList();

                // Validate --model against configured models before spending an LLM call.
                if (modelFilter is { Count: > 0 })
                {
                    var configured = services.GetRequiredService<IReadOnlyDictionary<string, ILlmAdapter>>();
                    var unknown = modelFilter.Where(m => !configured.ContainsKey(m)).ToList();
                    if (unknown.Count > 0)
                    {
                        await Console.Error.WriteLineAsync(
                            $"error: unknown --model: {string.Join(", ", unknown)}. " +
                            $"Available: {string.Join(", ", configured.Keys)}");
                        return 2;
                    }
                }

                var runStorePath = Path.Combine(
                    "runs",
                    $"{DateTimeOffset.UtcNow:yyyyMMdd-HHmmss}.jsonl");

                var capNote = "";
                if (maxFindingsPerType > 0 && afterPerType < totalEligible)
                    capNote += $" (per-type cap → {afterPerType} from {totalEligible})";
                if (maxFindings > 0 && llmInput.Count < afterPerType)
                    capNote += $" (global cap → {llmInput.Count})";

                var modelsNote = modelFilter is null ? "all" : string.Join("+", modelFilter);
                if (contextConfig.Level == ContextLevel.AnalyserOnly)
                {
                    progress.WriteLine(
                        $"Recording {llmInput.Count} static-analyser baseline finding(s){capNote} " +
                        $"[context: {contextConfig.Level}; no LLM calls]");
                }
                else
                {
                    progress.WriteLine(
                        $"Sending {llmInput.Count} finding(s) to LLM{capNote} " +
                        $"[context: {contextConfig.Level}, runs: {runs}, models: {modelsNote}, prompt: {HybridLens.ContextBuilder.PromptTemplate.Version}]");
                }
                progress.WriteLine($"Run trace: {Path.GetFullPath(runStorePath)}{Environment.NewLine}");

                await using IRunStore runStore = new JsonlRunStore(runStorePath);
                llmFindings = await pipeline.RunAsync(llmInput, minSeverity, runs, runStore, modelFilter, cancellationToken);
            }
            else
            {
                progress.WriteLine("Dry run — LLM pipeline skipped.");
            }

            // ── 4. Write output ──────────────────────────────────────────────
            IOutputFormatter formatter = format switch
            {
                OutputFormat.Json  => new JsonOutputFormatter(),
                OutputFormat.Sarif => new SarifOutputFormatter(),
                OutputFormat.Html  => new HtmlOutputFormatter(),
                _                  => new ConsoleOutputFormatter()
            };

            await using var writer = OpenWriter(outputFile);
            await formatter.WriteAsync(findings, llmFindings, target, writer, cancellationToken);

            // ── 5. Exit code ─────────────────────────────────────────────────
            return findings.Any(f => f.Severity >= minSeverity) ? ExitFindingsFound : 0;
        });

        return command;
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private static TextWriter OpenWriter(FileInfo? outputFile)
    {
        if (outputFile is null)
            return new StreamWriter(Console.OpenStandardOutput(), leaveOpen: true);

        outputFile.Directory?.Create();
        return new StreamWriter(outputFile.FullName, append: false, System.Text.Encoding.UTF8);
    }

    // ── Interactive prompts ──────────────────────────────────────────────────

    /// <summary>Parses a context-level token, tolerating hyphens/underscores/casing (e.g. "analyser-only" → AnalyserOnly). Null = unrecognised.</summary>
    private static ContextLevel? ParseContextLevel(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw)) return null;
        var t = raw.Trim().Replace("-", "").Replace("_", "").ToLowerInvariant();
        return t switch
        {
            "analyseronly" => ContextLevel.AnalyserOnly,
            "minimal"      => ContextLevel.Minimal,
            "structural"   => ContextLevel.Structural,
            "relational"   => ContextLevel.Relational,
            "full"         => ContextLevel.Full,
            _              => null
        };
    }

    private static T PromptEnum<T>(string label, T defaultValue) where T : struct, Enum
    {
        var names = Enum.GetNames<T>();
        while (true)
        {
            Console.WriteLine($"{label} [{string.Join(" / ", names)}] (default: {defaultValue})");
            Console.Write("> ");
            var input = Console.ReadLine()?.Trim();

            if (string.IsNullOrEmpty(input))
                return defaultValue;

            if (Enum.TryParse<T>(input, ignoreCase: true, out var parsed) && Enum.IsDefined(parsed))
                return parsed;

            Console.Error.WriteLine($"  Invalid value. Expected one of: {string.Join(", ", names)}");
        }
    }

    private static int PromptInt(string label, int defaultValue, int min = int.MinValue)
    {
        while (true)
        {
            Console.Write($"{label} (default: {defaultValue}): ");
            var input = Console.ReadLine()?.Trim();

            if (string.IsNullOrEmpty(input))
                return defaultValue;

            if (int.TryParse(input, out var value) && value >= min)
                return value;

            Console.Error.WriteLine($"  Expected an integer >= {min}");
        }
    }

    private static bool PromptYesNo(string label, bool defaultValue)
    {
        var def = defaultValue ? "Y/n" : "y/N";
        while (true)
        {
            Console.Write($"{label} [{def}]: ");
            var input = Console.ReadLine()?.Trim().ToLowerInvariant();

            if (string.IsNullOrEmpty(input)) return defaultValue;
            if (input is "y" or "yes")        return true;
            if (input is "n" or "no")         return false;

            Console.Error.WriteLine("  Please answer y or n.");
        }
    }

    private static FileInfo? PromptOptionalFile(string label)
    {
        Console.Write($"{label}: ");
        var input = Console.ReadLine()?.Trim();
        return string.IsNullOrEmpty(input) ? null : new FileInfo(input);
    }

    private static FileInfo? PromptForTarget()
    {
        while (true)
        {
            Console.Write("Target (.sln or .csproj): ");
            var input = Console.ReadLine()?.Trim();

            if (string.IsNullOrEmpty(input))
            {
                Console.Error.WriteLine("No path entered. Exiting.");
                return null;
            }

            var file = new FileInfo(input);
            if (!file.Exists)
            {
                Console.Error.WriteLine($"  Path not found: {input}");
                continue;
            }

            var ext = file.Extension.ToLowerInvariant();
            if (ext is not ".sln" and not ".csproj")
            {
                Console.Error.WriteLine($"  Expected a .sln or .csproj file, got '{ext}'");
                continue;
            }

            return file;
        }
    }

    /// <summary>Full table — used for console format (printed before LLM runs).</summary>
    private static void PrintStaticFindings(List<Finding> findings, FileInfo target, TextWriter writer)
    {
        if (findings.Count == 0)
        {
            writer.WriteLine("No findings.");
            return;
        }

        var baseDir = Path.GetDirectoryName(target.FullName)!;

        foreach (var group in findings.GroupBy(f => f.Type))
        {
            var sorted = group.OrderByDescending(f => f.Severity).ThenBy(f => f.SymbolName).ToList();
            writer.WriteLine($"── {group.Key} ({sorted.Count} finding(s)) ──");
            writer.WriteLine($"  {"Severity",-10}  {"Symbol",-60}  File");
            writer.WriteLine(new string('-', 120));

            foreach (var f in sorted)
            {
                var path = Path.GetRelativePath(baseDir, f.FilePath);
                writer.WriteLine($"  {f.Severity,-10}  {f.SymbolName,-60}  {path}:{f.Line}");
            }

            writer.WriteLine();
        }

        writer.WriteLine($"Total: {findings.Count} finding(s) " +
            $"({findings.Count(f => f.Severity == Severity.Critical)} critical, " +
            $"{findings.Count(f => f.Severity == Severity.Warning)} warnings){Environment.NewLine}");
    }

    /// <summary>One-line summary — used for json/sarif format progress (written to stderr).</summary>
    private static void PrintStaticFindingsSummary(List<Finding> findings, TextWriter progress)
    {
        if (findings.Count == 0)
        {
            progress.WriteLine("No findings.");
            return;
        }

        progress.WriteLine(
            $"Found {findings.Count} finding(s): " +
            $"{findings.Count(f => f.Severity == Severity.Critical)} critical, " +
            $"{findings.Count(f => f.Severity == Severity.Warning)} warnings.{Environment.NewLine}");
    }
}
