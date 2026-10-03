using System.Text.Json;
using HybridLens.Core.Models;
using HybridLens.Pipeline;

namespace HybridLens.Tests.Campaigns;

public sealed class CampaignPersistenceTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), $"campaign-persistence-{Guid.NewGuid():N}");
    private string LedgerPath => Path.Combine(_root, "execution-ledger.jsonl");

    public CampaignPersistenceTests() => Directory.CreateDirectory(_root);

    [Fact]
    public async Task LedgerRoundTrip_PreservesExistingSnakeCaseSchemaAndIgnoresFailedAttempts()
    {
        var ledger = new CampaignLedger<FactorialCampaignExecutionRecord>(LedgerPath, "campaign");
        var completed = Record();
        await ledger.AppendAsync(completed with { Completed = false, Error = "interrupted" });
        await ledger.AppendAsync(completed);

        Assert.Equal(completed.AssignmentId, Assert.Single(ledger.LoadCompleted()).Key);
        var bytes = File.ReadAllBytes(LedgerPath);
        Assert.False(bytes.Take(3).SequenceEqual(new byte[] { 0xef, 0xbb, 0xbf }));
        using var json = JsonDocument.Parse(File.ReadLines(LedgerPath).Last());
        Assert.Equal("campaign", json.RootElement.GetProperty("campaign_id").GetString());
        Assert.Equal("run", json.RootElement.GetProperty("run_ids")[0].GetString());
        Assert.False(json.RootElement.TryGetProperty("trace_sha256", out _));
    }

    [Fact]
    public async Task Resume_RejectsDuplicateCompletedAssignment()
    {
        var ledger = new CampaignLedger<FactorialCampaignExecutionRecord>(LedgerPath, "campaign");
        var record = Record();
        await ledger.AppendAsync(record);
        await ledger.AppendAsync(record);
        Assert.Contains("duplicate completion", Assert.Throws<InvalidDataException>(() => ledger.LoadCompleted()).Message);
    }

    [Fact]
    public async Task Resume_RejectsMissingTrace()
    {
        var ledger = new CampaignLedger<FactorialCampaignExecutionRecord>(LedgerPath, "campaign");
        var record = Record();
        await ledger.AppendAsync(record);
        File.Delete(record.TraceFile);
        Assert.Contains("no trace", Assert.Throws<InvalidDataException>(() => ledger.LoadCompleted()).Message);
    }

    [Fact]
    public async Task ResumeAndAppend_RejectDifferentCampaign()
    {
        var record = Record();
        await new CampaignLedger<FactorialCampaignExecutionRecord>(LedgerPath, "campaign").AppendAsync(record);
        var other = new CampaignLedger<FactorialCampaignExecutionRecord>(LedgerPath, "other");
        Assert.Throws<InvalidDataException>(() => other.LoadCompleted());
        await Assert.ThrowsAsync<InvalidDataException>(() => other.AppendAsync(record));
        Assert.Single(File.ReadAllLines(LedgerPath));
    }

    [Fact]
    public async Task Resume_RejectsHashDriftForContextLedger()
    {
        var basic = Record();
        var record = new LadderExecutionRecord
        {
            CampaignId = basic.CampaignId, AssignmentId = basic.AssignmentId, Order = 1,
            ContextLevel = ContextLevel.Full, Timestamp = basic.Timestamp, Completed = true,
            TraceFile = basic.TraceFile, TraceSha256 = FactorialCampaignPlanner.Sha256File(basic.TraceFile),
            RunIds = ["run"], EvaluatedModelCalls = 1, CrossFileFiles = 2, CrossFileTruncated = false,
            InputTokens = 10, OutputTokens = 20
        };
        var ledger = new CampaignLedger<LadderExecutionRecord>(LedgerPath, "campaign");
        await ledger.AppendAsync(record);
        Assert.Single(ledger.LoadCompleted(row => row.TraceSha256));
        File.AppendAllText(record.TraceFile, "tampered");
        Assert.Contains("hash changed", Assert.Throws<InvalidDataException>(() =>
            ledger.LoadCompleted(row => row.TraceSha256)).Message);
    }

    [Fact]
    public void Resume_RejectsPartialLedgerRowInsteadOfRepeatingACall()
    {
        File.WriteAllText(LedgerPath, "{\"campaign_id\":");
        Assert.Throws<JsonException>(() =>
            new CampaignLedger<FactorialCampaignExecutionRecord>(LedgerPath, "campaign").LoadCompleted());
    }

    [Fact]
    public async Task RecordingStore_ClosesBeforeHashingAndRejectsFurtherWrites()
    {
        var path = Path.Combine(_root, "trace.jsonl");
        await using var store = new RecordingRunStore(path);
        var record = new RunRecord
        {
            RunId = "run", Timestamp = DateTimeOffset.UtcNow, RunNumber = 1,
            AntiPatternType = AntiPatternType.LongMethod, FilePath = "input.cs", SymbolName = "Demo.Run",
            Line = 1, Severity = Severity.Warning, ContextLevel = ContextLevel.Minimal,
            ModelName = "fake", PromptVersion = "frozen", RawSystemPrompt = "system", RawUserPrompt = "user",
            ParseStatus = ParseStatus.Ok
        };
        await store.AppendAsync(record);
        await store.FlushAsync();
        await store.DisposeAsync();
        using var exclusive = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.None);
        Assert.True(exclusive.Length > 0);
        Assert.Equal("run", Assert.Single(store.RunIds));
        await Assert.ThrowsAsync<ObjectDisposedException>(() => store.AppendAsync(record));
    }

    private FactorialCampaignExecutionRecord Record()
    {
        var trace = Path.Combine(_root, "trace.jsonl");
        File.WriteAllText(trace, "{\"run_id\":\"run\"}\n");
        return new FactorialCampaignExecutionRecord
        {
            CampaignId = "campaign", AssignmentId = "assignment", Order = 1,
            Timestamp = DateTimeOffset.UtcNow, Completed = true, TraceFile = trace, RunIds = ["run"]
        };
    }

    public void Dispose() => WorkingCopy.TryDelete(_root);
}
