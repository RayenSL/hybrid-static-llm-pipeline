using Microsoft.CodeAnalysis.CSharp;

namespace HybridLens.ChangeStub;

public static class FixtureChecks
{
    private const string Throw = "throw new global::System.NotImplementedException()";

    private static readonly List<string> Failures = [];

    private static void Check(bool condition, string name)
    {
        if (!condition) Failures.Add(name);
    }

    private static bool Parses(string text) =>
        !CSharpSyntaxTree.ParseText(text).GetDiagnostics().Any(d => d.Severity == Microsoft.CodeAnalysis.DiagnosticSeverity.Error);

    public static int Run()
    {
        const string pre = """
            namespace N;
            public class A
            {
                private int _x;
                public A(int x) : base() { _x = x; }
                public int Value { get; set; }
                public int Doubled { get { return _x * 2; } }
                public int Add(int a) { return a + _x; }
                public int Add(int a, int b) { return a + b; }
                public int Square(int a) => a * a;
                public class Inner { public int Add(int a) { return a; } }
            }
            """;

        var same = ChangeStubber.Stub(pre, pre);
        Check(same.Stubbed.Length == 0 && same.Text == pre, "identical sources produce no stubs");

        var trivia = pre.Replace("return a + b;", "return  a + b; /* comment */");
        Check(ChangeStubber.Stub(pre, trivia).Stubbed.Length == 0, "whitespace and comments are not changes");

        var added = pre.Replace("public int Square", "public int Triple(int a) { return a * 3; }\n    public int Square");
        var addedResult = ChangeStubber.Stub(pre, added);
        Check(addedResult.Stubbed.SequenceEqual(["A.Triple(int)"]), "added method is the only stub");
        Check(addedResult.Text.Contains("Triple(int a) { " + Throw + "; }"), "added method body throws");
        Check(addedResult.Text.Contains("return a + b;"), "unchanged method keeps its body");

        var changed = pre.Replace("return a + _x;", "return a - _x;");
        var changedResult = ChangeStubber.Stub(pre, changed);
        Check(changedResult.Stubbed.SequenceEqual(["A.Add(int)"]), "only the changed overload is stubbed");
        Check(changedResult.Text.Contains("return a + b;"), "other overload keeps its body");
        Check(changedResult.Text.Contains("public int Add(int a) { return a; }"), "same-named method in nested type is untouched");

        var expression = pre.Replace("a * a;", "a * a * a;");
        var expressionResult = ChangeStubber.Stub(pre, expression);
        Check(expressionResult.Text.Contains("Square(int a) => " + Throw + ";"), "expression body becomes a throw expression");

        var property = pre.Replace("return _x * 2;", "return _x * 3;");
        var propertyResult = ChangeStubber.Stub(pre, property);
        Check(propertyResult.Stubbed.SequenceEqual(["A.Doubled"]), "changed property is stubbed");
        Check(propertyResult.Text.Contains("get { " + Throw + "; }"), "property accessor body throws");
        Check(propertyResult.Text.Contains("public int Value { get; set; }"), "auto-property is untouched");

        var ctor = pre.Replace("_x = x;", "_x = x + 1;");
        var ctorResult = ChangeStubber.Stub(pre, ctor);
        Check(ctorResult.Stubbed.SequenceEqual(["A.A(int)"]), "changed constructor is stubbed");
        Check(ctorResult.Text.Contains(": base() { " + Throw + "; }"), "constructor initializer is kept");

        var nested = pre.Replace("public int Add(int a) { return a; }", "public int Add(int a) { return -a; }");
        Check(ChangeStubber.Stub(pre, nested).Stubbed.SequenceEqual(["A.Inner.Add(int)"]), "nested type member key includes its type");

        var field = pre.Replace("private int _x;", "private int _x = 5;");
        var fieldResult = ChangeStubber.Stub(pre, field);
        Check(fieldResult.Stubbed.Length == 0 && fieldResult.Unstubbable.SequenceEqual(["A._x"]), "changed field initialiser is reported as unstubbable");

        foreach (var text in new[] { addedResult.Text, changedResult.Text, expressionResult.Text, propertyResult.Text, ctorResult.Text })
            Check(Parses(text), "stubbed output parses");

        const string api = """
            namespace N;
            public class Api
            {
                public int Add(int a) { return a; }
                internal string Name { get; set; } = "";
                private int Hidden() { return 1; }
                protected void Hook(string s) { }
            }
            internal interface IPort { void Send(int x); }
            """;
        Check(ApiChecker.Missing(api, api).Length == 0, "identical source has no missing API");
        Check(ApiChecker.Missing(api, api.Replace("return a;", "return a + 1;")).Length == 0, "body change keeps API");
        Check(ApiChecker.Missing(api, api.Replace("private int Hidden() { return 1; }", "")).Length == 0, "private member removal is not API loss");
        Check(ApiChecker.Missing(api, api.Replace("public int Add(int a) { return a; }", "public int Add(int a) { return a; }\n    public int Extra() => 0;")).Length == 0, "added member is allowed");
        Check(ApiChecker.Missing(api, api.Replace("public int Add(int a) { return a; }", "")).SequenceEqual(["Api.Add(int)"]), "removed public method is reported");
        Check(ApiChecker.Missing(api, api.Replace("Add(int a)", "Add(long a)")).SequenceEqual(["Api.Add(int)"]), "changed parameter type is reported");
        Check(ApiChecker.Missing(api, api.Replace("internal string Name { get; set; } = \"\";", "")).SequenceEqual(["Api.Name"]), "removed internal property is reported");
        Check(ApiChecker.Missing(api, api.Replace("protected void Hook(string s) { }", "")).SequenceEqual(["Api.Hook(string)"]), "removed protected method is reported");
        Check(ApiChecker.Missing(api, api.Replace("void Send(int x);", "")).SequenceEqual(["IPort.Send(int)"]), "removed interface member is reported");
        Check(ApiChecker.Missing(api, api.Replace("internal interface IPort { void Send(int x); }", "")).SequenceEqual(["IPort", "IPort.Send(int)"]), "removed type is reported");

        const string sigPre = """
            namespace N;
            public class Calc
            {
                public int Add(int a) { return a; }
                private int Helper() { return 1; }
            }
            """;
        Check(ApiSignatures.Added(sigPre, sigPre).Length == 0, "identical source adds no signatures");
        Check(ApiSignatures.Added(sigPre, sigPre.Replace("return a;", "return a + 1;")).Length == 0, "body change adds no signatures");
        Check(ApiSignatures.Added(sigPre, sigPre.Replace("private int Helper() { return 1; }", "private int Helper() { return 1; }\n    private int More() => 2;")).Length == 0, "private addition is not API");
        var sigAdded = ApiSignatures.Added(sigPre, sigPre.Replace("public int Add(int a) { return a; }", "public int Add(int a) { return a; }\n    public int Mul(int a, int b) => a * b;\n    public int Count { get { return 3; } }"));
        Check(sigAdded.SequenceEqual(["Calc: public int Count { get; }", "Calc: public int Mul(int a, int b);"]), "added method and property signatures without bodies");
        var typed = ApiSignatures.Added(sigPre, sigPre + "\npublic sealed class Pair : Calc\n{\n    public Pair(int x) { X = x; }\n    public int X { get; }\n}\n");
        Check(typed.SequenceEqual(["Pair: public Pair(int x);", "Pair: public int X { get; }", "Pair: public sealed class Pair : Calc"]), "new type header and members");
        var sigChanged = ApiSignatures.Added(sigPre, sigPre.Replace("public int Add(int a)", "public long Add(int a)"));
        Check(sigChanged.SequenceEqual(["Calc: public long Add(int a);"]), "changed return type is reported");

        Check(ApiSignatures.Added(sigPre, sigPre + "\npublic enum Mode { And, Or }\n").SequenceEqual(["Mode: public enum Mode { And, Or }"]), "enum header lists its values");
        Check(ApiSignatures.Added(sigPre, sigPre + "\npublic record Point(int X, int Y);\n").SequenceEqual(["Point: public record Point(int X, int Y)"]), "primary constructor parameters are part of the header");

        foreach (var failure in Failures) Console.Error.WriteLine("FAIL: " + failure);
        Console.WriteLine(Failures.Count == 0 ? "All change-stub fixture checks passed." : $"{Failures.Count} fixture check(s) failed.");
        return Failures.Count == 0 ? 0 : 1;
    }
}
