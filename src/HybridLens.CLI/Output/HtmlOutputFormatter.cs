using System.Net;
using System.Text;
using HybridLens.Core.Models;

namespace HybridLens.CLI.Output;

/// <summary>
/// Produces a single self-contained HTML report — no external CDN dependencies.
/// Designed for a tech lead reviewing a PR: summary cards, two bar charts,
/// filterable/expandable finding cards with side-by-side LLM model outputs,
/// and a per-file breakdown table.
/// </summary>
public sealed class HtmlOutputFormatter : IOutputFormatter
{
    public async Task WriteAsync(
        IReadOnlyList<Finding>    findings,
        IReadOnlyList<LlmFinding> llmFindings,
        FileInfo                  target,
        TextWriter                writer,
        CancellationToken         cancellationToken = default)
    {
        var html = Render(findings, llmFindings, target);
        await writer.WriteAsync(html.AsMemory(), cancellationToken);
    }

    // ── HTML-encode helper ────────────────────────────────────────────────────
    private static string H(string? s) => WebUtility.HtmlEncode(s ?? string.Empty);

    // ── Main render ───────────────────────────────────────────────────────────
    private static string Render(
        IReadOnlyList<Finding>    findings,
        IReadOnlyList<LlmFinding> llmFindings,
        FileInfo                  target)
    {
        var baseDir     = Path.GetDirectoryName(target.FullName)!;
        var projectName = Path.GetFileNameWithoutExtension(target.Name);
        var analysedAt  = DateTimeOffset.UtcNow;

        // Group LLM results by finding; sort models alphabetically for determinism
        var llmIndex = llmFindings
            .GroupBy(lf => lf.Finding)
            .ToDictionary(g => g.Key, g => g.OrderBy(x => x.ModelName).ToList());

        var critical    = findings.Count(f => f.Severity == Severity.Critical);
        var warning     = findings.Count(f => f.Severity == Severity.Warning);
        var llmAnalysed = llmIndex.Count;
        var modelCount  = llmFindings.Select(lf => lf.ModelName).Distinct().Count();

        // Sort: Critical first → type → symbol name
        var sorted = findings
            .OrderByDescending(f => f.Severity)
            .ThenBy(f => f.Type.ToString())
            .ThenBy(f => f.SymbolName)
            .Select((f, i) => (Finding: f, Index: i))
            .ToList();

        var sb = new StringBuilder(128 * 1024);

        sb.Append($"""
            <!DOCTYPE html>
            <html lang="en">
            <head>
              <meta charset="UTF-8">
              <meta name="viewport" content="width=device-width, initial-scale=1.0">
              <title>HybridLens — {H(projectName)}</title>
              <style>
            {Css}
              </style>
            </head>
            <body>
            <div class="container">
            """);

        sb.Append(RenderHeader(projectName, analysedAt, critical, warning));
        sb.Append(RenderSummaryCards(findings.Count, critical, warning, llmAnalysed, modelCount));
        sb.Append(RenderCharts(findings));
        sb.Append(RenderFindingsSection(sorted, llmIndex, baseDir, findings.Count));
        sb.Append(RenderFileBreakdown(findings, baseDir));

        sb.Append($"""
            </div>
            <script>
            {Js}
            </script>
            </body>
            </html>
            """);

        return sb.ToString();
    }

    // ── Section renderers ─────────────────────────────────────────────────────

    private static string RenderHeader(
        string projectName, DateTimeOffset analysedAt, int critical, int warning)
    {
        var badges = new StringBuilder();
        if (critical > 0) badges.Append($"<span class=\"badge badge-critical\">{critical} Critical</span>");
        if (warning  > 0) badges.Append($"<span class=\"badge badge-warning\">{warning} Warning</span>");
        if (critical == 0 && warning == 0)
            badges.Append("<span class=\"badge badge-success\">✓ No findings</span>");

        return $"""
            <header class="page-header">
              <div>
                <div class="header-logo">HybridLens</div>
                <div class="project-name">{H(projectName)}</div>
                <div class="meta">Analysed {H(analysedAt.ToString("dd MMM yyyy, HH:mm"))} UTC</div>
              </div>
              <div class="header-badges">{badges}</div>
            </header>
            """;
    }

