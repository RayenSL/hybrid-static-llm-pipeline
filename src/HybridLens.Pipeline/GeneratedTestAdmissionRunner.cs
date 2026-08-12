using System.Diagnostics;
using System.Security;
using System.Text;
using HybridLens.Core.Models;

namespace HybridLens.Pipeline;

/// <summary>
/// Materializes a generated test inside a fixed package-free console harness, then requires one
/// build and repeated successful executions against the pristine production project.
/// </summary>
public static class GeneratedTestAdmissionRunner
{
    private static readonly string[] ForbiddenFragments =
    [
        "System.IO", "File.", "Directory.", "HttpClient", "Process.", "Environment.",
        "Thread.Sleep", "Task.Delay", "Random(", "DateTime.Now", "DateTime.UtcNow", "Reflection"
    ];

    public static async Task<GeneratedTestAdmissionResult> RunAsync(
        GeneratedTestSource source,
        string productionProject,
        int baselineRuns,
        int timeoutSeconds,
        CancellationToken cancellationToken)
    {
        if (!ValidateAssertions(source, out var assertionReason))
            return new GeneratedTestAdmissionResult(
                GeneratedTestAdmissionStatus.AssertionGateFailed,
                assertionReason,
                false,
                null,
                [],
                string.Empty);

        var tempRoot = Path.Combine(Path.GetTempPath(), $"hybridlens-generated-test-{Guid.NewGuid():N}");
        Directory.CreateDirectory(tempRoot);
        try
        {
            var projectPath = Path.Combine(tempRoot, "GeneratedCharacterization.csproj");
            var programPath = Path.Combine(tempRoot, "Program.cs");
            await File.WriteAllTextAsync(projectPath, BuildProject(productionProject), cancellationToken);
            await File.WriteAllTextAsync(programPath, BuildProgram(source), cancellationToken);

            var build = await RunDotnetAsync(
                ["build", projectPath, "--nologo", "-v", "quiet", "-p:TreatWarningsAsErrors=false"],
                timeoutSeconds,
                cancellationToken);
            if (!build.Ok)
                return new GeneratedTestAdmissionResult(
                    GeneratedTestAdmissionStatus.BuildFailed,
                    "generated characterization project did not compile",
                    true,
                    false,
                    [],
                    Tail(build.Output, 4000));

            var requiredRuns = Math.Max(3, baselineRuns);
            var runResults = new List<bool>(requiredRuns);
            var output = new StringBuilder(build.Output);
            for (var i = 0; i < requiredRuns; i++)
            {
                var run = await RunDotnetAsync(
                    ["run", "--no-build", "-c", "Debug", "--project", projectPath],
                    timeoutSeconds,
                    cancellationToken);
                runResults.Add(run.Ok);
                output.AppendLine(run.Output);
            }

            if (runResults.All(x => x))
                return new GeneratedTestAdmissionResult(
                    GeneratedTestAdmissionStatus.Admitted,
                    null,
                    true,
                    true,
                    runResults,
                    Tail(output.ToString(), 4000));

            var status = runResults.Any(x => x)
                ? GeneratedTestAdmissionStatus.Flaky
                : GeneratedTestAdmissionStatus.BaselineFailed;
            var reason = status == GeneratedTestAdmissionStatus.Flaky
                ? "generated test was not stable across pristine baseline executions"
                : "generated test failed against the pristine baseline";
            return new GeneratedTestAdmissionResult(
                status,
                reason,
                true,
                true,
                runResults,
                Tail(output.ToString(), 4000));
        }
        finally
        {
            TryDeleteTree(tempRoot);
        }
    }

