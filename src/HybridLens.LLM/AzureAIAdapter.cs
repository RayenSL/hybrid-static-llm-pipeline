using Azure;
using Azure.AI.OpenAI;
using HybridLens.Core.Abstractions;
using OpenAI.Chat;

namespace HybridLens.LLM;

internal sealed class AzureAIAdapter : ILlmAdapter
{
    private readonly ChatClient _chatClient;
    private readonly ResolvedLlmConfig _config;

    public AzureAIAdapter(ResolvedLlmConfig config)
    {
        _config = config;

        if (string.IsNullOrWhiteSpace(config.BaseUrl))
            throw new InvalidOperationException(
                $"Model '{config.Model}' has no BaseUrl configured. " +
                "Set it under Llm.Models.<name>.BaseUrl.");

        var options = new AzureOpenAIClientOptions();
        if (config.TimeoutSeconds is { } seconds) options.NetworkTimeout = TimeSpan.FromSeconds(seconds);
        if (config.MaxRetries is { } retries) options.RetryPolicy = new System.ClientModel.Primitives.ClientRetryPolicy(retries);
        var client = new AzureOpenAIClient(
            new Uri(config.BaseUrl),
            new AzureKeyCredential(config.ApiKey ?? string.Empty),
            options);

        _chatClient = client.GetChatClient(config.Model);
    }

    public Task<LlmResponse> CompleteAsync(
        LlmRequest request,
        CancellationToken cancellationToken = default)
    {
        var messages = new List<ChatMessage>
        {
            new SystemChatMessage(request.SystemPrompt),
            new UserChatMessage(request.UserPrompt)
        };
        return CompleteChatAsync(messages, cancellationToken);
    }

    public Task<LlmResponse> CompleteAsync(
        LlmConversation conversation,
        CancellationToken cancellationToken = default)
    {
        var messages = new List<ChatMessage>(conversation.Turns.Count + 1)
        {
            new SystemChatMessage(conversation.SystemPrompt)
        };
        foreach (var turn in conversation.Turns)
            messages.Add(turn.Role == ChatRole.Assistant
                ? new AssistantChatMessage(turn.Content)
                : new UserChatMessage(turn.Content));
        return CompleteChatAsync(messages, cancellationToken);
    }

    private async Task<LlmResponse> CompleteChatAsync(
        IList<ChatMessage> messages, CancellationToken cancellationToken)
    {
        // MaxOutputTokenCount serialises as `max_tokens`.
        // o-series models reject that parameter and require `max_completion_tokens` instead,
        // which Azure.AI.OpenAI 2.x does not expose as a typed property.
        // Omitting it lets the deployment's own default cap apply — important for the agentic
        // arm, whose turns return the WHOLE edited file and must not be capped at 1024 tokens.
        var options = new ChatCompletionOptions
        {
            Temperature = _config.Temperature,
        };

        var response   = await _chatClient.CompleteChatAsync(messages, options, cancellationToken);
        var completion = response.Value;

        return new LlmResponse
        {
            Content      = completion.Content[0].Text,
            InputTokens  = completion.Usage.InputTokenCount,
            OutputTokens = completion.Usage.OutputTokenCount
        };
    }
}
