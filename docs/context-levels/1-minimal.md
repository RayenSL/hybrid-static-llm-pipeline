# Context Level 1 — Minimal

**Anti-pattern:** Long Method — `OrderImporter.ImportBatch` (LM-01, Ordering project)
**What this level sends:** just the anti-pattern type label + the raw method body extracted by Roslyn (`method.ToFullString()`). Nothing else.

The model sees 58 lines of code and is told it's a Long Method. It does not know:
- the method's name or containing class
- the exact CC/LOC values (it would have to count itself)
- whether this is the *only* real method in the class (changes the repair strategy completely)
- where in the project this file lives

**Why this matters for Long Method specifically:** unlike God Class (where the snippet is the
whole class), the Long Method snippet is *just one method body*. The model is handed the
problem in a vacuum — it cannot see whether the class has 1 method or 20, which is often the
deciding factor between "extract method" and "split into collaborators".

**Difference from the next level:** Level 2 (Structural) adds the symbol name, file path,
severity, and the computed CC/LOC values with their configured thresholds.

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
Anti-pattern: LongMethod

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

## What the model does NOT know at this level

| Information | Available? |
|---|---|
| Method name / containing class | No — not even the method name is shown |
| File path or project | No |
| Severity | No |
| CC = 17 (threshold > 10) | No — must count decision points manually |
| LOC = 58 (threshold > 50) | No — must count lines manually |
| Class has only 3 members total | No — critical for repair strategy |
| Whether containing class is also a God Class | No |

The model can observe that the code handles parsing, validation, deduplication, record
type dispatch, line-item building, pricing, and persistence — all in one loop. It can flag
this as a Long Method. But it cannot know whether the right fix is "extract private helpers
within this class" or "split responsibilities into separate classes" — that depends on the
class structure, which is hidden at this level.
