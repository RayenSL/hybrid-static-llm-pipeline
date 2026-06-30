# Context Level 3 — Relational

**Anti-pattern:** Long Method — `OrderImporter.ImportBatch` (LM-01, Ordering project)
**What this level adds over Structural:** a `## Class member summary` and a `## Surrounding code`
window.

For this instance these two additions carry the most important structural fact in the whole
prompt: **`OrderImporter` has exactly three members** — one field, one constructor, and
`ImportBatch`. The class itself is well-scoped (it does one thing: import batches). The method
is the problem, not the class. The correct repair is **extract private helper methods** within
`OrderImporter`, not extract a new class.

Without this level, a model reasoning purely from the method body might suggest heavier
restructuring (splitting into `OrderParser`, `OrderValidator`, `OrderPersister`) — a
technically valid but architecturally over-engineered response for a class this small.

**Surrounding code** adds the 10 lines before and after the method declaration (lines 1–20 of
the file). These show the namespace declaration, the class opener, the field, and the
constructor — confirming at a glance that nothing else lives in this class above `ImportBatch`.

**Difference from the next level:** Level 4 (Full) adds configurable project metadata and a
list of co-located findings in the same file. For this specific file both sections are absent
in the standard corpus run (no metadata configured, no other findings in `OrderImporter.cs`).

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

## User prompt

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

## Why the member summary is the key signal here

The member summary reveals `OrderImporter` has **3 members**: a field, a constructor, and
`ImportBatch`. From this the model can infer:

- The class responsibility is already well-scoped (importing batches). No class-level split needed.
- `ImportBatch` has grown to contain all the inlining (parsing, validation, deduplication,
  type dispatch, line-item building, pricing, persistence) that originally lived in separate
  private helpers.
- The canonical repair is **extract method**: restore `ParseLine`, `ValidateRecord`,
  `Deduplicate`, `MapToOrder`, `Persist` as private helpers, making `ImportBatch` an
  orchestrator loop.

Compare what the model would see if `OrderImporter` were also a God Class with 20+ methods:
the member summary would show that, and the model might correctly suggest a class-level split
rather than method extraction. The member surface is the branching condition for repair advice.

## How the surrounding code window is generated

`SnippetContextLines = 10` (from `appsettings.json`). The finding's start line is 10
(the method declaration). So:

```
start = max(0, 10 - 1 - 10) = 0   → file line 1
end   = min(67, 10 - 1 + 10) = 19  → file line 20
```

Lines 1–20 are shown. For a method in the middle of a large file this window would reveal
the surrounding method bodies rather than the class header — useful for spotting a cluster
of related methods that should be extracted together.
