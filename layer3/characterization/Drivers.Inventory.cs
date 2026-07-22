namespace Characterization;
using System.Globalization;
using System.Text;
using Inventory;

internal static class InventoryDrivers
{
    public static readonly (string Key, System.Func<string> Drive)[] All = new (string, System.Func<string>)[]
    {
        ("Inventory.CycleCountService", CycleCountService),
        ("Inventory.StockController", StockController),
        ("AllocationCalculator.Allocate", AllocationCalculator_Allocate),
        ("ReplenishmentPlanner.BuildPlan", ReplenishmentPlanner_BuildPlan),
        ("SnapshotWriter.Write", SnapshotWriter_Write),
        ("StockSync.Reconcile", StockSync_Reconcile),
    };

    static string I(int v) => v.ToString(CultureInfo.InvariantCulture);
    static string D(decimal v) => v.ToString(CultureInfo.InvariantCulture);

    static StockItem Item(string sku, int onHand, int reserved, int reorderPoint = 0)
        => new StockItem { Sku = sku, OnHand = onHand, Reserved = reserved, ReorderPoint = reorderPoint };

    static Warehouse Wh(string code, params (string Name, int Cap)[] zones)
    {
        var w = new Warehouse { Code = code };
        foreach (var (name, cap) in zones)
            w.Zones.Add(new Zone { Name = name, Capacity = cap });
        return w;
    }

    // ---- God Class: CycleCountService ----
    // Golden-master: drive every public method with fixed scenarios exercising the branches.
    static string CycleCountService()
    {
        var svc = new Inventory.CycleCountService();
        var wh = Wh("WH1", ("A", 100));
        var sb = new StringBuilder();

        // RecordCount: match, positive variance, negative-to-zero, large variance, invalid guards
        sb.Append("RecordCount.match=").Append(svc.RecordCount(Item("S1", 50, 0), wh, 50)).Append('\n');
        sb.Append("RecordCount.recorded=").Append(svc.RecordCount(Item("S2", 40, 0), wh, 45)).Append('\n');
        sb.Append("RecordCount.zeroed=").Append(svc.RecordCount(Item("S3", 10, 0), wh, 0)).Append('\n');
        sb.Append("RecordCount.large=").Append(svc.RecordCount(Item("S4", 0, 0), wh, 250)).Append('\n');
        sb.Append("RecordCount.invalid=").Append(svc.RecordCount(Item("S5", 5, 0), wh, -1)).Append('\n');
        sb.Append("RecordCount.nosku=").Append(svc.RecordCount(Item("", 5, 0), wh, 3)).Append('\n');
        sb.Append("RecordCount.nowh=").Append(svc.RecordCount(Item("S6", 5, 0), Wh(""), 3)).Append('\n');

        // CountVariance: relies on counts recorded above (S2 counted 45, onHand 40 -> variance 5)
        sb.Append("CountVariance.S2=").Append(I(svc.CountVariance(Item("S2", 40, 0)))).Append('\n');
        sb.Append("CountVariance.unknown=").Append(I(svc.CountVariance(Item("ZZ", 1, 0)))).Append('\n');
        sb.Append("CountVariance.nosku=").Append(I(svc.CountVariance(Item("", 1, 0)))).Append('\n');

        // Reconcile: reconciled, oversold, bad reserve, phantom
        sb.Append("Reconcile.ok=").Append(svc.Reconcile(Item("R1", 20, 5))).Append('\n');
        sb.Append("Reconcile.oversold=").Append(svc.Reconcile(Item("R2", 3, 10))).Append('\n');
        sb.Append("Reconcile.badreserve=").Append(svc.Reconcile(Item("R3", 10, -1))).Append('\n');
        sb.Append("Reconcile.phantom=").Append(svc.Reconcile(Item("R4", 0, 4))).Append('\n');

        // FlagDiscrepancy: critical, warn, info, note, guards
        sb.Append("Flag.critical=").Append(svc.FlagDiscrepancy(Item("F1", 1, 0), "oversold count")).Append('\n');
        sb.Append("Flag.warn=").Append(svc.FlagDiscrepancy(Item("F2", 1, 0), "low stock")).Append('\n');
        sb.Append("Flag.info=").Append(svc.FlagDiscrepancy(Item("F3", 1, 0), "excess units")).Append('\n');
        sb.Append("Flag.note=").Append(svc.FlagDiscrepancy(Item("F4", 1, 0), "misc")).Append('\n');
        sb.Append("Flag.noreason=").Append(svc.FlagDiscrepancy(Item("F5", 1, 0), "")).Append('\n');

        // UpdateValuation: normal, cap, zero basis, negative cost guard
        sb.Append("Valuation.normal=").Append(D(svc.UpdateValuation(Item("V1", 100, 0, 10), 3m))).Append('\n');
        sb.Append("Valuation.cap=").Append(D(svc.UpdateValuation(Item("V2", 1000000, 0), 5m))).Append('\n');
        sb.Append("Valuation.zeroqty=").Append(D(svc.UpdateValuation(Item("V3", 0, 0), 5m))).Append('\n');
        sb.Append("Valuation.negcost=").Append(D(svc.UpdateValuation(Item("V4", 10, 0), -1m)));
        return sb.ToString();
    }

