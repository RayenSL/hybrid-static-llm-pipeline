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

        var client = new AzureOpenAIClient(
            new Uri(config.BaseUrl),
            new AzureKeyCredential(config.ApiKey ?? string.Empty));

        _chatClient = client.GetChatClient(config.Model);
    }

    public async Task<LlmResponse> CompleteAsync(
        LlmRequest request,
        CancellationToken cancellationToken = default)
    {
        var messages = new List<ChatMessage>
        {
            new SystemChatMessage(request.SystemPrompt),
            new UserChatMessage(request.UserPrompt)
        };

        // MaxOutputTokenCount serialises as `max_tokens`.
        // o-series models reject that parameter and require `max_completion_tokens` instead,
        // which Azure.AI.OpenAI 2.x does not expose as a typed property.
        // Omitting it lets the deployment's own default cap apply.
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
