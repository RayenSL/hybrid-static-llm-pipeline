using HybridLens.Core.Models;

namespace HybridLens.Core.Abstractions;

/// <summary>
/// Append-only sink for <see cref="RunRecord"/>s.
/// One record is appended per (finding × model × context-level × run-number).
/// Implementations must be safe to call concurrently from multiple pipeline tasks.
/// </summary>
public interface IRunStore : IAsyncDisposable
{
    Task AppendAsync(RunRecord record, CancellationToken cancellationToken = default);
}