    // ---- God Class: StockController ----
    // Golden-master: real DefaultSupplier dependency from the corpus; fresh items where the
    // controller mutates OnHand, to keep scenarios independent and deterministic.
    static string StockController()
    {
        var ctrl = new Inventory.StockController(new DefaultSupplier());
        var sb = new StringBuilder();

        // AdjustStock: in, out, blocked-underflow, oversold warn; then movement count
        sb.Append("Adjust.in=").Append(I(ctrl.AdjustStock(Item("A1", 10, 0), 5))).Append('\n');
        sb.Append("Adjust.out=").Append(I(ctrl.AdjustStock(Item("A2", 10, 0), -4))).Append('\n');
        sb.Append("Adjust.blocked=").Append(I(ctrl.AdjustStock(Item("A3", 3, 0), -10))).Append('\n');
        sb.Append("Adjust.zero=").Append(I(ctrl.AdjustStock(Item("A4", 7, 0), 0))).Append('\n');
        sb.Append("Adjust.oversold=").Append(I(ctrl.AdjustStock(Item("A5", 2, 20), 1))).Append('\n');
        sb.Append("MovementCount=").Append(I(ctrl.MovementCount)).Append('\n');

        // Available
        sb.Append("Available.pos=").Append(I(ctrl.Available(Item("B1", 30, 12)))).Append('\n');
        sb.Append("Available.clamped=").Append(I(ctrl.Available(Item("B2", 5, 20)))).Append('\n');

        // Reorder decisions
        sb.Append("NeedsReorder.rp=").Append(ctrl.NeedsReorder(Item("C1", 10, 3, 8))).Append('\n');
        sb.Append("NeedsReorder.default=").Append(ctrl.NeedsReorder(Item("C2", 15, 0))).Append('\n');
        sb.Append("ReorderQty.rp=").Append(I(ctrl.ReorderQuantity(Item("C1", 5, 0, 8)))).Append('\n');
        sb.Append("ReorderQty.none=").Append(I(ctrl.ReorderQuantity(Item("C3", 500, 0, 8)))).Append('\n');
        sb.Append("ResolveThreshold.default=").Append(I(ctrl.ResolveThreshold("NOPE"))).Append('\n');

        // Zone allocation
        var wh = Wh("WH", ("Z1", 5), ("Z2", 50));
        sb.Append("Allocate.first=").Append(ctrl.AllocateToZone(Item("D1", 4, 0), wh)).Append('\n');
        sb.Append("Allocate.spill=").Append(ctrl.AllocateToZone(Item("D2", 40, 0), wh)).Append('\n');
        sb.Append("Allocate.overflow=").Append(ctrl.AllocateToZone(Item("D3", 100, 0), wh)).Append('\n');
        sb.Append("Allocate.nozones=").Append(ctrl.AllocateToZone(Item("D4", 5, 0), Wh("E"))).Append('\n');
        sb.Append("Allocate.nothing=").Append(ctrl.AllocateToZone(Item("D5", 3, 3), Wh("F", ("Z", 10)))).Append('\n');
        sb.Append("ZoneSpare=").Append(I(ctrl.ZoneSpare(wh))).Append('\n');

        // Supplier ordering: place then confirm partial/full
        var po = Item("P1", 2, 0, 10);
        sb.Append("PlaceReorder.accepted=").Append(ctrl.PlaceReorder(po)).Append('\n');
        sb.Append("PlaceReorder.dupe=").Append(ctrl.PlaceReorder(po)).Append('\n');
        sb.Append("ConfirmDelivery.partial=").Append(ctrl.ConfirmDelivery(po, 5)).Append('\n');
        sb.Append("ConfirmDelivery.none=").Append(ctrl.ConfirmDelivery(Item("PX", 0, 0), 5)).Append('\n');

        // Classify
        sb.Append("Classify.oversold=").Append(ctrl.Classify(Item("G1", 1, 5))).Append('\n');
        sb.Append("Classify.out=").Append(ctrl.Classify(Item("G2", 5, 5))).Append('\n');
        sb.Append("Classify.low=").Append(ctrl.Classify(Item("G3", 10, 4, 8))).Append('\n');
        sb.Append("Classify.excess=").Append(ctrl.Classify(Item("G4", 100, 0, 5))).Append('\n');
        sb.Append("Classify.ok=").Append(ctrl.Classify(Item("G5", 20, 0, 8))).Append('\n');

        // AuditStock (serialise the ordered finding list field-by-field)
        var audit = ctrl.AuditStock(Item("H1", -1, 5), Wh("W", ("Z1", 10)));
        sb.Append("Audit=[");
        for (int i = 0; i < audit.Count; i++) { if (i > 0) sb.Append(','); sb.Append(audit[i]); }
        sb.Append("]\n");
        var clean = ctrl.AuditStock(Item("H2", 10, 2), Wh("W", ("Z1", 10)));
        sb.Append("Audit.clean=[");
        for (int i = 0; i < clean.Count; i++) { if (i > 0) sb.Append(','); sb.Append(clean[i]); }
        sb.Append("]\n");

        // ForecastDepletion
        sb.Append("Forecast.days=").Append(I(ctrl.ForecastDepletion(Item("K1", 100, 0), 10))).Append('\n');
        sb.Append("Forecast.nodemand=").Append(I(ctrl.ForecastDepletion(Item("K2", 100, 0), 0))).Append('\n');
        sb.Append("Forecast.empty=").Append(I(ctrl.ForecastDepletion(Item("K3", 5, 5), 10))).Append('\n');
        sb.Append("Forecast.cap=").Append(I(ctrl.ForecastDepletion(Item("K4", 100000, 0), 1)));
        return sb.ToString();
    }