    private static string RenderSummaryCards(
        int total, int critical, int warning, int llmAnalysed, int modelCount)
    {
        return $"""
            <div class="summary-grid">
              {StatCard("Total Findings", total, "")}
              {StatCard("Critical",       critical,   "critical")}
              {StatCard("Warnings",       warning,    "warning")}
              {StatCard("LLM Analysed",  llmAnalysed, "")}
              {StatCard("Models",         modelCount,  "models")}
            </div>
            """;

        static string StatCard(string label, int value, string css) =>
            $"""<div class="stat-card {css}"><div class="stat-number">{value}</div><div class="stat-label">{H(label)}</div></div>""";
    }

    private static string RenderCharts(IReadOnlyList<Finding> findings)
    {
        // By type
        var types = new[]
        {
            (Label: "God Class",    Key: AntiPatternType.GodClass,         Css: "bar-godclass"),
            (Label: "Long Method",  Key: AntiPatternType.LongMethod,       Css: "bar-longmethod"),
            (Label: "Obsolete API", Key: AntiPatternType.ObsoleteApiUsage, Css: "bar-obsolete"),
        };
        var maxByType = types.Max(t => findings.Count(f => f.Type == t.Key));

        var typeChart = new StringBuilder();
        foreach (var (label, key, css) in types)
        {
            var count = findings.Count(f => f.Type == key);
            typeChart.Append(ChartRow(label, count, maxByType, css, "f-type", key.ToString()));
        }

        // By severity
        var sev = new[]
        {
            (Label: "Critical", Count: findings.Count(f => f.Severity == Severity.Critical), Css: "bar-critical"),
            (Label: "Warning",  Count: findings.Count(f => f.Severity == Severity.Warning),  Css: "bar-warning"),
            (Label: "Info",     Count: findings.Count(f => f.Severity == Severity.Info),     Css: "bar-info"),
        };
        var maxBySev = sev.Max(s => s.Count);

        var sevChart = new StringBuilder();
        foreach (var (label, count, css) in sev)
            sevChart.Append(ChartRow(label, count, maxBySev, css, "f-severity", label));

        return $"""
            <div class="charts-grid">
              <div class="card">
                <div class="card-title">By Type</div>
                {typeChart}
              </div>
              <div class="card">
                <div class="card-title">By Severity</div>
                {sevChart}
              </div>
            </div>
            """;

        // filterField / filterValue: when set the row is clickable and calls chartFilter()
        static string ChartRow(string label, int value, int max, string barCss,
                               string? filterField = null, string? filterValue = null)
        {
            var pct       = max > 0 ? (int)Math.Round(value * 100.0 / max) : 0;
            var clickable = filterField is not null && value > 0;
            var extra     = clickable
                ? $" class=\"chart-row clickable\" onclick=\"chartFilter('{filterField}','{filterValue}')\" title=\"Filter by {H(label)}\""
                : " class=\"chart-row\"";
            return $"""
                <div{extra}>
                  <span class="chart-label">{H(label)}</span>
                  <div class="chart-track"><div class="chart-bar {barCss}" style="width:{pct}%"></div></div>
                  <span class="chart-value">{value}</span>
                </div>
                """;
        }
    }

    private static string RenderFindingsSection(
        IReadOnlyList<(Finding Finding, int Index)> sorted,
        Dictionary<Finding, List<LlmFinding>> llmIndex,
        string baseDir,
        int total)
    {
        if (total == 0)
        {
            return """
                <div class="findings-section">
                  <div class="section-header"><span class="section-title">Findings</span></div>
                  <div class="empty-state">
                    <div class="empty-icon">✓</div>
                    <div class="empty-text">No findings detected.</div>
                  </div>
                </div>
                """;
        }

        // Unique type options for the type filter
        var typeOptions = sorted
            .Select(x => x.Finding.Type)
            .Distinct()
            .OrderBy(t => t.ToString())
            .Select(t => $"<option value=\"{H(t.ToString())}\">{H(TypeLabel(t))}</option>");

        var cards = new StringBuilder();
        foreach (var (finding, idx) in sorted)
        {
            llmIndex.TryGetValue(finding, out var llmList);
            cards.Append(RenderFindingCard(finding, idx, llmList, baseDir));
        }

        return $"""
            <div class="findings-section">
              <div class="section-header">
                <span class="section-title">Findings
                  <span class="findings-meta" id="visible-count">{total} finding{(total == 1 ? "" : "s")}</span>
                </span>
                <div class="section-controls">
                  <select class="filter-control" id="f-severity">
                    <option value="">All Severities</option>
                    <option value="Critical">Critical</option>
                    <option value="Warning">Warning</option>
                    <option value="Info">Info</option>
                  </select>
                  <select class="filter-control" id="f-type">
                    <option value="">All Types</option>
                    {string.Join("", typeOptions)}
                  </select>
                  <input class="filter-control" id="f-search" type="text" placeholder="Search symbol or file…">
                  <button class="expand-all-btn" onclick="toggleAll()">Expand All</button>
                </div>
              </div>
              <div id="findings-list">
                {cards}
              </div>
            </div>
            """;
    }