    /// <summary>
    /// Executes the original frozen visible test once against a repaired production project. A test
    /// project compilation failure is recorded separately from a runtime/assertion failure.
    /// </summary>
    public static async Task<GeneratedTestExecutionResult> ExecuteOnceAsync(
        GeneratedTestSource source,
        string productionProject,
        int timeoutSeconds,
        CancellationToken cancellationToken)
    {
        var stopwatch = Stopwatch.StartNew();
        var tempRoot = Path.Combine(Path.GetTempPath(), $"hybridlens-visible-test-{Guid.NewGuid():N}");
        Directory.CreateDirectory(tempRoot);
        try
        {
            var projectPath = Path.Combine(tempRoot, "GeneratedCharacterization.csproj");
            await File.WriteAllTextAsync(projectPath, BuildProject(productionProject), cancellationToken);
            await File.WriteAllTextAsync(Path.Combine(tempRoot, "Program.cs"), BuildProgram(source), cancellationToken);

            var build = await RunDotnetAsync(
                ["build", projectPath, "--nologo", "-v", "quiet", "-p:TreatWarningsAsErrors=false"],
                timeoutSeconds,
                cancellationToken);
            if (!build.Ok)
            {
                stopwatch.Stop();
                return new GeneratedTestExecutionResult(false, false, stopwatch.Elapsed.TotalMilliseconds,
                    Tail(build.Output, 4000));
            }

            var run = await RunDotnetAsync(
                ["run", "--no-build", "-c", "Debug", "--project", projectPath],
                timeoutSeconds,
                cancellationToken);
            stopwatch.Stop();
            return new GeneratedTestExecutionResult(true, run.Ok, stopwatch.Elapsed.TotalMilliseconds,
                Tail(build.Output + Environment.NewLine + run.Output, 4000));
        }
        finally
        {
            TryDeleteTree(tempRoot);
        }
    }

    public static bool HasNonVacuousAssertion(string body, out string? reason)
    {
        if (string.IsNullOrWhiteSpace(body) || !body.Contains("Check.", StringComparison.Ordinal))
        {
            reason = "test body contains no Check assertion";
            return false;
        }
        if (ForbiddenFragments.Any(body.Contains))
        {
            reason = "test body uses a forbidden nondeterministic or external-state API";
            return false;
        }

        var compact = string.Concat(body.Where(c => !char.IsWhiteSpace(c)));
        var assertions = compact.Split("Check.", StringSplitOptions.RemoveEmptyEntries).Skip(1).ToList();
        if (assertions.Count == 0 || assertions.All(a => a.StartsWith("True(true)", StringComparison.Ordinal)))
        {
            reason = "test body contains only a vacuous Check.True(true) assertion";
            return false;
        }
        if (!body.Contains("new ", StringComparison.Ordinal) && !body.Contains('.', StringComparison.Ordinal))
        {
            reason = "test body does not appear to invoke production code";
            return false;
        }

        reason = null;
        return true;
    }

    private static bool ValidateAssertions(GeneratedTestSource source, out string? reason)
    {
        if (ForbiddenFragments.Any(source.HelperCode.Contains))
        {
            reason = "test helpers use a forbidden nondeterministic or external-state API";
            return false;
        }
        if (!source.IsStructuredSuite)
            return HasNonVacuousAssertion(source.TestBody, out reason);
        if (source.Cases.Count != 5)
        {
            reason = "structured suite does not contain exactly five cases";
            return false;
        }
        foreach (var test in source.Cases)
        {
            if (!HasNonVacuousAssertion(test.TestBody, out var caseReason))
            {
                reason = $"{test.CaseId} failed assertion admission: {caseReason}";
                return false;
            }
        }
        reason = null;
        return true;
    }

    public static string BuildProgram(GeneratedTestSource source)
    {
        var usings = string.Join(Environment.NewLine, source.UsingDirectives);
        var generatedClass = source.IsStructuredSuite
            ? BuildStructuredClass(source)
            : $$"""
                static class GeneratedCharacterization
                {
                    public static void Run()
                    {
                {{Indent(source.TestBody, 8)}}
                    }
                }
                """;
        return $$"""
            {{usings}}
            using System.Collections.Generic;
            using System.Linq;

            try
            {
                GeneratedCharacterization.Run();
                Console.WriteLine("PASS");
                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"FAIL: {ex.GetType().Name}: {ex.Message}");
                return 1;
            }

            {{generatedClass}}

            static class Check
            {
                public static void True(bool value)
                {
                    if (!value) throw new InvalidOperationException("expected true");
                }

                public static void False(bool value)
                {
                    if (value) throw new InvalidOperationException("expected false");
                }

                public static void NotNull(object? value)
                {
                    if (value is null) throw new InvalidOperationException("expected non-null value");
                }

                public static void Null(object? value)
                {
                    if (value is not null) throw new InvalidOperationException("expected null value");
                }

                public static void Equal<T>(T expected, T actual)
                {
                    if (!EqualityComparer<T>.Default.Equals(expected, actual))
                        throw new InvalidOperationException($"expected '{expected}', actual '{actual}'");
                }

                public static void SequenceEqual<T>(IEnumerable<T> expected, IEnumerable<T> actual)
                {
                    if (!expected.SequenceEqual(actual))
                        throw new InvalidOperationException("sequences differ");
                }

                public static void Throws<TException>(Action action) where TException : Exception
                {
                    try
                    {
                        action();
                    }
                    catch (TException)
                    {
                        return;
                    }
                    catch (Exception ex)
                    {
                        throw new InvalidOperationException(
                            $"expected {typeof(TException).Name}, actual {ex.GetType().Name}");
                    }
                    throw new InvalidOperationException($"expected {typeof(TException).Name}");
                }
            }
            """;
    }

