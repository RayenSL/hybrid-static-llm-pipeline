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

    public Task<LlmResponse> CompleteAsync(
        LlmRequest request,
        CancellationToken cancellationToken = default)
    {
        var messages = new List<Message>
        {
            new() { Role = RoleType.User, Content = [new TextContent { Text = request.UserPrompt }] }
        };
        return SendAsync(request.SystemPrompt, messages, cancellationToken);
    }

    public Task<LlmResponse> CompleteAsync(
        LlmConversation conversation,
        CancellationToken cancellationToken = default)
    {
        var messages = conversation.Turns.Select(t => new Message
        {
            Role    = t.Role == ChatRole.Assistant ? RoleType.Assistant : RoleType.User,
            Content = [new TextContent { Text = t.Content }]
        }).ToList();
        return SendAsync(conversation.SystemPrompt, messages, cancellationToken);
    }

    private async Task<LlmResponse> SendAsync(
        string systemPrompt, List<Message> messages, CancellationToken cancellationToken)
    {
        var parameters = new MessageParameters
        {
            Model       = _config.Model,
            MaxTokens   = _config.MaxTokens,
            Temperature = (decimal)_config.Temperature,
            System      = [new SystemMessage(systemPrompt)],
            Messages    = messages
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
