namespace Characterization;
using System.Globalization;
using System.Text;
using Invoicing;

internal static class InvoicingDrivers
{
    public static readonly (string Key, System.Func<string> Drive)[] All = new (string, System.Func<string>)[]
    {
        ("Invoicing.BillingManager", BillingManager),
        ("Invoicing.StatementBuilder", StatementBuilder),
        ("InvoiceRenderer.Render", InvoiceRenderer_Render),
        ("VatResolver.Resolve", VatResolver_Resolve),
        ("CurrencyConverter.Convert", CurrencyConverter_Convert),
        ("PdfExporter.Export", PdfExporter_Export),
    };

    static string Inv(string n) => n; // marker helper (no-op) kept for readability

    // ── God Class → golden master: drive invoicing, tax, dunning and ledger surfaces ──
    static string BillingManager()
    {
        CultureInfo.CurrentCulture = CultureInfo.InvariantCulture;
        var bm = new Invoicing.BillingManager();
        var sb = new StringBuilder();

        var acctBiz = new Account { Id = "ACME01", Name = "Acme Ltd", BillingAddress = "1 High St", Kind = AccountKind.Business };
        var acctGov = new Account { Id = "GOV01", Name = "State Dept", BillingAddress = "", Kind = AccountKind.Government };
        var acctGovOk = new Account { Id = "GOV01", Name = "State Dept", BillingAddress = "Whitehall", Kind = AccountKind.Government };

        var inv1 = new Invoice
        {
            Number = "",
            Lines = new List<InvoiceLine>
            {
                new InvoiceLine { Description = "Widget", NetAmount = 200m, VatRate = 0.20m },
                new InvoiceLine { Description = "Gadget", NetAmount = 800m, VatRate = 0m },
            },
        };
        var inv2 = new Invoice
        {
            Number = "INV-GOV1",
            Lines = new List<InvoiceLine> { new InvoiceLine { Description = "Service", NetAmount = 500m, VatRate = 0m } },
        };

        sb.Append("create1=").Append(bm.CreateInvoice(inv1, acctBiz)).Append('\n');
        sb.Append("valid1=").Append(bm.ValidateInvoice(inv1)).Append('\n');
        sb.Append("tax1GB=").Append(bm.ComputeTax(inv1, "GB").ToString(CultureInfo.InvariantCulture)).Append('\n');
        sb.Append("taxXX=").Append(bm.ComputeTax(inv1, "XX").ToString(CultureInfo.InvariantCulture)).Append('\n');
        sb.Append("rateGB=").Append(bm.ResolveRate("GB").ToString(CultureInfo.InvariantCulture)).Append('\n');
        sb.Append("rateXX=").Append(bm.ResolveRate("XX").ToString(CultureInfo.InvariantCulture)).Append('\n');
        sb.Append("rateEmpty=").Append(bm.ResolveRate("").ToString(CultureInfo.InvariantCulture)).Append('\n');
        sb.Append("net1=").Append(bm.NetTotal(inv1).ToString(CultureInfo.InvariantCulture)).Append('\n');

        sb.Append("createGovNoPo=").Append(bm.CreateInvoice(inv2, acctGov)).Append('\n');
        sb.Append("createGovOk=").Append(bm.CreateInvoice(inv2, acctGovOk)).Append('\n');
        sb.Append("issued=").Append(bm.IssuedCount).Append('\n');

        sb.Append("rem1=").Append(bm.IssueReminder(inv1, acctBiz)).Append('\n');
        sb.Append("rem2=").Append(bm.IssueReminder(inv1, acctBiz)).Append('\n');
        sb.Append("rem3=").Append(bm.IssueReminder(inv1, acctBiz)).Append('\n');
        sb.Append("rem4=").Append(bm.IssueReminder(inv1, acctBiz)).Append('\n');
        sb.Append("remGov=").Append(bm.IssueReminder(inv2, acctGovOk)).Append('\n');
        sb.Append("level1=").Append(bm.ReminderLevel(inv1)).Append('\n');

        bm.Post(inv1, 1000m);
        bm.Post(inv1, -200m);
        sb.Append("settle=").Append(bm.Settle(inv1, 300m).ToString(CultureInfo.InvariantCulture)).Append('\n');
        sb.Append("late1=").Append(bm.ApplyLateFees(inv1, acctBiz).ToString(CultureInfo.InvariantCulture)).Append('\n');
        sb.Append("reconcile=").Append(bm.Reconcile(acctBiz)).Append('\n');
        sb.Append("balance=").Append(bm.Balance.ToString(CultureInfo.InvariantCulture));
        return sb.ToString();
    }

