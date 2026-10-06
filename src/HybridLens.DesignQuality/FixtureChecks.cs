using HybridLens.Core.Configuration;
using HybridLens.StaticAnalysis.Detectors;
using Microsoft.CodeAnalysis.CSharp;

namespace HybridLens.DesignQuality;

/// <summary>Small executable structural ground-truth fixtures; assertions are not design-quality labels.</summary>
public static class FixtureChecks
{
    private static FileFacts Facts(string code)
    {
        var tree = CSharpSyntaxTree.ParseText(code, CorpusCompiler.ParseOptions, "Fixture.cs");
        return StructuralFacts.Measure(CorpusCompiler.FromSources([tree]), tree);
    }
    private static void Check(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }
    private static void Measured(params FileFacts[] facts) => Check(facts.All(f => f.Status == "measured"),
        string.Join("\n", facts.SelectMany(f => f.SemanticErrors)));

    public static int Run()
    {
        var checks = new List<(string Name, Action Test)>
        {
            ("unchanged", () => {
                var a = Facts("class C { int M(int x) { if(x>0) return 1; return 0; } }"); Measured(a);
                var l = Lineage.Compare(a, a, "C.M", "long_method");
                Check(l.Candidates.Single().Evidence == "same_declaration_id" && l.UnmatchedAfter.Length == 0, "Identity mapping");
                Check(a.DecisionCount == 1 && a.MaxComplexity == 2 && a.MaxControlNesting == 1, "Hand-counted complexity");
            }),
            ("formatting", () => {
                var a = Facts("class C { int M() { return 1; } }");
                var b = Facts("class C\n{\n int M() { /* comment */ return 1; }\n}"); Measured(a,b);
                Check(a.Callables.Single().BodyFingerprint == b.Callables.Single().BodyFingerprint, "Trivia must not change body fingerprint");
            }),
            ("rename_candidate", () => {
                var a = Facts("class C { int M() { return 1; } }"); var b = Facts("class D { int N() { return 1; } }"); Measured(a,b);
                Check(Lineage.Compare(a,b,"C.M","long_method").Candidates.Single().Evidence == "identical_body_candidate", "Rename only candidate");
            }),
            ("extract_method", () => {
                var a = Facts("class C { int M(int x) { if(x>0) return 1; return 0; } }");
                var b = Facts("class C { int M(int x) { return H(x); } int H(int x) { if(x>0) return 1; return 0; } }"); Measured(a,b);
                Check(a.DecisionCount == b.DecisionCount, "Extraction preserves total decisions");
                Check(b.Callables.Sum(c=>c.Complexity) == a.Callables.Sum(c=>c.Complexity)+1, "Method baseline explains CC sum increase");
                Check(Lineage.Compare(a,b,"C.M","long_method").ReachableAddedCallables.Single() == "M:C.H(System.Int32)", "Reachable new helper");
            }),
            ("owned_state_extraction", () => {
                var a = Facts("class C { int x; public int M() => ++x; }");
                var b = Facts("class C { readonly D d=new(); public int M()=>d.M(); } class D { int x; public int M()=>++x; }"); Measured(a,b);
                Check(b.Callables.Single(c=>c.Id=="M:D.M").AttributeAccesses.Contains("F:D.x"), "Moved field owner resolved");
                Check(b.Types.All(t=>t.Tcc is null), "One-public-method cohesion is undefined");
            }),
            ("wrapper", () => {
                var b = Facts("class C { int M()=>H(); int H()=>1; }"); Measured(b);
                Check(b.Callables.Single(c=>c.Id=="M:C.M").Calls.Contains("M:C.H"), "Wrapper edge retained");
            }),
            ("complex_helper", () => {
                var body = string.Concat(Enumerable.Range(0,11).Select(i=>$"if (x == {i}) return {i};"));
                var tree = CSharpSyntaxTree.ParseText($"class C {{ int M(int x)=>H(x); int H(int x){{{body} return -1;}} }}", CorpusCompiler.ParseOptions,"Fixture.cs");
                var compilation=CorpusCompiler.FromSources([tree]); var b=StructuralFacts.Measure(compilation,tree); Measured(b);
                var finding=new LongMethodDetector(new LongMethodConfig()).Detect(compilation).Single();
                Check(finding.SymbolName=="C.H" && b.MaxComplexity==12, "Helper violation remains visible");
            }),
            ("shared_mutable_state", () => {
                var b = Facts("class S { public int x; } class C { S s=new(); int M()=>++s.x; } class D { S s=new(); int M()=>++s.x; }"); Measured(b);
                Check(b.Callables.Count(c=>c.AttributeAccesses.Contains("F:S.x"))==2, "Two accessors of declared state, not proof of runtime aliasing");
            }),
            ("cycle", () => {
                var b=Facts("class C { int A()=>B(); int B()=>A(); }"); Measured(b);
                Check(b.Callables.Single(c=>c.Id=="M:C.A").Calls.Contains("M:C.B") && b.Callables.Single(c=>c.Id=="M:C.B").Calls.Contains("M:C.A"),"Both cycle edges");
            }),
            ("duplication", () => {
                var c=StructuralFacts.CloneCoverage([ ["a","b","c","d"], ["a","b","c","e"] ],3);
                Check(c.CoveredTokens==6 && c.EligibleTokens==8 && c.Proportion==0.75,"Overlapping windows counted once");
                Check(StructuralFacts.CloneCoverage([["a","b","a","b"]],2).CoveredTokens==0,"Within-body repetition excluded");
                Check(StructuralFacts.CloneCoverage([],3).Proportion is null,"Undefined empty denominator");
            }),
            ("deleted_logic", () => {
                var a=Facts("class C { int M(int x) { if(x>0) return 1; return 0; } }"); var b=Facts("class C { int M(int x)=>0; }"); Measured(a,b);
                var l=Lineage.Compare(a,b,"C.M","long_method");
                Check(b.DecisionCount==0 && l.Status=="candidates_only","Fewer decisions must not imply behavioural correctness");
            }),
            ("ambiguous_mapping", () => {
                var a=Facts("class C { int M()=>1; }"); var b=Facts("class C { int A()=>1; int B()=>1; }"); Measured(a,b);
                Check(Lineage.Compare(a,b,"C.M","long_method").Candidates.Length==2,"Retain competing identical bodies");
            }),
            ("nested_callable_ownership", () => {
                var b=Facts("class C { int M(int x) { int H(int y) { if(y>0) return 1; return 0; } return H(x); } }"); Measured(b);
                Check(b.DecisionCount==1 && b.Callables.Single(c=>c.Id=="M:C.M(System.Int32)").DecisionCount==0,"Do not double count nested decisions");
                Check(b.Callables.Single(c=>c.Id=="M:C.M(System.Int32)").HistoricalComplexity==2,"Historical metric retained separately");
            }),
            ("missing_semantics", () => {
                var b=Facts("class C { Missing x; int M()=>x.F(); }");
                Check(b.Status=="semantic_error" && b.Types.Single().Atfd is null,"Missing semantic facts never zero");
                Check(Lineage.Compare(b,b,"C.M","long_method").Status=="unavailable","No lineage on broken compilation");
            }),
            ("file_metrics", () => {
                const string code = "class C { int M(int x) { if(x>0) return 1; return 0; } }";
                var m = FileMetrics.Measure(code);
                Check(m.Tokens == 24, "Hand-counted syntax tokens, end-of-file excluded");
                Check(m.DecisionBurden == Facts(code).DecisionCount && m.MaxCallableComplexity == Facts(code).MaxComplexity, "Agrees with structural facts");
                var formatted = FileMetrics.Measure("// header\nclass C\n{\n    int M(int x)\n    {\n        if (x > 0) return 1; /* note */\n        return 0;\n    }\n}\n");
                Check(formatted.Tokens == m.Tokens && formatted.DecisionBurden == m.DecisionBurden, "Comments and layout are not code volume");
                Check(FileMetrics.Measure("class C { int x = 1; }").MaxCallableComplexity is null, "No callables gives null maximum");
                var callables = FileMetrics.Measure("namespace N { class C { int M(int x) { if (x > 0) return 1; return 0; } int M(bool a, bool b) => a && b ? 1 : 2; void P() { System.Func<int, int> f = y => y > 0 ? y : 0; } } }").Callables;
                Check(callables["C.M"] == 2 && callables["C.P"] == 0, "Owned decisions per Type.Method, the maximum over overloads, lambdas excluded");
            }),
            ("overload_ambiguity", () => {
                var b=Facts("class C { int M()=>0; int M(int x)=>x; }"); Measured(b);
                Check(Lineage.Compare(b,b,"C.M","long_method").Status=="target_ambiguous","Do not arbitrarily select overload");
            })
        };
        var failures=0;
        foreach(var (name,test) in checks)
        {
            try { test(); Console.WriteLine($"PASS {name}"); }
            catch(Exception e) { failures++; Console.Error.WriteLine($"FAIL {name}: {e.Message}"); }
        }
        Console.WriteLine($"{checks.Count-failures}/{checks.Count} structural fixture checks passed");
        return failures==0 ? 0 : 1;
    }
}
