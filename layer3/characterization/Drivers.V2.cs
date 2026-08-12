namespace Characterization;

using System.Globalization;
using AccessControl;
using Claims;
using Fulfilment;
using Payments;
using ServiceDesk;
using Subscriptions;

internal static class V2Drivers
{
    public static readonly (string Key, Func<string> Drive)[] All =
    [
        ("Claims.ClaimAdjudicator.Evaluate", ClaimsCases),
        ("Payments.SettlementBatchProcessor.Process", PaymentsCases),
        ("AccessControl.AccessDecisionEngine.Decide", AccessCases),
        ("Fulfilment.FulfilmentCoordinator", FulfilmentCases),
        ("Subscriptions.SubscriptionAccountService", SubscriptionCases),
        ("ServiceDesk.CaseOperationsManager", ServiceDeskCases),
    ];

    private static string ClaimsCases()
    {
        static Claim Claim(decimal amount = 500m, string category = "damage", bool documents = true,
            bool policeReport = true, int days = 5, decimal priorPaid = 0m) =>
            new() { Reference = "C1", PolicyNumber = "P1", Category = category, ClaimedAmount = amount,
                DocumentsComplete = documents, PoliceReportPresent = policeReport, DaysAfterIncident = days,
                PriorPaidAmount = priorPaid };
        static string Show(ClaimDecision decision) =>
            $"{decision.Status}|{decision.Payable.ToString(CultureInfo.InvariantCulture)}|{string.Join(',', decision.Reasons)}";
        static ClaimDecision Run(Claim? claim, Coverage? coverage = null, int risk = 10) =>
            new ClaimAdjudicator().Evaluate(claim, new CoverageStub(coverage ?? new Coverage(true, 100m, 1000m, true)), new RiskStub(risk));

        var repeated = Run(Claim());
        return string.Join('\n',
            Show(Run(Claim())),
            Show(Run(null)),
            Show(Run(Claim(-1m))),
            Show(Run(Claim(99m))),
            Show(Run(Claim(100m))),
            Show(Run(Claim(101m))),
            Show(Run(Claim(500m, category: "theft", policeReport: true))),
            Show(Run(Claim(), risk: 80)),
            Show(repeated) + "/" + Show(Run(Claim())),
            Show(Run(Claim(950m, documents: false, days: 91, priorPaid: 100m))));
    }

    private static string PaymentsCases()
    {
        static PaymentItem Item(string reference = "R1", decimal amount = 100m, string currency = "EUR", bool refunded = false, bool held = false) =>
            new(reference, currency, amount, refunded, held);
        static string Run(IEnumerable<PaymentItem> items, decimal limit = 1000m, bool accepted = true, string merchant = "M1")
        {
            var gateway = new GatewayStub(accepted);
            var result = new SettlementBatchProcessor().Process(merchant, items, "EUR", 0.01m, 1m, limit, gateway);
            return $"{result.BatchStatus}|{result.SubmittedTotal.ToString(CultureInfo.InvariantCulture)}|{string.Join(',', result.Lines.Select(line => line.Status))}|calls={gateway.Calls}";
        }

        return string.Join('\n',
            Run([Item()]),
            Run([]),
            Run([Item()], merchant: ""),
            Run([Item(amount: 99m)], limit: 100m),
            Run([Item(amount: 102.02m)], limit: 100m),
            Run([Item(amount: 103.03m)], limit: 100m),
            Run([Item("R1"), Item("R2", currency: "USD")]),
            Run([Item()], accepted: false),
            Run([Item("R1"), Item("R1")]),
            Run([Item("R1", 50m), Item("R2", 0m), Item("R3", 70m)], limit: 115m));
    }

    private static string AccessCases()
    {
        static Principal Principal(params string[] roles) => new("U1", "T1", roles.ToHashSet(), false, 0);
        static Resource Resource(string classification = "ordinary", bool locked = false) => new("R1", "T1", classification, "U1", locked);
        static AccessRequest Request(string action = "read", int minute = 600, bool strong = false, bool breakGlass = false, string zone = "trusted") =>
            new(action, strong, breakGlass, minute, zone);
        static string Run(Principal? principal, Resource? resource, AccessRequest? request, bool delegated = false)
        {
            var decision = new AccessDecisionEngine().Decide(principal, resource, request, new DelegationStub(delegated));
            return $"{decision.Allowed}|{decision.Reason}|{decision.AuditRequired}";
        }

        return string.Join('\n',
            Run(Principal("operator"), Resource(), Request()),
            Run(null, Resource(), Request()),
            Run(Principal(), Resource(), Request("unknown")),
            Run(Principal(), Resource(), Request(minute: 479)),
            Run(Principal(), Resource(), Request(minute: 480)),
            Run(Principal(), Resource(), Request(minute: 1081)),
            Run(Principal("administrator"), Resource(), Request("delete")),
            Run(new Principal("U2", "T1", new HashSet<string>(), false, 0), Resource(), Request("write"), true),
            Run(Principal("operator"), Resource(), Request()) + "/" + Run(Principal("operator"), Resource(), Request()),
            Run(Principal("administrator"), Resource("restricted"), Request("delete", strong: true, breakGlass: true, zone: "untrusted")));
    }

