using Anthropic.SDK;
using Anthropic.SDK.Messaging;
using HybridLens.Core.Abstractions;

namespace HybridLens.LLM;

internal sealed class ClaudeAdapter : ILlmAdapter
{
    private readonly AnthropicClient _client;
    private readonly ResolvedLlmConfig _config;

    public ClaudeAdapter(ResolvedLlmConfig config)
    {
        _config = config;
        _client = new AnthropicClient(config.ApiKey ?? string.Empty);
    }

    public async Task<LlmResponse> CompleteAsync(
        LlmRequest request,
        CancellationToken cancellationToken = default)
    {
        var parameters = new MessageParameters
        {
            Model       = _config.Model,
            MaxTokens   = _config.MaxTokens,
            Temperature = (decimal)_config.Temperature,
            System      = [new SystemMessage(request.SystemPrompt)],
            Messages    =
            [
                new Message { Role = RoleType.User, Content = [new TextContent { Text = request.UserPrompt }] }
            ]
        };

        var response = await _client.Messages.GetClaudeMessageAsync(parameters, cancellationToken);
        var content  = response.Content.OfType<TextContent>().FirstOrDefault()?.Text
                    ?? response.FirstMessage
                    ?? string.Empty;

        return new LlmResponse
        {
            Content      = content,
            InputTokens  = response.Usage.InputTokens,
            OutputTokens = response.Usage.OutputTokens
        };
    }
}