    private static string RenderFindingCard(
        Finding finding, int idx, List<LlmFinding>? llmList, string baseDir)
    {
        var sevCss  = finding.Severity.ToString();
        var relPath = Path.GetRelativePath(baseDir, finding.FilePath).Replace('\\', '/');
        var typeBadgeCss = finding.Type switch
        {
            AntiPatternType.GodClass         => "badge-godclass",
            AntiPatternType.LongMethod       => "badge-longmethod",
            AntiPatternType.ObsoleteApiUsage => "badge-obsolete",
            _                                => ""
        };

        var id = $"f{idx}";

        // Metrics pills
        var metricsSb = new StringBuilder();
        if (finding.Metrics.Count > 0)
        {
            metricsSb.Append("<div class=\"metrics-row\">");
            foreach (var (key, value) in finding.Metrics.Where(m => !m.Key.StartsWith("Max", StringComparison.Ordinal)))
            {
                var exceeded = finding.Metrics.TryGetValue("Max" + key, out var max) && value > max;
                var pill     = exceeded ? "metric-pill exceeded" : "metric-pill";
                var maxLabel = exceeded ? $" / max {max:0}" : "";
                metricsSb.Append($"<span class=\"{pill}\">{H(key)}: {value:0}{H(maxLabel)}</span>");
            }
            metricsSb.Append("</div>");
        }

        // Code snippet (collapsed by default)
        var snippetSb = new StringBuilder();
        if (finding.Snippet is { Length: > 0 } snippet)
        {
            snippetSb.Append($"""
                <div class="snippet-toggle" onclick="toggleSnippet('{id}')">
                  <span class="snippet-toggle-icon" id="sicon-{id}">▶</span> Show code
                </div>
                <div class="snippet-block" id="snippet-{id}">
                  {CodeBlock(snippet, $"sc-{id}", finding.Line)}
                </div>
                """);
        }

        // LLM analysis
        var llmSb = new StringBuilder();
        if (llmList is { Count: > 0 })
        {
            llmSb.Append($"""<div class="llm-heading">LLM Analysis</div><div class="llm-grid" style="--model-count:{llmList.Count}">""");
            foreach (var lf in llmList)
            {
                llmSb.Append($"""
                    <div class="llm-model-card">
                      <div class="llm-model-name">{H(lf.ModelName)}</div>
                      <div class="llm-label">Explanation</div>
                      <div class="llm-text">{H(lf.Explanation)}</div>
                      <div class="llm-label">Remediation</div>
                      <div class="llm-remed-wrap">{CodeBlock(lf.Remediation, $"rc-{id}-{llmList!.IndexOf(lf)}")}</div>
                    </div>
                    """);
            }
            llmSb.Append("</div>");
        }
        else
        {
            llmSb.Append("<div class=\"no-llm\">No LLM analysis available for this finding.</div>");
        }

        return $"""
            <div class="finding-card sev-{H(sevCss)}"
                 data-id="{id}"
                 data-severity="{H(sevCss)}"
                 data-type="{H(finding.Type.ToString())}"
                 data-symbol="{H(finding.SymbolName.ToLowerInvariant())}"
                 data-file="{H(relPath.ToLowerInvariant())}">
              <div class="finding-header" onclick="toggleCard('{id}')">
                <span class="toggle-icon" id="icon-{id}">▶</span>
                <span class="badge badge-{H(sevCss.ToLowerInvariant())}">{H(sevCss)}</span>
                <span class="badge {typeBadgeCss}">{H(TypeLabel(finding.Type))}</span>
                <div class="finding-title">
                  <div class="finding-symbol" data-orig="{H(finding.SymbolName)}">{H(finding.SymbolName)}</div>
                  <div class="finding-location" data-orig="{H($"{relPath}:{finding.Line}")}">{H(relPath)}:{finding.Line}</div>
                </div>
              </div>
              <div class="finding-body" id="body-{id}">
                {metricsSb}
                {snippetSb}
                {llmSb}
              </div>
            </div>
            """;
    }

