using System.Reflection;
using System.Runtime.Loader;
using System.Text.Json;
using HybridLens.DesignQuality;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;

internal static class GenericProbe
{
    // --probe <original-file> <candidate-file> <hidden-tests.cs> <output.json>
    public static int Run(string[] args)
    {
        var original=Path.GetFullPath(args[1]);
        var baseline=CorpusCompiler.Load(Directory.GetFiles(Path.GetDirectoryName(original)!,"*.csproj").Single());
        var old=baseline.SyntaxTrees.Single(t=>t.FilePath==original);
        var compilation=baseline.ReplaceSyntaxTree(old,CSharpSyntaxTree.ParseText(File.ReadAllText(args[2]),CorpusCompiler.ParseOptions,original))
            .AddSyntaxTrees(CSharpSyntaxTree.ParseText(File.ReadAllText(args[3]),CorpusCompiler.ParseOptions,"HiddenMaintenanceTests.cs"))
            .WithAssemblyName("Probe_"+Guid.NewGuid().ToString("N"));
        using var stream=new MemoryStream();var emitted=compilation.Emit(stream);
        if(!emitted.Success)
        {
            File.WriteAllText(args[4],JsonSerializer.Serialize(new {build_passed=false,errors=emitted.Diagnostics.Where(d=>d.Severity==DiagnosticSeverity.Error).Select(d=>d.ToString()).ToArray()}));
            return 1;
        }
        stream.Position=0;var context=new AssemblyLoadContext("probe",isCollectible:true);
        try
        {
            var assembly=context.LoadFromStream(stream);
            var result=(string)assembly.GetType("MaintenanceTests")!.GetMethod("Run",BindingFlags.Public|BindingFlags.Static)!.Invoke(null,null)!;
            File.WriteAllText(args[4],result);
        }
        finally {context.Unload();}
        return 0;
    }
}
