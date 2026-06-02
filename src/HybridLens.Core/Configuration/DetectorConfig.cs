namespace HybridLens.Core.Configuration;

public sealed class DetectorConfig
{
    public GodClassConfig GodClass { get; set; } = new();
    public LongMethodConfig LongMethod { get; set; } = new();
    public ObsoleteApiConfig ObsoleteApi { get; set; } = new();
}

/// <summary>
/// God Class detection follows the composite strategy of Lanza &amp; Marinescu (2006):
/// a class is flagged iff (ATFD &gt; FEW) ∧ (WMC ≥ VERY_HIGH) ∧ (TCC &lt; 1/3),
/// all three holding simultaneously. The defaults are the statistically-derived
/// thresholds from their reference corpus.
/// </summary>
public sealed class GodClassConfig
{
    /// <summary>FEW bound for Access To Foreign Data. ATFD must strictly exceed this. Lanza &amp; Marinescu FEW ∈ [2,5].</summary>
    public int AtfdFew { get; set; } = 4;

    /// <summary>VERY_HIGH bound for Weighted Method Count. WMC must be ≥ this. Lanza &amp; Marinescu derive ~47.</summary>
    public int WmcVeryHigh { get; set; } = 47;

    /// <summary>Cohesion bound. TCC must be strictly below this (Lanza &amp; Marinescu use 1/3).</summary>
    public double TccThreshold { get; set; } = 1.0 / 3.0;
}

/// <summary>
/// Long Method detection uses cyclomatic complexity as the primary gate
/// (McCabe 1976; Watson &amp; McCabe 1996). A method is flagged when its CC exceeds
/// <see cref="MaxCyclomaticComplexity"/>; lines-of-code is a secondary signal that
/// only escalates severity (Critical when LOC is also exceeded, otherwise Warning).
/// </summary>
public sealed class LongMethodConfig
{
    /// <summary>Primary gate. A method is flagged when CC strictly exceeds this. 10 = low-risk boundary; up to 15 defensible.</summary>
    public int MaxCyclomaticComplexity { get; set; } = 10;

    /// <summary>Secondary signal. When LOC also exceeds this, the finding is escalated to Critical.</summary>
    public int MaxLinesOfCode { get; set; } = 50;
}

public sealed class ObsoleteApiConfig
{
    /// <summary>Additional namespace prefixes to flag beyond [Obsolete] attribute detection.</summary>
    public IList<string> DeprecatedNamespacePrefixes { get; set; } = [];
}