    private static string RenderFileBreakdown(IReadOnlyList<Finding> findings, string baseDir)
    {
        if (findings.Count == 0) return "";

        var byFile = findings
            .GroupBy(f => Path.GetRelativePath(baseDir, f.FilePath).Replace('\\', '/'))
            .Select(g => (
                File:     g.Key,
                Critical: g.Count(f => f.Severity == Severity.Critical),
                Warning:  g.Count(f => f.Severity == Severity.Warning),
                Total:    g.Count()))
            .OrderByDescending(r => r.Total)
            .ThenByDescending(r => r.Critical)
            .ToList();

        var rows = new StringBuilder();
        foreach (var (file, crit, warn, tot) in byFile)
        {
            var fileLower = file.Replace('\\', '/').ToLowerInvariant();
            rows.Append($"""
                <tr class="file-row" onclick="jumpToFile('{H(fileLower)}')" title="Jump to first finding in this file">
                  <td class="file-path">{H(file)}</td>
                  <td class="count-c">{(crit > 0 ? crit.ToString() : "—")}</td>
                  <td class="count-w">{(warn > 0 ? warn.ToString() : "—")}</td>
                  <td class="count-total">{tot}</td>
                </tr>
                """);
        }

        return $"""
            <div class="card file-breakdown">
              <div class="card-title">By File</div>
              <table class="file-table">
                <thead>
                  <tr>
                    <th>File</th>
                    <th class="th-right">Critical</th>
                    <th class="th-right">Warning</th>
                    <th class="th-right">Total</th>
                  </tr>
                </thead>
                <tbody>{rows}</tbody>
              </table>
            </div>
            """;
    }

    /// <summary>
    /// Renders a dark-background code block with a hover-reveal copy button.
    /// When <paramref name="startLine"/> is provided each line gets a line-number
    /// gutter via CSS <c>::before { content: attr(data-ln) }</c>.
    /// </summary>
    private static string CodeBlock(string content, string copyId, int? startLine = null)
    {
        var lines   = content.TrimEnd().Split('\n');
        var codeSb  = new StringBuilder(lines.Length * 80);
        var haLines = startLine.HasValue;

        for (var i = 0; i < lines.Length; i++)
        {
            var ln = haLines ? $" data-ln=\"{startLine!.Value + i}\"" : "";
            codeSb.Append($"<span class=\"line\"{ln}>{H(lines[i].TrimEnd())}</span>");
        }

        var preCss = haLines ? "code-pre has-lines" : "code-pre";
        return $"""
            <div class="code-wrap">
              <button class="copy-btn" onclick="copyCode(this)" title="Copy to clipboard">Copy</button>
              <pre class="{preCss}" id="{copyId}"><code>{codeSb}</code></pre>
            </div>
            """;
    }

    private static string TypeLabel(AntiPatternType t) => t switch
    {
        AntiPatternType.GodClass         => "God Class",
        AntiPatternType.LongMethod       => "Long Method",
        AntiPatternType.ObsoleteApiUsage => "Obsolete API",
        _                                => t.ToString()
    };