    // ---- Long Method: AllocationCalculator.Allocate ----
    static string AllocationCalculator_Allocate()
    {
        var calc = new AllocationCalculator();
        var sb = new StringBuilder();

        void Run(string label, StockItem item, Warehouse wh)
        {
            var r = calc.Allocate(item, wh);
            sb.Append(label).Append("=[");
            for (int i = 0; i < r.Count; i++) { if (i > 0) sb.Append(','); sb.Append(r[i]); }
            sb.Append("]\n");
        }

        // Multi-zone spill; the "remaining > capacity/2 -> place remaining-1" branch fires
        Run("spread", Item("S1", 30, 0), Wh("W", ("Z1", 10), ("Z2", 8), ("Z3", 20)));
        // Nothing available
        Run("empty", Item("S2", 5, 5), Wh("W", ("Z1", 10)));
        // Overflow: capacities too small, plus a skipped zero-capacity and empty-name zone
        Run("overflow", Item("S3", 25, 0), Wh("W", ("", 100), ("Z0", 0), ("Z1", 5)));
        // Exact single-zone fit
        sb.Append("halffit=");
        var last = calc.Allocate(Item("S4", 4, 0), Wh("W", ("Z1", 10)));
        sb.Append('[');
        for (int i = 0; i < last.Count; i++) { if (i > 0) sb.Append(','); sb.Append(last[i]); }
        sb.Append(']');
        return sb.ToString();
    }

    // ---- Long Method: ReplenishmentPlanner.BuildPlan ----
    static string ReplenishmentPlanner_BuildPlan()
    {
        var planner = new ReplenishmentPlanner();
        var sb = new StringBuilder();

        void Run(string label, int season)
        {
            var items = new List<StockItem>
            {
                Item("OK", 100, 0, 10),      // available above reorder -> skipped
                Item("SMALL", 2, 0, 5),      // deficit 3 (<10) -> 10
                Item("MID", 5, 0, 60),       // deficit 55 (<100) -> 55
                Item("BIG", 0, 0, 300),      // deficit 300 -> +50 = 350 (LARGE)
                Item("NEG", -1, 0, 10),      // onHand<0 -> skipped
                Item("", 0, 0, 10),          // empty sku -> skipped after qty calc
            };
            var plan = planner.BuildPlan(items, new DefaultSupplier(), season);
            sb.Append(label).Append("=[");
            for (int i = 0; i < plan.Count; i++) { if (i > 0) sb.Append(','); sb.Append(plan[i]); }
            sb.Append("]\n");
        }

        Run("normal", 2);   // no seasonal factor
        Run("peak", 4);     // *1.5
        var winterItems = new List<StockItem> { Item("W1", 0, 0, 300) };
        var winter = planner.BuildPlan(winterItems, new DefaultSupplier(), 1); // /2
        sb.Append("winter=[");
        for (int i = 0; i < winter.Count; i++) { if (i > 0) sb.Append(','); sb.Append(winter[i]); }
        sb.Append(']');
        return sb.ToString();
    }

    // ---- Obsolete API: SnapshotWriter.Write -> smoke ----
    // Calls [Obsolete] SnapshotApiV1.Persist internally; left as-is, not migrated.
    static string SnapshotWriter_Write()
    {
        var writer = new SnapshotWriter();
        writer.Write(Item("SNAP1", 42, 0));
        writer.Write(Item("SNAP2", 0, 0));
        _ = writer.Count;
        return "EXEC_OK";
    }

    // ---- Obsolete API: StockSync.Reconcile -> smoke ----
    // Calls [Obsolete] SyncApiV1.Reconcile internally; left as-is, not migrated.
    static string StockSync_Reconcile()
    {
        var sync = new StockSync();
        _ = sync.Reconcile(Item("SYNC1", 50, 0), 45);
        _ = sync.Reconcile(Item("SYNC2", 10, 0), 10);
        return "EXEC_OK";
    }
}
