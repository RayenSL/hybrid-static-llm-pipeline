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

        bool isColdChainItem = item.Sku?.StartsWith("COLD-", StringComparison.Ordinal) == true;

        foreach (var zone in warehouse.Zones)
        {
            if (zone.Capacity <= 0)
                continue;
            if (string.IsNullOrEmpty(zone.Name))
                continue;

            bool isColdChainZone = zone.Name.StartsWith("COLD", StringComparison.Ordinal);
            if (isColdChainItem != isColdChainZone)
                continue;
            int place = CalculatePlacement(remaining, zone.Capacity);
            if (place <= 0)
                continue;

            result.Add($"{zone.Name}:{place}");
            remaining -= place;
            if ((remaining <= 0 && result.Count > 0) || result.Count >= 3)
                break;
        }

        if (remaining > 0)
            result.Add($"OVERFLOW:{remaining}");
        return result;
    }

    private static int CalculatePlacement(int remaining, int capacity)
    {
        if (remaining > capacity)
            return capacity;
        if (remaining > capacity / 2)
            return remaining - 1;
        return remaining;
    }
}
