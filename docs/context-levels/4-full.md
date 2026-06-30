# Context Level 4 — Full

**Anti-pattern:** Long Method — `OrderImporter.ImportBatch` (LM-01, Ordering project)
**What this level adds over Relational:** two conditionally-present sections:

1. **`## Project metadata`** — arbitrary key-values from `Context.Metadata` in `appsettings.json`.
   The section is **omitted entirely** when `Metadata` is empty (the default). Populated below
   for illustration.

2. **`## Other findings in the same file`** — other anti-patterns found by the static analyser in
   the same `.cs` file. For `OrderImporter.cs` the corpus run produces no co-located findings
   (the class is clean apart from `ImportBatch`), so this section is also **absent in the
   standard run**. It is shown below with a hypothetical example to demonstrate its format and
   significance.

**Why co-located findings change everything for Long Method:**
If `OrderImporter` were *also* a God Class (say it had grown to 30 methods over time), the
`## Other findings` block would show:

```
  - [GodClass] Ordering.OrderImporter (line 4)
```

That single line flips the recommended repair from "extract private helpers" to "extract
collaborator classes" — the class-level restructuring becomes necessary before the method
can be usefully split. Without this information the model's repair suggestion may be
technically correct but architecturally at the wrong granularity.

---

## System prompt *(identical across all four levels)*

```
You are a .NET code quality expert. You will be given a code anti-pattern finding.

Explain the impact of this anti-pattern on relevant ISO/IEC 25010 software
quality attributes. Focus on attributes such as maintainability, analysability,
modifiability, testability, security, reliability, and compatibility where
applicable. Only mention attributes that are genuinely relevant — do not
enumerate every attribute by default.

Respond ONLY with a JSON object in this exact format, with no additional text:
{
  "explanation": "<why this is a problem and what its impact is>",
  "quality_impact": "Quality impact:\n- Attribute: short explanation\n- Attribute: short explanation",
  "remediation": "<concrete refactoring steps; include a short code example where helpful>"
}
```

---

## User prompt *(both optional sections populated for illustration)*

In the standard corpus run both sections below are absent for this file.
`## Project metadata` requires entries under `Context.Metadata` in `appsettings.json`;
`## Other findings in the same file` requires at least one additional finding in `OrderImporter.cs`.

```
## Finding
Anti-pattern : LongMethod
Severity     : Critical
Symbol       : OrderImporter.ImportBatch
Location     : corpus/src/Ordering/OrderImporter.cs:10

## Metrics
  CyclomaticComplexity: 17
  LinesOfCode: 58
  MaxCyclomaticComplexity: 10
  MaxLinesOfCode: 50

## Project metadata
  Framework: .NET 8
  Project: Ordering

## Other findings in the same file
  - [GodClass] Ordering.OrderImporter (line 4)

## Class member summary (up to 30 members)
  private readonly OrderRepository _repository;
  public OrderImporter(OrderRepository repository) => _repository = repository;
  public IReadOnlyList<Order> ImportBatch(IEnumerable<string> rows)

## Surrounding code
```csharp
    1: namespace Ordering;
    2: 
    3: /// <summary>Imports orders from a batch of delimited rows.</summary>
    4: public sealed class OrderImporter
    5: {
    6:     private readonly OrderRepository _repository;
    7: 
    8:     public OrderImporter(OrderRepository repository) => _repository = repository;
    9: 
   10:     public IReadOnlyList<Order> ImportBatch(IEnumerable<string> rows)
   11:     {
   12:         var imported = new List<Order>();
   13:         var seen = new HashSet<string>(StringComparer.Ordinal);
   14:         foreach (var row in rows)
   15:         {
   16:             if (string.IsNullOrWhiteSpace(row))
   17:                 continue;
   18:             var parts = row.Split(',');
   19:             if (parts.Length < 4)
   20:                 continue;
```

## Code
```csharp
    public IReadOnlyList<Order> ImportBatch(IEnumerable<string> rows)
    {
        var imported = new List<Order>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var row in rows)
        {
            if (string.IsNullOrWhiteSpace(row))
                continue;
            var parts = row.Split(',');
            if (parts.Length < 4)
                continue;

            var recordType = parts[0].Trim();
            var reference = parts[1].Trim();
            if (reference.Length == 0)
                continue;
            if (!seen.Add(reference))
                continue;

            Order order;
            switch (recordType)
            {
                case "H":
                case "ORDER":
                    order = new Order { Reference = reference, Channel = OrderChannel.Web };
                    break;
                case "M":
                    order = new Order { Reference = reference, Channel = OrderChannel.Marketplace };
                    break;
                default:
                    continue;
            }

            for (int i = 2; i + 1 < parts.Length; i += 2)
            {
                var sku = parts[i].Trim();
                if (sku.Length == 0)
                    continue;
                if (!int.TryParse(parts[i + 1], out var qty) || qty <= 0)
                    continue;

                decimal price = 0m;
                if (sku.StartsWith("PRM", StringComparison.Ordinal) && qty > 10)
                    price = 9.99m;
                else if (sku.StartsWith("STD", StringComparison.Ordinal))
                    price = 4.99m;

                order.Lines.Add(new OrderLine { Sku = sku, Quantity = qty, UnitPrice = price });
            }

            if (order.Lines.Count == 0)
                continue;

            _repository.Add(order);
            imported.Add(order);
        }
        return imported;
    }
```
```

---

## Cumulative diff: what each level adds

| Section | Minimal | Structural | Relational | Full |
|---|:---:|:---:|:---:|:---:|
| `Anti-pattern: LongMethod` (bare label) | ✓ | — | — | — |
| `## Finding` header (symbol, path, severity) | — | ✓ | ✓ | ✓ |
| `## Metrics` (CC/LOC + thresholds) | — | ✓ | ✓ | ✓ |
| `## Project metadata` (configurable) | — | — | — | ✓ (if set) |
| `## Other findings in same file` | — | — | — | ✓ (if any) |
| `## Class member summary` (≤30 signatures) | — | — | ✓ | ✓ |
| `## Surrounding code` (±10 lines) | — | — | ✓ | ✓ |
| `## Code` (method body, Roslyn snippet) | ✓ | ✓ | ✓ | ✓ |

## The repair-strategy decision tree enabled by context

```
Level 1 — code only
  → Model sees a long method. Repair: extract something (vague).

Level 2 — + metrics
  → CC=17, LOC=58. Quantified complexity. Repair: extract helpers to reduce paths.
    Still vague about scope (helpers in-class vs. new classes).

Level 3 — + member summary + surroundings
  → Class has 3 members. The class is lean; method inlined too much.
    Repair: extract private helpers (ParseLine, ValidateRecord, …) within this class.
    Precise, correctly scoped.

Level 4 — + co-located findings
  → If [GodClass] also present: extract-class first, then extract-method.
    If no co-located findings (real corpus run): same as Level 3.
    The co-located signal is the branching condition for repair granularity.
```

## Configuring project metadata

```json
// appsettings.json
"Context": {
  "Level": "Full",
  "Metadata": {
    "Framework": ".NET 8",
    "Project": "Ordering",
    "Domain": "e-commerce batch import"
  }
}
```

Injected verbatim into every Full-level prompt. Keep values short — they cost tokens on
every LLM call and are repeated across all findings.
