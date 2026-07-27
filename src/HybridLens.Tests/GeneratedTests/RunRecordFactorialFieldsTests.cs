using System.Text.Json;
using HybridLens.Core.Models;
using HybridLens.Pipeline;

namespace HybridLens.Tests.GeneratedTests;

public sealed class RunRecordFactorialFieldsTests
{
    [Fact]
    public async Task FactorialAndCostFields_SurviveJsonlStore()
    {
        var path = Path.Combine(Path.GetTempPath(), $"hl-jsonl-{Guid.NewGuid():N}.jsonl");
        try
        {
            var record = new RunRecord
            {
                RunId = "run",
                Timestamp = DateTimeOffset.UtcNow,
                RunNumber = 1,
                AntiPatternType = AntiPatternType.LongMethod,
                FilePath = "Proj/Thing.cs",
                SymbolName = "Demo.Thing.M",
                Line = 10,
                Severity = Severity.Warning,
                ContextLevel = ContextLevel.Structural,
                ModelName = "model",
                PromptVersion = "prompt",
                Architecture = "grounded_iterative",
                GroundingEnabled = true,
                ControlStructure = "iterative",
                VisibleTestsEnabled = true,
                VisibleTestAvailable = true,
                VisibleTestArtifactRef = "visible.json",
                VisibleTestSha256 = "test-hash",
                VisibleTestPassed = false,
                LlmCallCount = 3,
                BuildAttemptCount = 2,
                TestAttemptCount = 2,
                TestDurationMs = 25.5,
                MaterializedSourceRef = "final.json",
                MaterializedSourceSha256 = "source-hash",
                RawSystemPrompt = "system",
                RawUserPrompt = "user",
                DurationMs = 100.25,
                ParseStatus = ParseStatus.Ok
            };
            await using (var store = new JsonlRunStore(path))
                await store.AppendAsync(record);

            using var document = JsonDocument.Parse(await File.ReadAllTextAsync(path));
            var root = document.RootElement;
            Assert.True(root.GetProperty("grounding_enabled").GetBoolean());
            Assert.Equal("iterative", root.GetProperty("control_structure").GetString());
            Assert.True(root.GetProperty("visible_tests_enabled").GetBoolean());
            Assert.False(root.GetProperty("visible_test_passed").GetBoolean());
            Assert.Equal(3, root.GetProperty("llm_call_count").GetInt32());
            Assert.Equal(2, root.GetProperty("build_attempt_count").GetInt32());
            Assert.Equal(2, root.GetProperty("test_attempt_count").GetInt32());
            Assert.Equal(25.5, root.GetProperty("test_duration_ms").GetDouble());
            Assert.Equal("final.json", root.GetProperty("materialized_source_ref").GetString());
            Assert.Equal("source-hash", root.GetProperty("materialized_source_sha256").GetString());
            Assert.Equal(100.25, root.GetProperty("duration_ms").GetDouble());
        }
        finally
        {
            try { if (File.Exists(path)) File.Delete(path); } catch { }
        }
    }
}
