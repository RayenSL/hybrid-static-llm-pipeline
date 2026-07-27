using HybridLens.Core.Models;
using HybridLens.Pipeline;

namespace HybridLens.Tests.Analysis;

public sealed class KnownInstanceTests
{
    [Theory]
    [InlineData("declaration", 1)]
    [InlineData("\nline one\nline two\n", 2)]
    [InlineData("\r\nline one\r\nline two\r\n", 2)]
    public void Create_IgnoresBoundaryNewlinesWhenDerivingEndLine(
        string snippet,
        int declarationLineCount)
    {
        var instance = KnownInstance.Create(
            AntiPatternType.LongMethod,
            "Example.cs",
            "Example.Run",
            line: 10,
            Severity.Warning,
            snippet);

        Assert.Equal(10 + declarationLineCount - 1, instance.EndLine);
    }
}
