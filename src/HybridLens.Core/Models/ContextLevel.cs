namespace HybridLens.Core.Models;

public enum ContextLevel
{
    /// <summary>Code fragment only.</summary>
    Minimal,

    /// <summary>Code fragment + symbol name, file, line, anti-pattern type, metrics.</summary>
    Structural,

    /// <summary>Structural + surrounding lines + enclosing class member summary.</summary>
    Relational,

    /// <summary>Relational + project metadata + other findings in the same file.</summary>
    Full
}