    // ── God Class → golden master: statement assembly, currency formatting, contact resolution ──
    static string StatementBuilder()
    {
        CultureInfo.CurrentCulture = CultureInfo.InvariantCulture;
        var bldr = new Invoicing.StatementBuilder();
        var acct = new Account { Id = "CUST123", Name = "Beta Corp", Kind = AccountKind.Business };
        var invoices = new List<Invoice>
        {
            new Invoice { Number = "A1", Lines = new List<InvoiceLine> { new InvoiceLine { NetAmount = 100m }, new InvoiceLine { NetAmount = 50m } } },
            new Invoice { Number = "",   Lines = new List<InvoiceLine> { new InvoiceLine { NetAmount = 999m } } }, // no number -> skipped
            new Invoice { Number = "A3", Lines = new List<InvoiceLine> { new InvoiceLine { NetAmount = -5m } } },   // sub<=0 -> skipped
            new Invoice { Number = "A4", Lines = new List<InvoiceLine> { new InvoiceLine { NetAmount = 250m } } },
        };

        var sb = new StringBuilder();
        sb.Append("statement=[").Append(bldr.BuildStatement(acct, invoices)).Append("]\n");
        sb.Append("summary=").Append(bldr.AppendSummary(acct)).Append('\n');
        sb.Append("amtNeg=").Append(bldr.FormatAmount(-12.5m)).Append('\n');
        sb.Append("amtZero=").Append(bldr.FormatAmount(0m)).Append('\n');
        sb.Append("amtSmall=").Append(bldr.FormatAmount(0.5m)).Append('\n');
        sb.Append("amtK=").Append(bldr.FormatAmount(2500m)).Append('\n');
        sb.Append("amtM=").Append(bldr.FormatAmount(3_000_000m)).Append('\n');
        sb.Append("amtStd=").Append(bldr.FormatAmount(42.75m)).Append('\n');
        sb.Append("totZero=").Append(bldr.FormatTotal(0m)).Append('\n');
        sb.Append("totMinor=").Append(bldr.FormatTotal(5m)).Append('\n');
        sb.Append("totNotable=").Append(bldr.FormatTotal(60000m)).Append('\n');
        sb.Append("totReview=").Append(bldr.FormatTotal(150000m)).Append('\n');
        sb.Append("totLarge=").Append(bldr.FormatTotal(2_000_000m)).Append('\n');
        sb.Append("contactBiz=").Append(bldr.ResolveContact(acct)).Append('\n');
        sb.Append("contactGov=").Append(bldr.ResolveContact(new Account { Id = "GOV9", Kind = AccountKind.Government })).Append('\n');
        sb.Append("contactGovX=").Append(bldr.ResolveContact(new Account { Id = "X123", Kind = AccountKind.Government })).Append('\n');
        sb.Append("contactShort=").Append(bldr.ResolveContact(new Account { Id = "ab", Kind = AccountKind.Consumer })).Append('\n');
        sb.Append("contactEmpty=").Append(bldr.ResolveContact(new Account { Id = "", Kind = AccountKind.Consumer }));
        return sb.ToString();
    }