    private static string BuildStructuredClass(GeneratedTestSource source)
    {
        var calls = string.Join(Environment.NewLine,
            source.Cases.Select(test => $"        RunCase(\"{test.CaseId}\", Case_{test.CaseId});"));
        var methods = string.Join(Environment.NewLine + Environment.NewLine,
            source.Cases.Select(test => $$"""
                    private static void Case_{{test.CaseId}}()
                    {
                {{Indent(test.TestBody, 8)}}
                    }
                """));
        var helpers = string.IsNullOrWhiteSpace(source.HelperCode)
            ? string.Empty
            : Environment.NewLine + Indent(source.HelperCode, 4) + Environment.NewLine;
        return $$"""
            static class GeneratedCharacterization
            {
                public static void Run()
                {
            {{calls}}
                }

                private static void RunCase(string id, Action action)
                {
                    try { action(); }
                    catch (Exception ex) { throw new InvalidOperationException($"{id}: {ex.Message}", ex); }
                }
            {{helpers}}
            {{methods}}
            }
            """;
    }

    private static string BuildProject(string productionProject)
    {
        var escaped = SecurityElement.Escape(Path.GetFullPath(productionProject));
        return $$"""
            <Project Sdk="Microsoft.NET.Sdk">
              <PropertyGroup>
                <OutputType>Exe</OutputType>
                <TargetFramework>net10.0</TargetFramework>
                <ImplicitUsings>enable</ImplicitUsings>
                <Nullable>enable</Nullable>
                <TreatWarningsAsErrors>false</TreatWarningsAsErrors>
              </PropertyGroup>
              <ItemGroup>
                <ProjectReference Include="{{escaped}}" />
              </ItemGroup>
            </Project>
            """;
    }

    private static async Task<(bool Ok, string Output)> RunDotnetAsync(
        IReadOnlyList<string> arguments,
        int timeoutSeconds,
        CancellationToken cancellationToken)
    {
        var psi = new ProcessStartInfo
        {
            FileName = "dotnet",
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true
        };
        foreach (var argument in arguments) psi.ArgumentList.Add(argument);

        using var process = new Process { StartInfo = psi };
        var output = new StringBuilder();
        process.OutputDataReceived += (_, e) => { if (e.Data is not null) output.AppendLine(e.Data); };
        process.ErrorDataReceived += (_, e) => { if (e.Data is not null) output.AppendLine(e.Data); };
        process.Start();
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();

        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(Math.Max(1, timeoutSeconds)));
        try
        {
            await process.WaitForExitAsync(timeout.Token);
        }
        catch (OperationCanceledException)
        {
            try { if (!process.HasExited) process.Kill(entireProcessTree: true); } catch { }
            if (cancellationToken.IsCancellationRequested) throw;
            return (false, $"dotnet command timed out after {timeoutSeconds}s\n{output}");
        }
        return (process.ExitCode == 0, output.ToString());
    }

    private static string Indent(string text, int spaces)
    {
        var prefix = new string(' ', spaces);
        return string.Join(Environment.NewLine, text.Replace("\r", string.Empty).Split('\n').Select(line => prefix + line));
    }

    private static string Tail(string value, int maxChars) =>
        value.Length <= maxChars ? value : value[^maxChars..];

    private static void TryDeleteTree(string path)
    {
        try { if (Directory.Exists(path)) Directory.Delete(path, recursive: true); }
        catch { }
    }
}
