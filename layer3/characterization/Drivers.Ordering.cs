namespace Characterization;
using System.Globalization;
using System.Text;
using Ordering;

internal static class OrderingDrivers
{
    public static readonly (string Key, System.Func<string> Drive)[] All = new (string, System.Func<string>)[]
    {
        ("Ordering.OrderProcessor", OrderProcessor),
        ("Ordering.CheckoutCoordinator", CheckoutCoordinator),
        ("Ordering.ReturnsHandler", ReturnsHandler),
        ("OrderImporter.ImportBatch", OrderImporter_ImportBatch),
        ("PricingRules.ApplyAdjustments", PricingRules_ApplyAdjustments),
        ("LabelPrinter.Print", LabelPrinter_Print),
    };

    // ---- helpers ----

    static string Inv(decimal d) => d.ToString(CultureInfo.InvariantCulture);
    static string Inv(bool b) => b ? "true" : "false";

    static Order MakeOrder(string reference, OrderChannel channel, decimal? discountOverride, params (string Sku, int Qty, decimal Price)[] lines)
    {
        var order = new Order { Reference = reference, Channel = channel, DiscountOverride = discountOverride };
        foreach (var (sku, qty, price) in lines)
            order.Lines.Add(new OrderLine { Sku = sku, Quantity = qty, UnitPrice = price });
        return order;
    }

    static Customer MakeCustomer(string name, CustomerTier tier, string countryCode, string city, string postal)
        => new Customer
        {
            Name = name,
            Tier = tier,
            Address = new Address { CountryCode = countryCode, City = city, PostalCode = postal },
        };

    static void AppendList(StringBuilder sb, string label, IReadOnlyList<string> items)
    {
        sb.Append(label).Append('=');
        for (int i = 0; i < items.Count; i++)
        {
            if (i > 0) sb.Append(',');
            sb.Append(items[i]);
        }
        sb.Append('\n');
    }

    // ---- OrderProcessor (God Class) ----