    // ── Long Method → golden master: render across account kinds, VAT bands, discounts, truncation ──
    static string InvoiceRenderer_Render()
    {
        CultureInfo.CurrentCulture = CultureInfo.InvariantCulture;
        var r = new InvoiceRenderer();

        // Scenario A: business, std + reduced + zero-rated lines, net>1000 -> 5% discount
        var acctBiz = new Account { Id = "B1", Name = "Trade Co", Kind = AccountKind.Business };
        var invA = new Invoice
        {
            Number = "INV-R1",
            Lines = new List<InvoiceLine>
            {
                new InvoiceLine { Description = "Std item",     NetAmount = 600m, VatRate = 0.20m },
                new InvoiceLine { Description = "Reduced item", NetAmount = 500m, VatRate = 0.05m },
                new InvoiceLine { Description = "Zero item",    NetAmount = 100m, VatRate = 0m },
            },
        };

        // Scenario B: government, small net -> no discount, gov footer
        var acctGov = new Account { Id = "G1", Name = "State Dept", Kind = AccountKind.Government };
        var invB = new Invoice
        {
            Number = "INV-R2",
            Lines = new List<InvoiceLine> { new InvoiceLine { Description = "Consulting", NetAmount = 200m, VatRate = 0.20m } },
        };

        // Scenario C: consumer, net>5000 -> 10% discount, long description truncation, negative line skipped
        var acctCon = new Account { Id = "C1", Name = "Jane", Kind = AccountKind.Consumer };
        var invC = new Invoice
        {
            Number = "INV-R3",
            Lines = new List<InvoiceLine>
            {
                new InvoiceLine { Description = "This is a very long product description exceeding forty characters", NetAmount = 6000m, VatRate = 0m },
                new InvoiceLine { Description = "Refund", NetAmount = -10m, VatRate = 0.20m },
            },
        };

        var sb = new StringBuilder();
        sb.Append("=== R1 ===\n").Append(r.Render(invA, acctBiz));
        sb.Append("=== R2 ===\n").Append(r.Render(invB, acctGov));
        sb.Append("=== R3 ===\n").Append(r.Render(invC, acctCon));
        return sb.ToString();
    }

    // ── Long Method → golden master: VAT switch, account overrides, high-value cap, net<=0 guard ──
    static string VatResolver_Resolve()
    {
        CultureInfo.CurrentCulture = CultureInfo.InvariantCulture;
        var v = new VatResolver();
        var consumer = new Account { Id = "C", Kind = AccountKind.Consumer };
        var business = new Account { Id = "B", Kind = AccountKind.Business };
        var government = new Account { Id = "G", Kind = AccountKind.Government };

        var sb = new StringBuilder();
        sb.Append("nonpositive=").Append(v.Resolve(consumer, 0m, "GB").ToString(CultureInfo.InvariantCulture)).Append('\n');
        sb.Append("gbConsumer=").Append(v.Resolve(consumer, 1000m, "GB").ToString(CultureInfo.InvariantCulture)).Append('\n');
        sb.Append("frConsumer=").Append(v.Resolve(consumer, 1000m, "FR").ToString(CultureInfo.InvariantCulture)).Append('\n');
        sb.Append("deBizHalved=").Append(v.Resolve(business, 20000m, "DE").ToString(CultureInfo.InvariantCulture)).Append('\n');
        sb.Append("deBizSmall=").Append(v.Resolve(business, 5000m, "DE").ToString(CultureInfo.InvariantCulture)).Append('\n');
        sb.Append("govZero=").Append(v.Resolve(government, 5000m, "GB").ToString(CultureInfo.InvariantCulture)).Append('\n');
        sb.Append("ieCapped=").Append(v.Resolve(consumer, 150000m, "IE").ToString(CultureInfo.InvariantCulture)).Append('\n');
        sb.Append("unknown=").Append(v.Resolve(consumer, 500m, "ZZ").ToString(CultureInfo.InvariantCulture)).Append('\n');
        sb.Append("belowCap=").Append(v.Resolve(consumer, 99999m, "GB").ToString(CultureInfo.InvariantCulture)).Append('\n');
        sb.Append("atCap=").Append(v.Resolve(consumer, 100000m, "GB").ToString(CultureInfo.InvariantCulture));
        return sb.ToString();
    }

    // ── Obsolete API → smoke: Convert calls RatesV1.Lookup ([Obsolete]) internally; left as-is ──
    static string CurrencyConverter_Convert()
    {
        var c = new CurrencyConverter();
        var _ = c.Convert(100m, "EUR", "USD");
        return "EXEC_OK";
    }

    // ── Obsolete API → smoke: Export calls RenderApiV1.ToPdf ([Obsolete]) internally; left as-is ──
    static string PdfExporter_Export()
    {
        var exporter = new PdfExporter();
        var invoice = new Invoice
        {
            Number = "INV-PDF1",
            Lines = new List<InvoiceLine>
            {
                new InvoiceLine { Description = "Item A", NetAmount = 100m, VatRate = 0.20m },
                new InvoiceLine { Description = "Item B", NetAmount = 50m, VatRate = 0m },
            },
        };
        var _ = exporter.Export(invoice);
        return "EXEC_OK";
    }
}
