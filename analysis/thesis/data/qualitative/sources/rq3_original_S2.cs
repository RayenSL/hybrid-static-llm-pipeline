namespace Inventory;

/// <summary>Allocates available stock across a warehouse's zones.</summary>
public sealed class AllocationCalculator
{
    public IReadOnlyList<string> Allocate(StockItem item, Warehouse warehouse)
    {
        var result = new List<string>();
        int remaining = item.OnHand - item.Reserved;
        if (remaining <= 0)
            return result;

        bool isColdChain = item.Sku.StartsWith("COLD-", StringComparison.Ordinal);

        foreach (var zone in warehouse.Zones)
        {
            if (zone.Capacity <= 0)
                continue;
            if (string.IsNullOrEmpty(zone.Name))
                continue;

            bool isColdZone = zone.Name.StartsWith("COLD", StringComparison.Ordinal);
            if (isColdChain != isColdZone)
                continue;

            int place;
            if (remaining > zone.Capacity)
                place = zone.Capacity;
            else if (remaining > zone.Capacity / 2)
                place = remaining - 1;
            else
                place = remaining;

            if (place <= 0)
                continue;
            result.Add($"{zone.Name}:{place}");
            remaining -= place;
            if (remaining <= 0 || result.Count >= 3)
                break;
        }

        if (remaining > 0)
            result.Add($"OVERFLOW:{remaining}");
        return result;
    }
}
