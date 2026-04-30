using System.Text.Json;
using System.Text.Json.Nodes;
using HybridLens.Core.Models;

namespace HybridLens.CLI.Output;

/// <summary>
/// Emits a SARIF 2.1.0 document compatible with GitHub Code Scanning and
/// Azure DevOps pipeline artifact uploads.
///
/// One SARIF result is produced per static finding.  If an LLM explanation is
/// available the message text is taken from the first model's output and the
/// remediation is stored in <c>properties.remediation</c>.  Results from
/// additional models are stored in <c>properties.llmModels</c>.
///
/// Rule IDs:
///   HL001 — GodClass
///   HL002 — LongMethod
///   HL003 — ObsoleteApiUsage
/// </summary>
public sealed class SarifOutputFormatter : IOutputFormatter
{
    private static readonly JsonSerializerOptions WriteOptions = new() { WriteIndented = true };

    private static readonly IReadOnlyDictionary<AntiPatternType, (string Id, string Name, string Description)> RuleMap =
        new Dictionary<AntiPatternType, (string, string, string)>
        {
            [AntiPatternType.GodClass] = (
                "HL001", "GodClass",
                "A class has too many responsibilities (too many methods, fields, or lines of code)."),
            [AntiPatternType.LongMethod] = (
                "HL002", "LongMethod",
                "A method exceeds the configured line-count or cyclomatic-complexity threshold."),
            [AntiPatternType.ObsoleteApiUsage] = (
                "HL003", "ObsoleteApiUsage",
                "Usage of a deprecated or obsolete API member or namespace."),
        };

    public async Task WriteAsync(
        IReadOnlyList<Finding>    findings,
        IReadOnlyList<LlmFinding> llmFindings,
        FileInfo                  target,
        TextWriter                writer,
        CancellationToken         cancellationToken = default)
    {
        var llmByFinding = llmFindings
            .GroupBy(lf => lf.Finding)
            .ToDictionary(g => g.Key, g => g.ToList());

        var baseDir = Path.GetDirectoryName(target.FullName)!;

        // ── tool.driver.rules ────────────────────────────────────────────────
        var rulesArray = new JsonArray();
        foreach (var type in findings.Select(f => f.Type).Distinct())
        {
            var (id, name, desc) = RuleMap[type];
            rulesArray.Add(new JsonObject
            {
                ["id"]   = id,
                ["name"] = name,
                ["shortDescription"] = new JsonObject { ["text"] = desc },
                ["properties"]       = new JsonObject { ["antiPatternType"] = type.ToString() }
            });
        }

        // ── results ──────────────────────────────────────────────────────────
        var resultsArray = new JsonArray();
        foreach (var f in findings)
        {
            var (ruleId, _, defaultDesc) = RuleMap[f.Type];

            llmByFinding.TryGetValue(f, out var analyses);
            var primary = analyses?.FirstOrDefault();

            var level = f.Severity switch
            {
                Severity.Critical => "error",
                Severity.Warning  => "warning",
                _                 => "note"
            };

            var relPath = Path.GetRelativePath(baseDir, f.FilePath).Replace('\\', '/');

            var result = new JsonObject
            {
                ["ruleId"]  = ruleId,
                ["level"]   = level,
                ["message"] = new JsonObject { ["text"] = primary?.Explanation ?? defaultDesc },
                ["locations"] = new JsonArray
                {
                    new JsonObject
                    {
                        ["physicalLocation"] = new JsonObject
                        {
                            ["artifactLocation"] = new JsonObject
                            {
                                ["uri"]       = relPath,
                                ["uriBaseId"] = "%SRCROOT%"
                            },
                            ["region"] = new JsonObject { ["startLine"] = f.Line }
                        }
                    }
                }
            };

            // Optional properties block
            var props = new JsonObject();
            var hasProps = false;

            if (primary?.Remediation is not null)
            {
                props["remediation"] = primary.Remediation;
                hasProps = true;
            }

            if (f.Metrics.Count > 0)
            {
                var metrics = new JsonObject();
                foreach (var (k, v) in f.Metrics)
                    metrics[k] = v;
                props["metrics"] = metrics;
                hasProps = true;
            }

            // If multiple models ran, store all results
            if (analyses?.Count > 1)
            {
                var modelsArray = new JsonArray();
                foreach (var lf in analyses)
                {
                    modelsArray.Add(new JsonObject
                    {
                        ["model"]       = lf.ModelName,
                        ["explanation"] = lf.Explanation,
                        ["remediation"] = lf.Remediation
                    });
                }
                props["llmModels"] = modelsArray;
                hasProps = true;
            }

            if (hasProps)
                result["properties"] = props;

            resultsArray.Add(result);
        }

        // ── root document ────────────────────────────────────────────────────
        var srcRootUri = new Uri(baseDir.TrimEnd('\\', '/') + "/").AbsoluteUri;

        var doc = new JsonObject
        {
            ["$schema"] = "https://json.schemastore.org/sarif-2.1.0.json",
            ["version"] = "2.1.0",
            ["runs"]    = new JsonArray
            {
                new JsonObject
                {
                    ["tool"] = new JsonObject
                    {
                        ["driver"] = new JsonObject
                        {
                            ["name"]           = "HybridLens",
                            ["version"]        = "1.0.0",
                            ["informationUri"] = "https://github.com/your-org/hybrid-static-llm-pipeline",
                            ["rules"]          = rulesArray
                        }
                    },
                    ["results"] = resultsArray,
                    ["originalUriBaseIds"] = new JsonObject
                    {
                        ["%SRCROOT%"] = new JsonObject { ["uri"] = srcRootUri }
                    }
                }
            }
        };

        using var ms  = new MemoryStream();
        using var jw  = new Utf8JsonWriter(ms, new JsonWriterOptions { Indented = true });
        doc.WriteTo(jw);
        jw.Flush();

        var json = System.Text.Encoding.UTF8.GetString(ms.ToArray());
        await writer.WriteAsync(json.AsMemory(), cancellationToken);
        await writer.WriteLineAsync();
    }
}
