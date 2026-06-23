using System.Text.Json;
using HybridLens.ContextBuilder;
using HybridLens.Core.Abstractions;

namespace HybridLens.Pipeline;

/// <summary>
/// Strict-literal repair applier (§4.7.1, Appendix A.1). Sends the finding, the proposed repair,
/// and the original source to a non-evaluated Claude-family model behind the frozen applier prompt,
/// and parses its structured verdict. Makes no edits itself — it only relays the model's output.
/// </summary>
public sealed class RepairApplier(ILlmAdapter applier, string applierModel)
{
    public string Model         => applierModel;
    public string PromptVersion => PromptTemplate.ApplierVersion;

    public async Task<ApplierResult> ApplyAsync(
        RepairCandidate candidate, string originalSource, string relativePath, CancellationToken cancellationToken)
    {
        var request = new LlmRequest
        {
            SystemPrompt  = PromptTemplate.ApplierSystemPrompt,
            UserPrompt    = PromptTemplate.BuildApplierUserPrompt(
                candidate.Type.ToString(), candidate.SymbolName,
                $"{relativePath}:{candidate.Line}", candidate.RepairText,
                relativePath, originalSource),
            PromptVersion = PromptTemplate.ApplierVersion
        };

        var response = await applier.CompleteAsync(request, cancellationToken);
        var (parseOk, applicable, reason, edited) = Parse(response.Content);

        return new ApplierResult(
            SystemPrompt: request.SystemPrompt,
            UserPrompt:   request.UserPrompt,
            RawOutput:    response.Content,
            InputTokens:  response.InputTokens,
            OutputTokens: response.OutputTokens,
            ParseOk:      parseOk,
            Applicable:   applicable,
            Reason:       reason,
            EditedFile:   edited);
    }

    private static (bool ParseOk, bool Applicable, string? Reason, string? EditedFile) Parse(string content)
    {
        try
        {
            var json = content.Trim();
            if (json.StartsWith("```"))
            {
                json = string.Join('\n', json.Split('\n').Skip(1));
                var fence = json.LastIndexOf("```", StringComparison.Ordinal);
                if (fence >= 0) json = json[..fence].Trim();
            }

            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;

            var applicable =
                root.TryGetProperty("applicable", out var a) &&
                (a.ValueKind == JsonValueKind.True ||
                 (a.ValueKind == JsonValueKind.String && bool.TryParse(a.GetString(), out var b) && b));

            var reason = root.TryGetProperty("reason_if_not", out var r) ? r.GetString() : null;
            var edited = root.TryGetProperty("edited_file",   out var e) ? e.GetString() : null;

            // Claimed applicable but produced no file → treat as not applicable.
            if (applicable && string.IsNullOrWhiteSpace(edited))
                applicable = false;

            return (true, applicable, string.IsNullOrWhiteSpace(reason) ? null : reason, edited);
        }
        catch
        {
            return (false, false, null, null);
        }
    }
}

/// <summary>Outcome of one applier call. <see cref="ParseOk"/> false ⇒ the applier's output was not valid JSON.</summary>
public sealed record ApplierResult(
    string  SystemPrompt,
    string  UserPrompt,
    string  RawOutput,
    int     InputTokens,
    int     OutputTokens,
    bool    ParseOk,
    bool    Applicable,
    string? Reason,
    string? EditedFile);
