namespace HybridLens.Core.Models;

public enum ContextLevel
{
    /// <summary>
    /// Baseline (H1 in the thesis): no LLM call. The pipeline writes a deterministic
    /// "analyser-only" record containing the diagnostic message (anti-pattern type,
    /// location, brief metric-based reason). Used as the comparison baseline against
    /// the hybrid (LLM-grounded) conditions.
    /// </summary>
    AnalyserOnly,

    /// <summary>Code fragment only.</summary>
    Minimal,

    /// <summary>Code fragment + symbol name, file, line, anti-pattern type, metrics.</summary>
    Structural,

    /// <summary>Structural + surrounding lines + enclosing class member summary.</summary>
    Relational,

    /// <summary>Relational + project metadata + other findings in the same file.</summary>
    Full
}
 