    // ── Styles ────────────────────────────────────────────────────────────────
    private const string Css = """
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        body {
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
          background: #f3f4f6; color: #111827; font-size: 14px; line-height: 1.5;
        }
        .container { max-width: 1600px; margin: 0 auto; padding: 28px 24px; }

        /* Header */
        .page-header {
          background: #fff; border: 1px solid #e5e7eb; border-radius: 10px;
          padding: 22px 24px; margin-bottom: 14px;
          display: flex; justify-content: space-between; align-items: flex-start;
        }
        .header-logo { font-size: 11px; font-weight: 700; color: #6366f1; letter-spacing: .08em; text-transform: uppercase; margin-bottom: 4px; }
        .project-name { font-size: 20px; font-weight: 700; color: #111827; }
        .meta { font-size: 12px; color: #9ca3af; margin-top: 3px; }
        .header-badges { display: flex; gap: 8px; align-items: center; flex-shrink: 0; margin-top: 4px; }

        /* Badges */
        .badge {
          display: inline-flex; align-items: center;
          padding: 3px 10px; border-radius: 9999px;
          font-size: 11px; font-weight: 600;
          text-transform: uppercase; letter-spacing: .06em; white-space: nowrap;
        }
        .badge-critical  { background: #fee2e2; color: #b91c1c; }
        .badge-warning   { background: #fef3c7; color: #b45309; }
        .badge-info      { background: #dbeafe; color: #1d4ed8; }
        .badge-success   { background: #d1fae5; color: #065f46; }
        .badge-godclass    { background: #ede9fe; color: #6d28d9; }
        .badge-longmethod  { background: #cffafe; color: #0e7490; }
        .badge-obsolete    { background: #d1fae5; color: #065f46; }

        /* Summary grid */
        .summary-grid {
          display: grid; grid-template-columns: repeat(5, 1fr);
          gap: 12px; margin-bottom: 14px;
        }
        .stat-card {
          background: #fff; border: 1px solid #e5e7eb; border-radius: 10px;
          padding: 16px; text-align: center;
        }
        .stat-number { font-size: 30px; font-weight: 700; color: #111827; }
        .stat-label  { font-size: 11px; color: #9ca3af; margin-top: 3px; text-transform: uppercase; letter-spacing: .06em; }
        .stat-card.critical .stat-number { color: #dc2626; }
        .stat-card.warning  .stat-number { color: #d97706; }
        .stat-card.models   .stat-number { color: #6366f1; }

        /* Charts */
        .charts-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 14px; }
        .card { background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 20px; margin-bottom: 14px; }
        .card-title { font-size: 11px; font-weight: 600; color: #9ca3af; text-transform: uppercase; letter-spacing: .06em; margin-bottom: 14px; }
        .chart-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
        .chart-label { font-size: 12px; color: #374151; min-width: 100px; text-align: right; }
        .chart-track { flex: 1; background: #f3f4f6; border-radius: 3px; height: 16px; }
        .chart-bar   { height: 100%; border-radius: 3px; min-width: 2px; transition: width .4s ease; }
        .chart-value { font-size: 12px; font-weight: 600; color: #374151; min-width: 24px; text-align: right; }
        .bar-critical   { background: #dc2626; }
        .bar-warning    { background: #d97706; }
        .bar-info       { background: #2563eb; }
        .bar-godclass   { background: #7c3aed; }
        .bar-longmethod { background: #0891b2; }
        .bar-obsolete   { background: #059669; }

        /* Findings section */
        .findings-section { margin-bottom: 14px; }
        .section-header {
          display: flex; justify-content: space-between; align-items: center;
          margin-bottom: 10px; flex-wrap: wrap; gap: 8px;
        }
        .section-title { font-size: 15px; font-weight: 600; color: #111827; display: flex; align-items: baseline; gap: 8px; }
        .findings-meta { font-size: 12px; color: #9ca3af; font-weight: 400; }
        .section-controls { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
        .filter-control {
          padding: 5px 10px; border: 1px solid #d1d5db; border-radius: 6px;
          font-size: 12px; color: #374151; background: #fff; outline: none; height: 30px;
        }
        .filter-control:focus { border-color: #6366f1; box-shadow: 0 0 0 2px rgba(99,102,241,.1); }
        input.filter-control { width: 200px; }
        .expand-all-btn {
          padding: 5px 12px; border: 1px solid #d1d5db; border-radius: 6px;
          font-size: 12px; background: #fff; color: #374151; cursor: pointer; height: 30px;
        }
        .expand-all-btn:hover { background: #f9fafb; }

        /* Finding cards */
        .finding-card {
          background: #fff; border: 1px solid #e5e7eb;
          border-radius: 8px; margin-bottom: 6px; overflow: hidden;
        }
        .finding-card.sev-Critical { border-left: 3px solid #dc2626; }
        .finding-card.sev-Warning  { border-left: 3px solid #d97706; }
        .finding-card.sev-Info     { border-left: 3px solid #2563eb; }
        .finding-header {
          display: flex; align-items: center; gap: 10px;
          padding: 10px 14px; cursor: pointer; user-select: none;
        }
        .finding-header:hover { background: #f9fafb; }
        .toggle-icon { font-size: 9px; color: #9ca3af; flex-shrink: 0; width: 10px; }
        .finding-title { flex: 1; min-width: 0; }
        .finding-symbol { font-size: 13px; font-weight: 600; color: #111827; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .finding-location { font-size: 11px; color: #9ca3af; font-family: 'SF Mono', Consolas, monospace; margin-top: 1px; }
        .finding-body { border-top: 1px solid #f3f4f6; padding: 14px 16px; display: none; }

        /* Metrics */
        .metrics-row { display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 14px; }
        .metric-pill {
          background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 4px;
          padding: 2px 7px; font-size: 11px; color: #374151;
          font-family: 'SF Mono', Consolas, monospace;
        }
        .metric-pill.exceeded { border-color: #fca5a5; background: #fff1f2; color: #b91c1c; }

        /* Code snippet */
        .snippet-toggle {
          display: inline-flex; align-items: center; gap: 6px;
          font-size: 11px; font-weight: 600; color: #6366f1;
          cursor: pointer; user-select: none; margin-bottom: 8px;
        }
        .snippet-toggle:hover { color: #4f46e5; }
        .snippet-toggle-icon { font-size: 9px; }
        .snippet-block { display: none; margin-bottom: 14px; }
        .code-pre {
          background: #1e1e2e; color: #cdd6f4;
          border-radius: 6px; padding: 14px 16px;
          font-family: 'SF Mono', Consolas, 'Cascadia Code', monospace;
          font-size: 12px; line-height: 1.6;
          overflow-x: auto; white-space: pre;
          border: 1px solid #313244;
        }

        /* LLM analysis */
        .llm-heading { font-size: 11px; font-weight: 600; color: #9ca3af; text-transform: uppercase; letter-spacing: .06em; margin-bottom: 10px; }
        /*
         * LLM grid — CSS subgrid alignment
         *
         * The parent defines 5 explicit row tracks (one per section of a model response:
         * name, explanation label, explanation text, remediation label, remediation text).
         * Each .llm-model-card spans all 5 tracks with grid-row: 1 / -1 and mirrors those
         * tracks internally via subgrid, so the explanation and remediation blocks are
         * always at the same vertical position across every model column.
         */
        .llm-grid {
          display: grid;
          grid-template-columns: repeat(var(--model-count, 1), 1fr);
          grid-template-rows: auto auto auto auto auto;
          column-gap: 10px;
        }
        .llm-model-card {
          grid-row: 1 / -1;
          display: grid;
          grid-template-rows: subgrid;
          background: #f9fafb;
          border: 1px solid #e5e7eb;
          border-radius: 6px;
          overflow: hidden;
        }
        .llm-model-name {
          font-size: 11px; font-weight: 600; color: #6b7280;
          text-transform: uppercase; letter-spacing: .05em;
          padding: 10px 12px 8px;
          border-bottom: 1px solid #e5e7eb;
        }
        .llm-label {
          font-size: 10px; font-weight: 600; color: #9ca3af;
          text-transform: uppercase; letter-spacing: .06em;
          padding: 10px 12px 3px;
          align-self: end;
        }
        .llm-text      { font-size: 12px; color: #374151; line-height: 1.65; white-space: pre-wrap; padding: 3px 12px 10px; }
        .llm-remed-code { margin: 3px 12px 10px; font-size: 12px; }
        .no-llm { font-size: 12px; color: #9ca3af; font-style: italic; }

        /* File breakdown */
        .file-breakdown { margin-bottom: 0; }
        .file-table { width: 100%; border-collapse: collapse; }
        .file-table th {
          text-align: left; padding: 7px 12px;
          font-size: 11px; font-weight: 600; color: #9ca3af;
          text-transform: uppercase; letter-spacing: .06em;
          border-bottom: 2px solid #e5e7eb;
        }
        .file-table td { padding: 7px 12px; border-bottom: 1px solid #f3f4f6; }
        .file-table tr:last-child td { border-bottom: none; }
        .file-table tr:hover td { background: #f9fafb; }
        .file-path { font-family: 'SF Mono', Consolas, monospace; font-size: 12px; color: #374151; }
        .th-right { text-align: right; }
        .count-c     { color: #dc2626; font-weight: 600; text-align: right; }
        .count-w     { color: #d97706; font-weight: 600; text-align: right; }
        .count-total { font-weight: 700; text-align: right; }

        /* Empty state */
        .empty-state { text-align: center; padding: 40px; color: #9ca3af; }
        .empty-icon { font-size: 32px; margin-bottom: 8px; }
        .empty-text { font-size: 14px; }

        /* ── Sticky filter bar ─────────────────────────────────────────────── */
        .section-header {
          position: sticky; top: 0; z-index: 20;
          background: #f3f4f6;
          padding: 8px 0; margin-bottom: 2px;
        }

        /* ── Clickable chart rows ──────────────────────────────────────────── */
        .chart-row.clickable { cursor: pointer; border-radius: 4px; padding: 2px 4px; margin: 0 -4px 4px; transition: background .1s; }
        .chart-row.clickable:hover { background: #ede9fe; }
        .chart-row.clickable:hover .chart-label { color: #6366f1; }

        /* ── Code block with copy button ───────────────────────────────────── */
        .code-wrap { position: relative; }
        .copy-btn {
          position: absolute; top: 8px; right: 8px;
          padding: 3px 8px; background: #313244; color: #cdd6f4;
          border: 1px solid #45475a; border-radius: 4px;
          font-size: 11px; cursor: pointer;
          opacity: 0; transition: opacity .15s;
          font-family: inherit;
        }
        .code-wrap:hover .copy-btn { opacity: 1; }
        .copy-btn:hover { background: #45475a; }

        /* ── Line numbers ──────────────────────────────────────────────────── */
        .line { display: block; }
        .code-pre.has-lines .line::before {
          content: attr(data-ln);
          display: inline-block; width: 2.5em;
          padding-right: .75em; margin-right: 1em;
          color: #6c7086; border-right: 1px solid #313244;
          text-align: right;
          user-select: none; -webkit-user-select: none;
        }

        /* ── Search highlight ──────────────────────────────────────────────── */
        mark.hl { background: #fef08a; color: #111827; border-radius: 2px; padding: 0 1px; }

        /* ── File breakdown jump ───────────────────────────────────────────── */
        .file-table tr.file-row { cursor: pointer; }

        /* ── LLM remediation wrapper ───────────────────────────────────────── */
        .llm-remed-wrap { padding: 3px 12px 10px; }
        .llm-remed-wrap .copy-btn { top: 4px; right: 4px; }

        /* ── Responsive ────────────────────────────────────────────────────── */
        @media (max-width: 800px) {
          .summary-grid { grid-template-columns: repeat(3, 1fr); }
          .charts-grid  { grid-template-columns: 1fr; }
          .llm-grid     { grid-template-columns: 1fr !important; grid-template-rows: none; }
          .llm-model-card { grid-row: auto; grid-template-rows: none; display: block; padding: 12px; margin-bottom: 8px; }
          .section-header { position: static; }
        }
        @media (max-width: 500px) {
          .summary-grid { grid-template-columns: repeat(2, 1fr); }
        }

        /* ── Print ─────────────────────────────────────────────────────────── */
        @media print {
          body { background: #fff; font-size: 11px; }
          .container { max-width: none; padding: 0; }
          .section-header { position: static; background: transparent; }
          .section-controls, .expand-all-btn,
          .snippet-toggle, .copy-btn { display: none !important; }
          .finding-body  { display: block !important; }
          .snippet-block { display: block !important; }
          .finding-card  { break-inside: avoid; margin-bottom: 16px; }
          .charts-grid   { display: none; }
          .llm-grid { grid-template-columns: 1fr !important; grid-template-rows: none !important; }
          .llm-model-card { grid-row: auto !important; display: block !important; margin-bottom: 8px; }
          .code-pre {
            background: #f8f9fa !important; color: #212529 !important;
            border: 1px solid #dee2e6 !important;
          }
          .code-pre.has-lines .line::before { color: #6c757d !important; border-right-color: #dee2e6 !important; }
        }
        """;

