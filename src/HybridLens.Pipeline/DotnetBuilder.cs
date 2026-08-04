using System.Diagnostics;
using System.Text;

namespace HybridLens.Pipeline;

/// <summary>
/// Runs <c>dotnet build</c> on the applied working solution — the build gate of §4.5.1.
/// Warnings (incl. CS0618 obsolete warnings, which are expected at every Obsolete-API call site)
/// do not fail the gate: only a non-zero exit code does. The gate answers one question — does the
/// applied source compile?
/// </summary>
public static class DotnetBuilder
{
    public static Task<(bool Ok, string Output)> BuildAsync(
        string solutionPath, int timeoutSeconds, CancellationToken cancellationToken)
        => BuildAsync(solutionPath, timeoutSeconds, null, cancellationToken);

    /// <summary>
    /// As <see cref="BuildAsync(string,int,CancellationToken)"/>, with extra arguments appended to
    /// the command line. Solutions that cannot restore in the execution environment need
    /// <c>--no-restore</c> and <c>-p:NuGetAudit=false</c> so the gate builds against a package cache
    /// populated beforehand; without them a private-feed authentication failure would be
    /// indistinguishable from a repair that does not compile.
    /// </summary>
    public static async Task<(bool Ok, string Output)> BuildAsync(
        string solutionPath, int timeoutSeconds, IReadOnlyList<string>? extraArguments,
        CancellationToken cancellationToken)
    {
        var psi = new ProcessStartInfo
        {
            FileName               = "dotnet",
            RedirectStandardOutput = true,
            RedirectStandardError  = true,
            UseShellExecute        = false,
            CreateNoWindow         = true
        };
        psi.ArgumentList.Add("build");
        psi.ArgumentList.Add(solutionPath);
        psi.ArgumentList.Add("--nologo");
        psi.ArgumentList.Add("-v");
        psi.ArgumentList.Add("quiet");
        psi.ArgumentList.Add("-p:TreatWarningsAsErrors=false");
        if (extraArguments is not null)
            foreach (var argument in extraArguments)
                if (!string.IsNullOrWhiteSpace(argument))
                    psi.ArgumentList.Add(argument);

        using var proc = new Process { StartInfo = psi };
        var output = new StringBuilder();
        proc.OutputDataReceived += (_, e) => { if (e.Data is not null) output.AppendLine(e.Data); };
        proc.ErrorDataReceived  += (_, e) => { if (e.Data is not null) output.AppendLine(e.Data); };

        proc.Start();
        proc.BeginOutputReadLine();
        proc.BeginErrorReadLine();

        using var cts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        cts.CancelAfter(TimeSpan.FromSeconds(timeoutSeconds));

        try
        {
            await proc.WaitForExitAsync(cts.Token);
        }
        catch (OperationCanceledException)
        {
            try { if (!proc.HasExited) proc.Kill(entireProcessTree: true); } catch { /* best effort */ }
            if (cancellationToken.IsCancellationRequested) throw;
            return (false, $"build timed out after {timeoutSeconds}s\n{output}");
        }

        return (proc.ExitCode == 0, output.ToString());
    }
}