    static string OrderProcessor()
    {
        var proc = new Ordering.OrderProcessor(new ParcelShipper());
        var sb = new StringBuilder();

        // Scenario A: standard GB customer, mixed lines, above minimum.
        var custA = MakeCustomer("Alice", CustomerTier.Standard, "GB", "London", "SW1A1AA");
        var orderA = MakeOrder("A1", OrderChannel.Web, null,
            ("SKU1", 3, 20m), ("SKU2", 2, 300m));
        sb.Append("A.validate="); AppendJoined(sb, proc.ValidateOrder(orderA, custA)); sb.Append('\n');
        sb.Append("A.meetsMin=").Append(Inv(proc.MeetsMinimum(orderA))).Append('\n');
        sb.Append("A.checkAddr=").Append(Inv(proc.CheckAddress(custA.Address))).Append('\n');
        sb.Append("A.tax=").Append(Inv(proc.ComputeTax(orderA, custA))).Append('\n');
        sb.Append("A.duty=").Append(Inv(proc.EstimateDuty(orderA, custA))).Append('\n');
        sb.Append("A.classify=").Append(proc.Classify(orderA, custA)).Append('\n');
        sb.Append("A.discount=").Append(Inv(proc.ApplyDiscount(orderA, custA))).Append('\n');
        sb.Append("A.service=").Append(proc.SelectService(custA)).Append('\n');
        AppendList(sb, "A.manifest", proc.BuildManifest(orderA));
        sb.Append("A.dispatch=").Append(proc.Dispatch(orderA, custA)).Append('\n');
        sb.Append("A.dispatchDup=").Append(proc.Dispatch(orderA, custA)).Append('\n');

        // Scenario B: wholesale FR customer, big-qty line, marketplace channel.
        var custB = MakeCustomer("Bob", CustomerTier.Wholesale, "FR", "Paris", "75001");
        var orderB = MakeOrder("B1", OrderChannel.Marketplace, 5m,
            ("BULK", 60, 30m), ("SMALL", 25, 2m));
        sb.Append("B.validate="); AppendJoined(sb, proc.ValidateOrder(orderB, custB)); sb.Append('\n');
        sb.Append("B.tax=").Append(Inv(proc.ComputeTax(orderB, custB))).Append('\n');
        sb.Append("B.duty=").Append(Inv(proc.EstimateDuty(orderB, custB))).Append('\n');
        sb.Append("B.classify=").Append(proc.Classify(orderB, custB)).Append('\n');
        sb.Append("B.discount=").Append(Inv(proc.ApplyDiscount(orderB, custB))).Append('\n');
        sb.Append("B.service=").Append(proc.SelectService(custB)).Append('\n');
        AppendList(sb, "B.manifest", proc.BuildManifest(orderB));
        sb.Append("B.dispatch=").Append(proc.Dispatch(orderB, custB)).Append('\n');

        // Scenario C: blocked customer, blocked destination, empty order.
        var custC = MakeCustomer("Carol", CustomerTier.Blocked, "KP", "Pyongyang", "");
        var orderC = MakeOrder("C1", OrderChannel.Phone, null);
        sb.Append("C.validate="); AppendJoined(sb, proc.ValidateOrder(orderC, custC)); sb.Append('\n');
        sb.Append("C.checkAddr=").Append(Inv(proc.CheckAddress(custC.Address))).Append('\n');
        sb.Append("C.service=").Append(proc.SelectService(custC)).Append('\n');
        sb.Append("C.classify=").Append(proc.Classify(orderC, custC)).Append('\n');
        AppendList(sb, "C.manifest", proc.BuildManifest(orderC));
        sb.Append("C.dispatch=").Append(proc.Dispatch(orderC, custC)).Append('\n');

        // Scenario D: US zero-rate, high-value line to exercise tax surcharge + high-value classify.
        var custD = MakeCustomer("Dan", CustomerTier.Standard, "US", "NYC", "10001");
        var orderD = MakeOrder("D1", OrderChannel.Web, null,
            ("HV", 5, 1500m));
        sb.Append("D.tax=").Append(Inv(proc.ComputeTax(orderD, custD))).Append('\n');
        sb.Append("D.resolveRate=").Append(Inv(proc.ResolveRate("XX"))).Append('\n');
        sb.Append("D.rounding=").Append(Inv(proc.ApplyRounding(-5m))).Append('\n');
        sb.Append("D.classify=").Append(proc.Classify(orderD, custD)).Append('\n');

        sb.Append("dispatchedCount=").Append(proc.DispatchedCount);
        return sb.ToString();
    }

    static void AppendJoined(StringBuilder sb, IReadOnlyList<string> items)
    {
        sb.Append('[');
        for (int i = 0; i < items.Count; i++)
        {
            if (i > 0) sb.Append(';');
            sb.Append(items[i]);
        }
        sb.Append(']');
    }

    // ---- CheckoutCoordinator (God Class) ----

