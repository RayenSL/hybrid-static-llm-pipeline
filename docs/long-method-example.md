# lONG METHOD EXAMPLE

---

## The seeded Long Method — `Ordering/OrderImporter.cs`

`ImportBatch` **Cyclomatic complexity 17, 58 lines of code** (detection thresholds:
CC > 10, LOC > 50).

```csharp
public IReadOnlyList<Order> ImportBatch(IEnumerable<string> rows)
{
    var imported = new List<Order>();
    var seen = new HashSet<string>(StringComparer.Ordinal);
    foreach (var row in rows)
    {
        if (string.IsNullOrWhiteSpace(row)) continue;
        var parts = row.Split(',');
        if (parts.Length < 4) continue;
        var recordType = parts[0].Trim();
        var reference = parts[1].Trim();
        if (reference.Length == 0) continue;
        if (!seen.Add(reference)) continue;
        Order order;
        switch (recordType)                              // branch density
        {
            case "H": case "ORDER":
                order = new Order { Reference = reference, Channel = OrderChannel.Web }; break;
            case "M":
                order = new Order { Reference = reference, Channel = OrderChannel.Marketplace }; break;
            default: continue;
        }
        for (int i = 2; i + 1 < parts.Length; i += 2)    // nested loop + pricing rules
        {
            var sku = parts[i].Trim();
            if (sku.Length == 0) continue;
            if (!int.TryParse(parts[i + 1], out var qty) || qty <= 0) continue;
            decimal price = 0m;
            if (sku.StartsWith("PRM") && qty > 10) price = 9.99m;
            else if (sku.StartsWith("STD")) price = 4.99m;
            order.Lines.Add(new OrderLine { Sku = sku, Quantity = qty, UnitPrice = price });
        }
        if (order.Lines.Count == 0) continue;
        _repository.Add(order); imported.Add(order);
    }
    return imported;
}
```

---

## Architecture comparison

### 1. Analyser-only (baseline — detection, no repair)

The Roslyn detector flags the method and stops:

> `[LongMethod] OrderImporter.ImportBatch … lines of code = 58, cyclomatic complexity = 17.`

No language model, no fix. This is the "list of warnings a developer already receives" baseline;
its verified-repair rate is zero by construction.

### 2. Hybrid (static analysis → LLM suggestion → strict-literal application)

The detector's finding is passed to `gpt-5.6-sol`, which returns a **text repair recipe** (not code
that is executed directly):

> *"Keep `ImportBatch` as a coordinator only. Extract row parsing into `TryParseOrder`,
> record-type mapping into `TryCreateOrder`, line parsing into `ParseLines`, pricing into
> `CalculatePrice` …"* — accompanied by a worked code example.

A separate, non-evaluated applier then applies that suggestion **strictly literally** — it
implements only what the suggestion states and makes no design decisions of its own. The applied
solution compiles, and re-measuring the triggering metric shows cyclomatic complexity has dropped
below the threshold.

**Outcome: `resolved`** (applicable → builds → metric-resolved).

### 3. Agentic (ungrounded — autonomous compiler-in-the-loop)

Given only the raw, unannotated file, the agent **did detect the Long Method** (it reported it in
its findings) — but then declared itself finished **without making a single edit** (0 build
iterations). Its own stated reason, verbatim from the frozen trajectory:

> *"No edit applied because the task requires source modification through a build loop, but no
> build tool interaction is available in this context."*

It talked itself out of the task — despite having a compiler tool available. The method is left
unchanged, still at cyclomatic complexity 17.

**Outcome: `builds_unresolved`** (the pristine file compiles, but the anti-pattern remains). This
is the ungrounded failure mode in miniature: the model can *name* the problem but, without the
finding to anchor it, does not act on it.

### 4. Grounded-iterative (same loop, but seeded with the analyser's finding)

This arm uses **identical machinery** to the agentic arm — same autonomous loop, same iteration
budget, same compiler-only tool. The single difference: its opening prompt carries the analyser's
finding block. With that anchor it refactored immediately (1 iteration, 1 successful build):

> *"Refactored `ImportBatch` into smaller focused helpers: `TryParseOrder`, `TryCreateOrder`,
> `AddOrderLines`, `TryCreateOrderLine`, `DetermineUnitPrice`. This preserves behaviour while
> reducing method size and complexity, isolating parsing and pricing decisions into testable units."*

The edited solution compiles and re-measures below the complexity threshold. Notably, it
independently arrived at essentially the same extract-method structure the hybrid arm had suggested.

**Outcome: `resolved`.**

---

## Outcome

| Architecture | Action taken | Built? | Verified outcome |
|---|---|---|---|
| Analyser-only | detection only, no repair | — | no repair (baseline) |
| Hybrid | suggestion applied literally | yes | **resolved** |
| Agentic (ungrounded) | detected, then **0 edits** | (unchanged) | builds-unresolved |
| Grounded-iterative | refactored into 5 helpers (1 pass) | yes | **resolved** |