    // ── Script ────────────────────────────────────────────────────────────────
    private const string Js = """
        var _allOpen = false;

        // ── Card / snippet toggles ─────────────────────────────────────────
        function toggleCard(id) {
          var body = document.getElementById('body-' + id);
          var icon = document.getElementById('icon-' + id);
          var open = body.style.display === 'block';
          body.style.display = open ? 'none' : 'block';
          icon.textContent   = open ? '▶' : '▼';
        }

        function toggleSnippet(id) {
          var block  = document.getElementById('snippet-' + id);
          var icon   = document.getElementById('sicon-'   + id);
          var toggle = block.previousElementSibling;
          var open   = block.style.display === 'block';
          block.style.display  = open ? 'none' : 'block';
          icon.textContent     = open ? '▶' : '▼';
          // update the text node after the icon span
          toggle.childNodes[1].textContent = open ? ' Show code' : ' Hide code';
        }

        function toggleAll() {
          _allOpen = !_allOpen;
          document.querySelectorAll('.finding-card').forEach(function(card) {
            if (card.style.display === 'none') return;
            var id   = card.dataset.id;
            var body = document.getElementById('body-' + id);
            var icon = document.getElementById('icon-' + id);
            body.style.display = _allOpen ? 'block' : 'none';
            icon.textContent   = _allOpen ? '▼' : '▶';
          });
          document.querySelector('.expand-all-btn').textContent = _allOpen ? 'Collapse All' : 'Expand All';
        }

        // ── Copy to clipboard ──────────────────────────────────────────────
        function copyCode(btn) {
          var code = btn.nextElementSibling.querySelector('code');
          var text = code.textContent.trimEnd();
          function done() {
            var orig = btn.textContent;
            btn.textContent = '✓ Copied';
            setTimeout(function() { btn.textContent = orig; }, 2000);
          }
          if (navigator.clipboard) {
            navigator.clipboard.writeText(text).then(done).catch(function() { fallbackCopy(text); done(); });
          } else { fallbackCopy(text); done(); }
        }
        function fallbackCopy(text) {
          var ta = document.createElement('textarea');
          ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
          document.body.appendChild(ta); ta.focus(); ta.select();
          try { document.execCommand('copy'); } catch(e) {}
          document.body.removeChild(ta);
        }

        // ── Search highlight helpers ───────────────────────────────────────
        function escHtml(s) {
          return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
        }
        function hlText(text, term) {
          if (!term) return escHtml(text);
          var res = '', low = text.toLowerCase(), pos = 0, idx;
          while ((idx = low.indexOf(term, pos)) !== -1) {
            res += escHtml(text.slice(pos, idx));
            res += '<mark class="hl">' + escHtml(text.slice(idx, idx + term.length)) + '</mark>';
            pos  = idx + term.length;
          }
          return res + escHtml(text.slice(pos));
        }

        // ── Main filter function ───────────────────────────────────────────
        function applyFilters() {
          var sev    = document.getElementById('f-severity').value;
          var type   = document.getElementById('f-type').value;
          var search = document.getElementById('f-search').value.toLowerCase().trim();
          var visible = 0;

          document.querySelectorAll('.finding-card').forEach(function(card) {
            var show =
              (!sev    || card.dataset.severity === sev)  &&
              (!type   || card.dataset.type     === type) &&
              (!search || card.dataset.symbol.includes(search) || card.dataset.file.includes(search));

            card.style.display = show ? '' : 'none';

            if (show) {
              visible++;
              // Highlight search term in header text
              var sym = card.querySelector('.finding-symbol');
              var loc = card.querySelector('.finding-location');
              if (sym) sym.innerHTML = hlText(sym.dataset.orig || sym.textContent, search);
              if (loc) loc.innerHTML = hlText(loc.dataset.orig || loc.textContent, search);
            }
          });

          document.getElementById('visible-count').textContent =
            visible + ' finding' + (visible === 1 ? '' : 's');
        }

        // ── Chart click filter ─────────────────────────────────────────────
        // Toggles the filter — click again to clear
        function chartFilter(inputId, value) {
          var el = document.getElementById(inputId);
          el.value = (el.value === value) ? '' : value;
          applyFilters();
          document.getElementById('findings-list').scrollIntoView({ behavior: 'smooth', block: 'start' });
        }

        // ── Jump to first finding in file ──────────────────────────────────
        function jumpToFile(file) {
          var card = document.querySelector('.finding-card[data-file="' + file + '"]');
          if (!card) return;
          var id   = card.dataset.id;
          var body = document.getElementById('body-' + id);
          var icon = document.getElementById('icon-' + id);
          if (body.style.display !== 'block') {
            body.style.display = 'block';
            icon.textContent   = '▼';
          }
          card.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }

        // ── Keyboard shortcuts ─────────────────────────────────────────────
        // /  → focus search box
        // Esc → clear all filters
        document.addEventListener('keydown', function(e) {
          var search = document.getElementById('f-search');
          if (e.key === '/' && document.activeElement !== search) {
            e.preventDefault(); search.focus(); search.select();
          }
          if (e.key === 'Escape') {
            document.getElementById('f-severity').value = '';
            document.getElementById('f-type').value     = '';
            search.value = '';
            applyFilters();
            search.blur();
          }
        });

        // ── Wire up controls ───────────────────────────────────────────────
        document.getElementById('f-severity').addEventListener('change', applyFilters);
        document.getElementById('f-type').addEventListener('change', applyFilters);
        document.getElementById('f-search').addEventListener('input', applyFilters);
        """;
}
