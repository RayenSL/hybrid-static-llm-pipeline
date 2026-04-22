using HybridLens.Core.Models;
using Microsoft.CodeAnalysis;

namespace HybridLens.StaticAnalysis.Abstractions;

public interface IDetector
{
    AntiPatternType Type { get; }
    IEnumerable<Finding> Detect(Compilation compilation);
}