    static string CheckoutCoordinator()
    {
        var cc = new Ordering.CheckoutCoordinator();
        var sb = new StringBuilder();

        // Scenario A: standard web customer, full flow begin -> advance -> complete.
        var custA = MakeCustomer("Alice", CustomerTier.Standard, "GB", "London", "SW1A1AA");
        var orderA = MakeOrder("A1", OrderChannel.Web, null,
            ("SKU1", 3, 20m), ("SKU2", 12, 5m));
        sb.Append("A.begin=").Append(cc.BeginCheckout(orderA, custA)).Append('\n');
        sb.Append("A.advPay=").Append(Inv(cc.AdvanceStep("pay"))).Append('\n');
        sb.Append("A.advPayDup=").Append(Inv(cc.AdvanceStep("pay"))).Append('\n');
        sb.Append("A.advEmpty=").Append(Inv(cc.AdvanceStep("  "))).Append('\n');
        sb.Append("A.priceOrder=").Append(Inv(cc.PriceOrder(orderA))).Append('\n');
        sb.Append("A.summarise=").Append(Inv(cc.SummariseCharges(orderA, custA))).Append('\n');
        sb.Append("A.tender=").Append(cc.ResolveTender(orderA, custA)).Append('\n');
        AppendList(sb, "A.fulfil", cc.ScheduleFulfilment(orderA));
        sb.Append("A.complete=").Append(cc.CompleteCheckout(orderA, custA)).Append('\n');
        sb.Append("A.stepCount=").Append(cc.StepCount.ToString(CultureInfo.InvariantCulture)).Append('\n');

        // Scenario B: wholesale marketplace with discount override + promo.
        var cc2 = new Ordering.CheckoutCoordinator();
        var custB = MakeCustomer("Bob", CustomerTier.Wholesale, "FR", "Paris", "75001");
        var orderB = MakeOrder("B1", OrderChannel.Marketplace, 10m,
            ("BULK", 120, 8m), ("MED", 15, 4m));
        sb.Append("B.begin=").Append(cc2.BeginCheckout(orderB, custB)).Append('\n');
        sb.Append("B.priceOrder=").Append(Inv(cc2.PriceOrder(orderB))).Append('\n');
        sb.Append("B.summarise=").Append(Inv(cc2.SummariseCharges(orderB, custB))).Append('\n');
        sb.Append("B.validatePromoVIP=").Append(Inv(cc2.ValidatePromo("VIP"))).Append('\n');
        sb.Append("B.validatePromoTMP=").Append(Inv(cc2.ValidatePromo("TMP9"))).Append('\n');
        sb.Append("B.validatePromoBad=").Append(Inv(cc2.ValidatePromo("XY"))).Append('\n');
        sb.Append("B.promoVIP=").Append(Inv(cc2.ApplyPromo(orderB, "VIP"))).Append('\n');
        sb.Append("B.promoDup=").Append(Inv(cc2.ApplyPromo(orderB, "WELCOME"))).Append('\n');
        sb.Append("B.tender=").Append(cc2.ResolveTender(orderB, custB)).Append('\n');
        AppendList(sb, "B.fulfil", cc2.ScheduleFulfilment(orderB));
        sb.Append("B.complete=").Append(cc2.CompleteCheckout(orderB, custB)).Append('\n');

        // Scenario C: phone channel, complete without begin, audit trail.
        var cc3 = new Ordering.CheckoutCoordinator();
        var custC = MakeCustomer("Carol", CustomerTier.Standard, "DE", "Berlin", "10115");
        var orderC = MakeOrder("C1", OrderChannel.Phone, null,
            ("P", 2, 300m));
        sb.Append("C.completeNoStart=").Append(cc3.CompleteCheckout(orderC, custC)).Append('\n');
        sb.Append("C.tender=").Append(cc3.ResolveTender(orderC, custC)).Append('\n');
        sb.Append("C.summarise=").Append(Inv(cc3.SummariseCharges(orderC, custC))).Append('\n');
        cc3.RecordAudit("C1: checkout opened");
        cc3.RecordAudit("Z9: unrelated");
        cc3.RecordAudit("");
        AppendList(sb, "C.audit", cc3.AuditTrail(orderC));
        AppendList(sb, "C.fulfil", cc3.ScheduleFulfilment(orderC));

        // Scenario D: blocked customer / empty order edge cases.
        var cc4 = new Ordering.CheckoutCoordinator();
        var custD = MakeCustomer("Dan", CustomerTier.Blocked, "GB", "Leeds", "LS11AA");
        var orderD = MakeOrder("D1", OrderChannel.Web, null);
        sb.Append("D.begin=").Append(cc4.BeginCheckout(orderD, custD)).Append('\n');
        sb.Append("D.beginEmpty=").Append(cc4.BeginCheckout(MakeOrder("", OrderChannel.Web, null), custD)).Append('\n');
        sb.Append("D.tender=").Append(cc4.ResolveTender(orderD, custD)).Append('\n');
        AppendList(sb, "D.audit", cc4.AuditTrail(orderD));

        return sb.ToString();
    }

    // ---- ReturnsHandler (God Class) ----

