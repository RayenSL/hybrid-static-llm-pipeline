using System.CommandLine;
using HybridLens.CLI.Commands;
using HybridLens.Core.Configuration;
using HybridLens.StaticAnalysis.Workspace;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;

var configuration = new ConfigurationBuilder()
    .SetBasePath(AppContext.BaseDirectory)
    .AddJsonFile("appsettings.json", optional: false)
    .AddJsonFile("appsettings.local.json", optional: true)   // local overrides, git-ignored
    .Build();

var services = new ServiceCollection()
    .AddSingleton(configuration.GetSection("Detectors").Get<DetectorConfig>() ?? new DetectorConfig())
    .AddSingleton(configuration.GetSection("Context").Get<ContextConfig>() ?? new ContextConfig())
    .AddSingleton(configuration.GetSection("Llm").Get<LlmConfig>() ?? new LlmConfig())
    .AddSingleton<WorkspaceLoader>()
    .BuildServiceProvider();

var root = new RootCommand("HybridLens — hybrid static + LLM .NET code analyser")
{
    AnalyseCommand.Build(services)
};

return await root.Parse(args).InvokeAsync();
