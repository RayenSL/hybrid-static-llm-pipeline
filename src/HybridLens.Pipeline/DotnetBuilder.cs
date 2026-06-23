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
    public static async Task<(bool Ok, string Output)> BuildAsync(
        string solutionPath, int timeoutSeconds, CancellationToken cancellationToken)
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