    static string ReturnsHandler()
    {
        var rh = new Ordering.ReturnsHandler();
        var sb = new StringBuilder();

        // Scenario A: standard returnable order, refund + log + restock + duplicate.
        var custA = MakeCustomer("Alice", CustomerTier.Standard, "GB", "London", "SW1A1AA");
        var orderA = MakeOrder("A1", OrderChannel.Web, null,
            ("SKU1", 60, 10m), ("SKU2", 15, 5m), ("SKU3", 5, 2m), ("SKU4", 1, 1m));
        sb.Append("A.returnable=").Append(Inv(rh.IsReturnable(orderA))).Append('\n');
        sb.Append("A.refund=").Append(Inv(rh.ComputeRefund(orderA))).Append('\n');
        rh.LogRefund(orderA, rh.ComputeRefund(orderA));
        sb.Append("A.process=").Append(rh.ProcessReturn(orderA, custA)).Append('\n');
        sb.Append("A.restock=").Append(rh.Restock(orderA).ToString(CultureInfo.InvariantCulture)).Append('\n');
        sb.Append("A.processDup=").Append(rh.ProcessReturn(orderA, custA)).Append('\n');
        sb.Append("A.returnableAfter=").Append(Inv(rh.IsReturnable(orderA))).Append('\n');

        // Scenario B: quantity too high (>100) short-circuits ProcessReturn.
        var custB = MakeCustomer("Bob", CustomerTier.Standard, "FR", "Paris", "75001");
        var orderB = MakeOrder("B1", OrderChannel.Web, null,
            ("BIG", 150, 3m));
        sb.Append("B.returnable=").Append(Inv(rh.IsReturnable(orderB))).Append('\n');
        sb.Append("B.process=").Append(rh.ProcessReturn(orderB, custB)).Append('\n');
        sb.Append("B.refund=").Append(Inv(rh.ComputeRefund(orderB))).Append('\n');

        // Scenario C: blocked customer.
        var custC = MakeCustomer("Carol", CustomerTier.Blocked, "DE", "Berlin", "10115");
        var orderC = MakeOrder("C1", OrderChannel.Web, null,
            ("SKU5", 3, 4m));
        sb.Append("C.process=").Append(rh.ProcessReturn(orderC, custC)).Append('\n');

        // Scenario D: missing reference / empty order + refund log branches.
        var custD = MakeCustomer("Dan", CustomerTier.Standard, "GB", "Leeds", "LS11AA");
        var orderD = MakeOrder("", OrderChannel.Web, null,
            ("SKU6", 2, 5m));
        sb.Append("D.processNoRef=").Append(rh.ProcessReturn(orderD, custD)).Append('\n');
        var orderE = MakeOrder("E1", OrderChannel.Web, null);
        sb.Append("D.processEmpty=").Append(rh.ProcessReturn(orderE, custD)).Append('\n');
        var rh2 = new Ordering.ReturnsHandler();
        rh2.LogRefund(orderA, 200m);   // >100 branch
        rh2.LogRefund(orderA, 75m);    // >50 branch
        rh2.LogRefund(orderA, 25m);    // >10 branch
        rh2.LogRefund(orderA, 5m);     // small branch
        rh2.LogRefund(orderA, 0m);     // ignored
        sb.Append("D.refundLargeQty=").Append(Inv(rh2.ComputeRefund(MakeOrder("Q", OrderChannel.Web, null, ("Q", 30, 1m))))).Append('\n');

        return sb.ToString();
    }

    // ---- OrderImporter.ImportBatch (Long Method) ----

