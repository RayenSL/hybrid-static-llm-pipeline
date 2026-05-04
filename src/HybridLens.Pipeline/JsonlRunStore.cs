using System.Text.Json;
using System.Text.Json.Serialization;
using HybridLens.Core.Abstractions;
using HybridLens.Core.Models;

namespace HybridLens.Pipeline;

/// <summary>
/// Thread-safe append-only JSONL writer for <see cref="RunRecord"/>.
///
/// JSONL (one JSON object per line, no outer array) is preferred over a single
/// JSON document because:
///   1. Crashes never corrupt the file — partially written runs are simply truncated.
///   2. The file can be `tail -f`'d during long experiment campaigns.
///   3. pandas / R / DuckDB load it natively (<c>pd.read_json(..., lines=True)</c>).
/// </summary>
public sealed class JsonlRunStore : IRunStore
{
    private static readonly JsonSerializerOptions SerializerOptions = new()
    {
        PropertyNamingPolicy   = JsonNamingPolicy.SnakeCaseLower,
        DefaultIgnoreCondition = JsonIgnoreCondition.Never, // keep nulls — they are signal for the thesis
        Converters             = { new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower) },
        WriteIndented          = false
    };

    private readonly StreamWriter _writer;
    private readonly SemaphoreSlim _lock = new(1, 1);

    public string FilePath { get; }

    /// <summary>UTF-8 without BOM — standard JSONL pipelines (pandas/ujson, jq, DuckDB) reject the BOM.</summary>
    private static readonly System.Text.UTF8Encoding Utf8NoBom = new(encoderShouldEmitUTF8Identifier: false);

    public JsonlRunStore(string filePath)
    {
        FilePath = filePath;
        Directory.CreateDirectory(Path.GetDirectoryName(filePath)!);
        _writer = new StreamWriter(filePath, append: true, Utf8NoBom) { AutoFlush = false };
    }

    public async Task AppendAsync(RunRecord record, CancellationToken cancellationToken = default)
    {
        var line = JsonSerializer.Serialize(record, SerializerOptions);

        await _lock.WaitAsync(cancellationToken);
        try
        {
            await _writer.WriteLineAsync(line.AsMemory(), cancellationToken);
            await _writer.FlushAsync(cancellationToken); // flush per-record: never lose a run on crash
        }
        finally
        {
            _lock.Release();
        }
    }

    public async ValueTask DisposeAsync()
    {
        await _writer.FlushAsync();
        await _writer.DisposeAsync();
        _lock.Dispose();
    }
}
