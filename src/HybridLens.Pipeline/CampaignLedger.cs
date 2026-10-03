using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using HybridLens.Core.Models;

namespace HybridLens.Pipeline;

/// <summary>Append-only completion ledger shared by frozen campaign executors.</summary>
public sealed class CampaignLedger<T>(string path, string campaignId) where T : class, ICampaignExecutionRecord
{
    private static readonly JsonSerializerOptions Json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower) }
    };

    public Dictionary<string, T> LoadCompleted(Func<T, string?>? traceHash = null)
    {
        var completed = new Dictionary<string, T>(StringComparer.Ordinal);
        if (!File.Exists(path)) return completed;
        foreach (var line in File.ReadLines(path))
        {
            if (string.IsNullOrWhiteSpace(line)) continue;
            var record = JsonSerializer.Deserialize<T>(line, Json)
                ?? throw new InvalidDataException("execution ledger contains an invalid row");
            if (record.CampaignId != campaignId)
                throw new InvalidDataException("execution ledger belongs to a different campaign");
            if (!record.Completed) continue;
            if (!completed.TryAdd(record.AssignmentId, record))
                throw new InvalidDataException($"execution ledger contains duplicate completion: {record.AssignmentId}");
            if (!File.Exists(record.TraceFile))
                throw new InvalidDataException($"completed assignment {record.AssignmentId} has no trace: {record.TraceFile}");
            if (traceHash is not null && Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(record.TraceFile))) != traceHash(record))
                throw new InvalidDataException($"completed assignment trace hash changed: {record.AssignmentId}");
        }
        return completed;
    }

    public async Task AppendAsync(T record, CancellationToken cancellationToken = default)
    {
        if (record.CampaignId != campaignId)
            throw new InvalidDataException("execution ledger belongs to a different campaign");
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!);
        await File.AppendAllTextAsync(path, JsonSerializer.Serialize(record, Json) + Environment.NewLine,
            new UTF8Encoding(false), cancellationToken);
    }
}