    static string OrderImporter_ImportBatch()
    {
        var repo = new Ordering.OrderRepository();
        var importer = new Ordering.OrderImporter(repo);
        var rows = new[] { "H,REF1,PRM100,15,STD200,3", "M,REF2,STD1,5", ", , ,", "H,REF3,XYZ,2", "X,REF4,STD9,1", "H,REF1,STD5,2", "ORDER,REF5,PRM9,4,STD7,25", "H,REF6" };
        var orders = importer.ImportBatch(rows);
        var sb = new StringBuilder();
        foreach (var o in orders)
        {
            sb.Append(o.Reference).Append('|').Append(o.Channel).Append('|');
            foreach (var l in o.Lines)
                sb.Append(l.Sku).Append(':').Append(l.Quantity).Append(':').Append(l.UnitPrice.ToString(CultureInfo.InvariantCulture)).Append(';');
            sb.Append('\n');
        }
        sb.Append("repoCount=").Append(repo.Count).Append('\n');
        sb.Append("empty=").Append(new OrderImporter(new OrderRepository()).ImportBatch(Array.Empty<string>()).Count).Append('\n');
        sb.Append("blank=").Append(new OrderImporter(new OrderRepository()).ImportBatch(["  "]).Count).Append('\n');
        sb.Append("malformed=").Append(new OrderImporter(new OrderRepository()).ImportBatch(["H,ONLY"]).Count).Append('\n');
        sb.Append("zeroQty=").Append(new OrderImporter(new OrderRepository()).ImportBatch(["H,ZERO,STD1,0"]).Count).Append('\n');
        sb.Append("unitQty=").Append(new OrderImporter(new OrderRepository()).ImportBatch(["H,ONE,STD1,1"]).Count);
        return sb.ToString();
    }

    // ---- PricingRules.ApplyAdjustments (Long Method) ----

    static string PricingRules_ApplyAdjustments()
    {
        var pricing = new Ordering.PricingRules();
        var sb = new StringBuilder();

        // A: standard web, small subtotal (no >500 rebate).
        var a = MakeOrder("A1", OrderChannel.Web, null, ("X", 2, 50m));
        sb.Append("A=").Append(Inv(pricing.ApplyAdjustments(a, CustomerTier.Standard))).Append('\n');

        // B: wholesale marketplace, large subtotal (>500 rebate + 1.02 channel).
        var b = MakeOrder("B1", OrderChannel.Marketplace, null, ("Y", 10, 80m));
        sb.Append("B=").Append(Inv(pricing.ApplyAdjustments(b, CustomerTier.Wholesale))).Append('\n');

        // C: standard phone with discount override (+2 channel).
        var c = MakeOrder("C1", OrderChannel.Phone, 15m, ("Z", 4, 200m));
        sb.Append("C=").Append(Inv(pricing.ApplyAdjustments(c, CustomerTier.Standard))).Append('\n');

        // D: blocked tier -> early return 0.
        var d = MakeOrder("D1", OrderChannel.Web, null, ("W", 3, 100m));
        sb.Append("D=").Append(Inv(pricing.ApplyAdjustments(d, CustomerTier.Blocked))).Append('\n');

        // E: override drives result negative -> clamped to 0.
        var e = MakeOrder("E1", OrderChannel.Web, 10000m, ("V", 1, 50m));
        sb.Append("E=").Append(Inv(pricing.ApplyAdjustments(e, CustomerTier.Standard))).Append('\n');
        sb.Append("empty=").Append(Inv(pricing.ApplyAdjustments(MakeOrder("F", OrderChannel.Web, null), CustomerTier.Standard))).Append('\n');
        sb.Append("below500=").Append(Inv(pricing.ApplyAdjustments(MakeOrder("G", OrderChannel.Web, null, ("X", 1, 499m)), CustomerTier.Standard))).Append('\n');
        sb.Append("at500=").Append(Inv(pricing.ApplyAdjustments(MakeOrder("H", OrderChannel.Web, null, ("X", 1, 500m)), CustomerTier.Standard))).Append('\n');
        sb.Append("above500=").Append(Inv(pricing.ApplyAdjustments(MakeOrder("I", OrderChannel.Web, null, ("X", 1, 501m)), CustomerTier.Standard))).Append('\n');
        sb.Append("repeat=").Append(Inv(pricing.ApplyAdjustments(a, CustomerTier.Standard)));
        return sb.ToString();
    }

    // ---- LabelPrinter.Print (Obsolete API -> SMOKE) ----

    static string LabelPrinter_Print()
    {
        var printer = new Ordering.LabelPrinter();
        var order = MakeOrder("REF1", OrderChannel.Web, null, ("SKU1", 1, 10m));
        _ = printer.Print(order, "standard");
        return "EXEC_OK";
    }
}
