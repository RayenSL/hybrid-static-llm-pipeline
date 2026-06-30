# Context Level 2 — Structural

**Anti-pattern:** Long Method — `OrderImporter.ImportBatch` (LM-01, Ordering project)
**What this level adds over Minimal:** a `## Finding` header (method name, file path, severity)
and a `## Metrics` block with computed values and configured thresholds.

The model now knows:
- the method is `OrderImporter.ImportBatch` in the Ordering project
- CC = 17 against a threshold of > 10 — 70% over the limit
- LOC = 58 against a threshold of > 50 — both gates exceeded, so severity is `Critical`

It can now make grounded statements like "with cyclomatic complexity 17, this method
has 17 distinct execution paths to test". Without this level it would have to eyeball-count
the `if`/`switch`/`for` branches.

**Difference from the next level:** Level 3 (Relational) adds a flat list of every class member
and a window of source lines around the method declaration — revealing that
`ImportBatch` is the *only* real method in `OrderImporter`, which is the critical structural
fact for deciding the right refactoring strategy.

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

## What the model gains at this level (vs Minimal)

| Information | Minimal | Structural |
|---|---|---|
| Method / class name | No | `OrderImporter.ImportBatch` |
| File path | No | `corpus/src/Ordering/OrderImporter.cs:10` |
| Severity | No | `Critical` |
| CC value + threshold | Must count | 17 (threshold > 10) |
| LOC value + threshold | Must count | 58 (threshold > 50) |
| Class structure | No | **Still no** — added at Level 3 |

The metrics allow the model to say "with 17 execution paths, every branch combination
would need a unit test to achieve full coverage" — a specific, actionable claim. But the
repair suggestion is still unconstrained: without knowing the class's member surface, the
model might suggest extracting a separate `OrderParser` class when the real class has only
one method and a simple extract-method refactor is appropriate.
