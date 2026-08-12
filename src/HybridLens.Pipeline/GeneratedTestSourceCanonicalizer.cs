using System.Security.Cryptography;
using System.Text;
using HybridLens.Core.Models;

namespace HybridLens.Pipeline;

public static class GeneratedTestSourceCanonicalizer
{
    public static string Content(GeneratedTestSource source)
    {
        if (!source.IsStructuredSuite)
            return string.Join("\n", source.UsingDirectives) + "\n" + source.TestBody;

        var output = new StringBuilder();
        output.AppendLine(source.TestName);
        foreach (var directive in source.UsingDirectives) output.AppendLine(directive);
        output.AppendLine(source.HelperCode);
        foreach (var test in source.Cases)
        {
            output.AppendLine(test.CaseId);
            output.AppendLine(test.Category.ToString());
            output.AppendLine(test.TestName);
            output.AppendLine(test.TestBody);
        }
        return output.ToString();
    }

    public static string Hash(GeneratedTestSource source) =>
        Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(Content(source))));

    public static string RenderForPrompt(GeneratedTestSource source)
    {
        if (!source.IsStructuredSuite) return source.TestBody;
        var output = new StringBuilder();
        if (!string.IsNullOrWhiteSpace(source.HelperCode))
        {
            output.AppendLine("// Deterministic in-memory test helpers");
            output.AppendLine(source.HelperCode.Trim());
            output.AppendLine();
        }
        foreach (var test in source.Cases)
        {
            output.AppendLine($"// {test.CaseId} [{CategoryName(test.Category)}]: {test.TestName}");
            output.AppendLine("{");
            foreach (var line in test.TestBody.Replace("\r", string.Empty).Split('\n'))
                output.AppendLine("    " + line);
            output.AppendLine("}");
            output.AppendLine();
        }
        return output.ToString().TrimEnd();
    }

    private static string CategoryName(GeneratedTestCaseCategory category) => category switch
    {
        GeneratedTestCaseCategory.HappyPath => "happy_path",
        GeneratedTestCaseCategory.EmptyOrInvalid => "empty_or_invalid",
        GeneratedTestCaseCategory.BoundaryValues => "boundary_values",
        GeneratedTestCaseCategory.AlternativePath => "alternative_path",
        GeneratedTestCaseCategory.DependencyOrState => "dependency_or_state",
        _ => category.ToString()
    };
}
