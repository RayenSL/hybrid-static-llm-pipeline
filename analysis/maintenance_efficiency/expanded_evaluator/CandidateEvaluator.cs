using System.Collections;
using System.Globalization;
using System.Reflection;
using System.Runtime.Loader;
using System.Text.Json;
using HybridLens.DesignQuality;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;

internal static class CandidateEvaluator
{
    // --compile <original-file> <candidate-file> <output-json>
    // --evaluate <original-file> <candidate-file> <output-json> <tasks-json> <task-id>
    public static int Run(string[] args)
    {
        if (args.Length != (args[0] == "--compile" ? 4 : 6)) throw new ArgumentException("Invalid evaluator arguments");
        var original = Path.GetFullPath(args[1]);
        var project = Directory.GetFiles(Path.GetDirectoryName(original)!, "*.csproj").Single();
        var baseline = CorpusCompiler.Load(project);
        var tree = baseline.SyntaxTrees.Single(t => t.FilePath == original);
        var compilation = baseline.ReplaceSyntaxTree(tree, CSharpSyntaxTree.ParseText(File.ReadAllText(args[2]), CorpusCompiler.ParseOptions, original))
            .WithAssemblyName("MaintenanceCandidate_" + Guid.NewGuid().ToString("N"));
        using var stream = new MemoryStream();
        var emit = compilation.Emit(stream);
        var diagnostics = emit.Diagnostics.Where(d => d.Severity == DiagnosticSeverity.Error).Select(d => d.ToString()).ToArray();
        int? acceptance = null, regression = null;
        string? error = null;
        if (emit.Success && args[0] == "--evaluate")
        {
            using var tasks = JsonDocument.Parse(File.ReadAllBytes(args[4]));
            var task = tasks.RootElement.GetProperty("tasks").EnumerateArray().Single(t => t.GetProperty("task_id").GetString() == args[5]);
            stream.Position = 0;
            var context = new AssemblyLoadContext("candidate", isCollectible: true);
            try
            {
                var assembly = context.LoadFromStream(stream);
                int Failures(string field) => task.GetProperty(field).EnumerateArray().Count(c => !Pass(assembly,c));
                acceptance = Failures("acceptance_cases"); regression = Failures("regression_cases");
            }
            catch (Exception e) { error = e.GetType().Name; }
            finally { context.Unload(); }
        }
        File.WriteAllText(args[3], JsonSerializer.Serialize(new { build_passed = emit.Success, diagnostics,
            acceptance_failures = acceptance, regression_failures = regression, evaluation_error = error,
            acceptance_passed = !emit.Success || error is not null ? false : acceptance.HasValue ? acceptance == 0 : (bool?)null,
            regression_passed = !emit.Success || error is not null ? false : regression.HasValue ? regression == 0 : (bool?)null }));
        return 0;
    }

    private static bool Pass(Assembly assembly, JsonElement c)
    {
        try
        {
            var orderType = assembly.GetType("Ordering.Order")!;
            var lineType = assembly.GetType("Ordering.OrderLine")!;
            var order = Activator.CreateInstance(orderType)!;
            var line = Activator.CreateInstance(lineType)!;
            var price = decimal.Parse(c[0].GetString()!, CultureInfo.InvariantCulture);
            lineType.GetProperty("UnitPrice")!.SetValue(line, price);
            lineType.GetProperty("Quantity")!.SetValue(line, 1);
            ((IList)orderType.GetProperty("Lines")!.GetValue(order)!).Add(line);
            orderType.GetProperty("Channel")!.SetValue(order, Enum.Parse(assembly.GetType("Ordering.OrderChannel")!, c[2].GetString()!));
            orderType.GetProperty("DiscountOverride")!.SetValue(order,
                c[3].ValueKind == JsonValueKind.Null ? null : decimal.Parse(c[3].GetString()!, CultureInfo.InvariantCulture));
            var pricingType = assembly.GetType("Ordering.PricingRules")!;
            var pricing = Activator.CreateInstance(pricingType)!;
            var actual = pricingType.GetMethod("ApplyAdjustments")!.Invoke(pricing,
                [order, Enum.Parse(assembly.GetType("Ordering.CustomerTier")!, c[1].GetString()!)]);
            return actual is decimal number && number == decimal.Parse(c[4].GetString()!, CultureInfo.InvariantCulture);
        }
        catch { return false; }
    }
}
