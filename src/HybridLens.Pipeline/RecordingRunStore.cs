using HybridLens.Core.Abstractions;
using HybridLens.Core.Models;

namespace HybridLens.Pipeline;

/// <summary>Persists assignment traces and retains their records for the completion ledger.</summary>
public sealed class RecordingRunStore(string tracePath) : IRunStore
{
    private readonly JsonlRunStore _inner = new(tracePath);
    private readonly List<RunRecord> _records = [];
    private bool _closed;

    public IReadOnlyList<RunRecord> Records => _records;
    public IEnumerable<string> RunIds => _records.Select(record => record.RunId);

    public async Task AppendAsync(RunRecord record, CancellationToken cancellationToken = default)
    {
        ObjectDisposedException.ThrowIf(_closed, this);
        await _inner.AppendAsync(record, cancellationToken);
        _records.Add(record);
    }

    /// <summary>Closes the trace before it is hashed and committed to the ledger.</summary>
    public async Task FlushAsync(CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        await DisposeAsync();
    }

    public async ValueTask DisposeAsync()
    {
        if (_closed) return;
        _closed = true;
        await _inner.DisposeAsync();
    }
}