    private static string FulfilmentCases()
    {
        static OrderRequest Order(int quantity = 2, bool priority = false, bool fragile = false) =>
            new("O1", "NL", "standard", priority, [new OrderItem("S1", quantity, fragile)]);
        static IReadOnlyDictionary<string, StockPosition> Stock(int available) =>
            new Dictionary<string, StockPosition> { ["S1"] = new("S1", available, 0, "A", false) };
        static CarrierOption Carrier() => new("FAST", 10m, 1, true, new HashSet<string> { "NL" });

        var repeat = new FulfilmentCoordinator();
        var compound = new FulfilmentCoordinator();
        var order = Order();
        var compoundResult = string.Join('/', compound.Reserve(order, Stock(2)), compound.CreatePickNote(order, Stock(2)),
            compound.ConfirmPick(order, 2, false), compound.ChooseCarrier(order, [Carrier()]), compound.Dispatch(order, "FAST-1", true));
        return string.Join('\n',
            new FulfilmentCoordinator().Reserve(Order(), Stock(2)),
            new FulfilmentCoordinator().Reserve(new OrderRequest("O1", "NL", "standard", false, []), Stock(2)),
            new FulfilmentCoordinator().Reserve(Order(0), Stock(2)),
            new FulfilmentCoordinator().Reserve(Order(1), Stock(2)),
            new FulfilmentCoordinator().Reserve(Order(2), Stock(2)),
            new FulfilmentCoordinator().Reserve(Order(3), Stock(2)),
            new FulfilmentCoordinator().ChooseCarrier(Order(priority: true, fragile: true), [Carrier()]),
            new FulfilmentCoordinator().ChooseCarrier(Order(fragile: true), []),
            repeat.Reserve(Order(), Stock(2)) + "/" + repeat.Reserve(Order(), Stock(2)),
            compoundResult);
    }

    private static string SubscriptionCases()
    {
        static Account Account(bool arrears = false) => new("A1", "NL", "a@example.test", true, arrears);
        static Plan Plan(int seats = 5, bool trial = true) => new("P1", 20m, seats, trial, new HashSet<string> { "NL" });

        var payment = new SubscriptionAccountService();
        payment.Start(Account(), Plan(), 1, false);
        payment.RecordInvoice(Account(), Plan(), 1, 0m);
        var repeat = new SubscriptionAccountService();
        var entitlement = new Entitlement("reports", 1, false);
        var compound = new SubscriptionAccountService();
        var account = Account();
        var plan = Plan();
        return string.Join('\n',
            new SubscriptionAccountService().Start(Account(), Plan(), 1, false),
            new SubscriptionAccountService().Start(new Account("", "NL", "a@example.test", true, false), Plan(), 1, false),
            new SubscriptionAccountService().Start(Account(), Plan(), 0, false),
            new SubscriptionAccountService().Start(Account(), Plan(), 4, false),
            new SubscriptionAccountService().Start(Account(), Plan(), 5, false),
            new SubscriptionAccountService().Start(Account(), Plan(), 6, false),
            new SubscriptionAccountService().Start(Account(), Plan(), 1, true),
            payment.ApplyPayment(Account(), new PaymentAttempt("PAY1", 20m, false, "declined")),
            repeat.GrantEntitlement(Account(), entitlement) + "/" + repeat.GrantEntitlement(Account(), entitlement),
            string.Join('/', compound.Start(account, plan, 1, false), compound.RecordInvoice(account, plan, 1, 0m),
                compound.ApplyPayment(account, new PaymentAttempt("PAY2", 20m, true, "")), compound.GrantEntitlement(account, entitlement)));
    }

    private static string ServiceDeskCases()
    {
        static SupportCase Case(bool security = false, int reopens = 0, string summary = "Cannot sign in") =>
            new("C1", "premium", "Portal", summary, security, reopens);
        static ServicePolicy Policy() => new("Portal", 120, 30, 3, true);
        static string Deadline(int current)
        {
            var manager = new CaseOperationsManager();
            manager.SetDeadline(Case(), Policy(), 100, false);
            return manager.CheckDeadline(Case(), current, 10);
        }

        var repeat = new CaseOperationsManager();
        var supportCase = Case();
        repeat.Assign(supportCase, [new Agent("A1", new HashSet<string> { "portal" }, 1, true, "EU")], "portal");
        var compound = new CaseOperationsManager();
        var securityCase = Case(security: true);
        return string.Join('\n',
            new CaseOperationsManager().Triage(Case(), new HashSet<string> { "Portal" }),
            new CaseOperationsManager().Triage(Case(summary: ""), new HashSet<string> { "Portal" }),
            new CaseOperationsManager().Triage(Case(reopens: -1), new HashSet<string> { "Portal" }),
            Deadline(219),
            Deadline(220),
            Deadline(221),
            new CaseOperationsManager().Triage(Case(security: true), new HashSet<string> { "Portal" }),
            new CaseOperationsManager().Assign(Case(), [], "portal"),
            repeat.Reassign(supportCase, new Agent("A2", new HashSet<string> { "portal" }, 2, true, "EU"), "load"),
            string.Join('/', compound.Triage(securityCase, new HashSet<string> { "Portal" }),
                compound.SetDeadline(securityCase, Policy(), 100, false),
                compound.RecordMessage(securityCase, new CustomerMessage("email", "Security incident details", true, 0)),
                compound.Escalate(securityCase, new EscalationRule("SEC", "premium", true, 30, "security-team"), 31)));
    }

    private sealed class CoverageStub(Coverage coverage) : ICoverageRegister
    {
        public Coverage? Find(string policyNumber) => coverage;
    }

    private sealed class RiskStub(int score) : IRiskScreen
    {
        public int Score(Claim claim) => score;
    }

    private sealed class GatewayStub(bool accepted) : ISettlementGateway
    {
        public int Calls { get; private set; }
        public GatewayResult Submit(string merchantId, string currency, decimal amount, IReadOnlyList<string> references)
        {
            Calls++;
            return new GatewayResult(accepted, accepted ? "ok" : "declined");
        }
    }

    private sealed class DelegationStub(bool delegated) : IDelegationRegister
    {
        public bool HasDelegation(string principalId, string resourceId, string action) => delegated;
    }
}