---
### Hybrid 

```csharp
public IReadOnlyList<Order> ImportBatch(IEnumerable<string> rows)
{
    var imported = new List<Order>();
    var seen = new HashSet<string>(StringComparer.Ordinal);

    foreach (var row in rows)
    {
        if (!TryParseOrder(row, seen, out var order))
            continue;

        _repository.Add(order);
        imported.Add(order);
    }

    return imported;
}

private bool TryParseOrder(string row, HashSet<string> seen, out Order order)
{
    order = null!;
    if (string.IsNullOrWhiteSpace(row))
        return false;

    var parts = row.Split(',');
    if (parts.Length < 4)
        return false;

    var recordType = parts[0].Trim();
    var reference = parts[1].Trim();
    if (reference.Length == 0 || !seen.Add(reference))
        return false;

    if (!TryCreateOrder(recordType, reference, out order))
        return false;

    foreach (var line in ParseLines(parts))
        order.Lines.Add(line);

    return order.Lines.Count > 0;
}

private bool TryCreateOrder(string recordType, string reference, out Order order)
{
    order = recordType switch
    {
        "H" or "ORDER" => new Order { Reference = reference, Channel = OrderChannel.Web },
        "M" => new Order { Reference = reference, Channel = OrderChannel.Marketplace },
        _ => null!
    };
    return order != null;
}

private IEnumerable<OrderLine> ParseLines(string[] parts)
{
    for (int i = 2; i + 1 < parts.Length; i += 2)
    {
        var sku = parts[i].Trim();
        if (sku.Length == 0)
            continue;
        if (!int.TryParse(parts[i + 1], out var qty) || qty <= 0)
            continue;

        yield return new OrderLine { Sku = sku, Quantity = qty, UnitPrice = CalculatePrice(sku, qty) };
    }
}

private decimal CalculatePrice(string sku, int qty)
{
    if (sku.StartsWith("PRM", StringComparison.Ordinal) && qty > 10)
        return 9.99m;
    if (sku.StartsWith("STD", StringComparison.Ordinal))
        return 4.99m;
    return 0m;
}
```

### Grounded-iterative 

```csharp
public IReadOnlyList<Order> ImportBatch(IEnumerable<string> rows)
{
    var imported = new List<Order>();
    var seen = new HashSet<string>(StringComparer.Ordinal);

    foreach (var row in rows)
    {
        if (!TryParseOrder(row, seen, out var order))
            continue;

        _repository.Add(order);
        imported.Add(order);
    }

    return imported;
}

private static bool TryParseOrder(string row, HashSet<string> seen, out Order order)
{
    order = null!;
    if (string.IsNullOrWhiteSpace(row))
        return false;

    var parts = row.Split(',');
    if (parts.Length < 4)
        return false;

    var recordType = parts[0].Trim();
    var reference = parts[1].Trim();
    if (reference.Length == 0 || !seen.Add(reference))
        return false;

    if (!TryCreateOrder(recordType, reference, out order))
        return false;

    AddOrderLines(parts, order);
    return order.Lines.Count > 0;
}

private static bool TryCreateOrder(string recordType, string reference, out Order order)
{
    switch (recordType)
    {
        case "H":
        case "ORDER":
            order = new Order { Reference = reference, Channel = OrderChannel.Web };
            return true;
        case "M":
            order = new Order { Reference = reference, Channel = OrderChannel.Marketplace };
            return true;
        default:
            order = null!;
            return false;
    }
}

private static void AddOrderLines(string[] parts, Order order)
{
    for (int i = 2; i + 1 < parts.Length; i += 2)
    {
        if (TryCreateOrderLine(parts[i], parts[i + 1], out var line))
            order.Lines.Add(line);
    }
}

private static bool TryCreateOrderLine(string skuPart, string quantityPart, out OrderLine line)
{
    line = null!;
    var sku = skuPart.Trim();
    if (sku.Length == 0)
        return false;

    if (!int.TryParse(quantityPart, out var qty) || qty <= 0)
        return false;

    line = new OrderLine { Sku = sku, Quantity = qty, UnitPrice = DetermineUnitPrice(sku, qty) };
    return true;
}

private static decimal DetermineUnitPrice(string sku, int qty)
{
    if (sku.StartsWith("PRM", StringComparison.Ordinal) && qty > 10)
        return 9.99m;

    if (sku.StartsWith("STD", StringComparison.Ordinal))
        return 4.99m;

    return 0m;
}
```

In both arms the single 58-line, CC-17 method becomes a coordinator plus focused helpers, none
exceeding CC 10 — so re-measuring reports the Long Method as **resolved** in each case, with the
parsing and pricing behaviour unchanged. The two decompositions differ only in style (the hybrid
applier used four helpers with a `switch` expression and a `yield` iterator; the grounded arm used
five with classic control flow) — evidence that the extract-method fix is a natural, stable target
rather than an artefact of one arm.

---
