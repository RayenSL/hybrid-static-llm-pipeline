namespace Inventory;

/// <summary>Allocates available stock across a warehouse's zones.</summary>
public sealed class AllocationCalculator
{
    public IReadOnlyList<string> Allocate(StockItem item, Warehouse warehouse)
    {
        var result = new List<string>();
        string sku = item.Sku?.Trim() ?? "";
        if (sku.Length == 0)
            return result;

        int remaining = item.OnHand - item.Reserved;
        if (remaining <= 0)
            return result;

        bool isColdChainItem = sku.StartsWith("COLD-", StringComparison.OrdinalIgnoreCase);
        var usedZoneNames = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        foreach (var zone in warehouse.Zones)
        {
            AllocateToZone(zone, isColdChainItem, usedZoneNames, result, ref remaining);
            if (remaining <= 0 || result.Count >= 3)
                break;
        }

        if (remaining > 0)
            result.Add($"OVERFLOW:{remaining}");
        return result;
    }

    private static void AllocateToZone(
        Zone zone,
        bool isColdChainItem,
        HashSet<string> usedZoneNames,
        List<string> result,
        ref int remaining)
    {
        string zoneName = zone.Name?.Trim() ?? "";
        if (zoneName.Length == 0)
            return;
        if (!usedZoneNames.Add(zoneName))
            return;
        if (zone.Capacity <= 0)
            return;

        bool isColdZone = zoneName.StartsWith("COLD", StringComparison.OrdinalIgnoreCase);
        if (isColdChainItem != isColdZone)
            return;

        int place = CalculatePlacement(remaining, zone.Capacity);
        if (place <= 0)
            return;

        result.Add($"{zoneName}:{place}");
        remaining -= place;
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
