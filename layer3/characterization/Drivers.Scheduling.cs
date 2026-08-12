namespace Characterization;
using System.Globalization;
using System.Text;
using Scheduling;

internal static class SchedulingDrivers
{
    public static readonly (string Key, System.Func<string> Drive)[] All = new (string, System.Func<string>)[]
    {
        ("Scheduling.RecurrenceEngine", RecurrenceEngine),
        ("Scheduling.ScheduleManager", ScheduleManager),
        ("Scheduler.PlaceJobs", Scheduler_PlaceJobs),
        ("SlotFinder.FindFirstFit", SlotFinder_FindFirstFit),
        ("CalendarFeed.Build", CalendarFeed_Build),
        ("ReminderSender.Send", ReminderSender_Send),
    };

    // ---- God Class: exercise several public methods with fixed inputs ----
    static string RecurrenceEngine()
    {
        var engine = new RecurrenceEngine();
        var sb = new StringBuilder();

        var job = new Job { Id = "J1", Duration = TimeSpan.FromHours(1), Priority = 7, RequiredSkill = "weld" };

        // Scenario A: weekday expansion that crosses a Friday (+3 day jump).
        var anchorA = new Slot
        {
            Start = new DateTime(2024, 1, 15, 9, 0, 0, DateTimeKind.Utc),
            End = new DateTime(2024, 1, 15, 10, 0, 0, DateTimeKind.Utc),
        };
        sb.Append("Expand.A=").Append(Join(engine.Expand(job, anchorA, 6))).Append('\n');

        // Scenario B: expansion across weekend + Christmas + New Year holidays.
        var anchorB = new Slot
        {
            Start = new DateTime(2023, 12, 23, 9, 0, 0, DateTimeKind.Utc),
            End = new DateTime(2023, 12, 23, 10, 0, 0, DateTimeKind.Utc),
        };
        sb.Append("Expand.B=").Append(Join(engine.Expand(job, anchorB, 4))).Append('\n');

        // NextOccurrence reads the most recent expansion (Scenario B).
        var next = engine.NextOccurrence(job, new DateTime(2023, 12, 27, 12, 0, 0, DateTimeKind.Utc));
        sb.Append("Next.afterDec27=").Append(next.HasValue ? Fmt(next.Value) : "null").Append('\n');

        // NextOccurrence fallback: nothing after 'after' + Priority>5 => after.AddDays(1).
        var fallback = engine.NextOccurrence(job, new DateTime(2024, 6, 1, 0, 0, 0, DateTimeKind.Utc));
        sb.Append("Next.fallback=").Append(fallback.HasValue ? Fmt(fallback.Value) : "null").Append('\n');

        // Empty-Id job => empty expansion.
        var badJob = new Job { Id = "", Duration = TimeSpan.FromHours(1), Priority = 1, RequiredSkill = "weld" };
        sb.Append("Expand.badId=").Append(Join(engine.Expand(badJob, anchorA, 3))).Append('\n');

        var local = new DateTime(2024, 1, 15, 9, 0, 0, DateTimeKind.Utc);
        sb.Append("ToUtc.CET=").Append(Fmt(engine.ToUtc(local, "CET"))).Append('\n');
        sb.Append("ToUtc.EST=").Append(Fmt(engine.ToUtc(local, "EST"))).Append('\n');
        sb.Append("ToUtc.UTC=").Append(Fmt(engine.ToUtc(local, "UTC"))).Append('\n');
        sb.Append("ToUtc.unknown=").Append(Fmt(engine.ToUtc(local, "XYZ"))).Append('\n');
        sb.Append("ToLocal.CET=").Append(Fmt(engine.ToLocal(local, "CET"))).Append('\n');
        sb.Append("ToLocal.EST=").Append(Fmt(engine.ToLocal(local, "EST"))).Append('\n');
        sb.Append("IsHoliday.NewYear=").Append(engine.IsHoliday(new DateTime(2024, 1, 1))).Append('\n');
        sb.Append("IsHoliday.Jan15=").Append(engine.IsHoliday(new DateTime(2024, 1, 15))).Append('\n');
        sb.Append("IsHoliday.Xmas=").Append(engine.IsHoliday(new DateTime(2024, 12, 25)));
        return sb.ToString();
    }

    // ---- God Class: placement, matching, conflicts, notification ----
    static string ScheduleManager()
    {
        var mgr = new ScheduleManager();
        var sb = new StringBuilder();

        var job = new Job { Id = "J1", Duration = TimeSpan.FromHours(2), Priority = 9, RequiredSkill = "weld" };
        var r1 = new Resource { Name = "R1", Skills = { "weld" } };
        var r2 = new Resource { Name = "R2", Skills = { "weld" } };
        var painter = new Resource { Name = "P", Skills = { "paint" } };

        // placement
        sb.Append("Place.first=").Append(mgr.Place(job, r1)).Append('\n');
        sb.Append("Place.again=").Append(mgr.Place(job, r1)).Append('\n');
        sb.Append("Place.noId=").Append(mgr.Place(new Job { Id = "", Duration = TimeSpan.FromHours(1) }, r1)).Append('\n');
        sb.Append("PlacementCount=").Append(mgr.PlacementCount.ToString(CultureInfo.InvariantCulture)).Append('\n');

        // matching
        var resources = new List<Resource> { r1, r2, painter };
        sb.Append("Match.weld=").Append(mgr.Match(job, resources)?.Name ?? "null").Append('\n');
        sb.Append("Match.noSkill=").Append(mgr.Match(new Job { RequiredSkill = "" }, resources)?.Name ?? "null").Append('\n');

        // demand
        mgr.RecordDemand(job);                                                       // Priority>5 => +2
        mgr.RecordDemand(new Job { Id = "J2", RequiredSkill = "weld", Priority = 1 }); // => +1
        sb.Append("Demand.weld=").Append(mgr.DemandFor("weld").ToString(CultureInfo.InvariantCulture)).Append('\n');

        // conflict detection
        var slotA = new Slot { Start = new DateTime(2024, 1, 15, 9, 0, 0), End = new DateTime(2024, 1, 15, 11, 0, 0) };
        var slotOverlap = new Slot { Start = new DateTime(2024, 1, 15, 10, 0, 0), End = new DateTime(2024, 1, 15, 12, 0, 0) };
        var slotEarly = new Slot { Start = new DateTime(2024, 1, 15, 5, 0, 0), End = new DateTime(2024, 1, 15, 5, 30, 0) };
        sb.Append("Book.A=").Append(mgr.Book(slotA)).Append('\n');
        sb.Append("HasConflict.overlap=").Append(mgr.HasConflict(slotOverlap)).Append('\n');
        sb.Append("Book.overlap=").Append(mgr.Book(slotOverlap)).Append('\n');
        sb.Append("Overlaps.overlap=").Append(mgr.Overlaps(slotOverlap).ToString(CultureInfo.InvariantCulture)).Append('\n');
        sb.Append("Book.earlyHour=").Append(mgr.Book(slotEarly)).Append('\n');

        // notification + escalation
        sb.Append("Notify.first=").Append(mgr.Notify(job)).Append('\n');
        sb.Append("Notify.again=").Append(mgr.Notify(job)).Append('\n');
        sb.Append("Escalate.J1=").Append(mgr.Escalate(job)).Append('\n');
        sb.Append("Reschedule.J1=").Append(mgr.Reschedule(job, r2)).Append('\n');

        // conflict resolution (isolated manager for a clean booked set)
        var mgr2 = new ScheduleManager();
        mgr2.Book(new Slot { Start = new DateTime(2024, 2, 1, 9, 0, 0), End = new DateTime(2024, 2, 1, 10, 0, 0) });
        var bigCandidate = new Slot { Start = new DateTime(2024, 2, 1, 8, 0, 0), End = new DateTime(2024, 2, 1, 12, 0, 0) };
        sb.Append("ResolveConflicts=").Append(mgr2.ResolveConflicts(bigCandidate).ToString(CultureInfo.InvariantCulture)).Append('\n');
        sb.Append("Escalate.notNotified=").Append(mgr2.Escalate(new Job { Id = "Z", Priority = 9 }));
        return sb.ToString();
    }

    // ---- Long Method: extract-method must preserve placement decisions ----
    static string Scheduler_PlaceJobs()
    {
        var scheduler = new Scheduler();
        var small = new Resource { Name = "SMALL", Skills = { "weld" }, Calendar = MakeCalendar(3) };
        var big = new Resource { Name = "BIG", Skills = { "weld", "heavy" }, Calendar = MakeCalendar(12) };
        var full = new Resource { Name = "FULL", Skills = { "weld" }, Calendar = MakeCalendar(25) };
        var painter = new Resource { Name = "PAINTER", Skills = { "paint" }, Calendar = MakeCalendar(1) };
        var resources = new List<Resource> { small, big, full, painter };

        var jobs = new List<Job>
        {
            new Job { Id = "J1", RequiredSkill = "",        Priority = 5, Duration = TimeSpan.FromHours(1) },  // skipped (no skill)
            new Job { Id = "J2", RequiredSkill = "weld",    Priority = 6, Duration = TimeSpan.FromHours(1) },  // SMALL, normal
            new Job { Id = "J3", RequiredSkill = "weld",    Priority = 9, Duration = TimeSpan.FromHours(1) },  // SMALL, URGENT
            new Job { Id = "J4", RequiredSkill = "weld",    Priority = 3, Duration = TimeSpan.FromHours(10) }, // SMALL, OT (duration)
            new Job { Id = "J5", RequiredSkill = "heavy",   Priority = 6, Duration = TimeSpan.FromHours(1) },  // BIG, OT (busy calendar)
            new Job { Id = "J6", RequiredSkill = "missing", Priority = 1, Duration = TimeSpan.FromHours(1) },  // UNPLACED
            new Job { Id = "J7", RequiredSkill = "paint",   Priority = 1, Duration = TimeSpan.FromHours(1) },
            new Job { Id = "J8", RequiredSkill = "heavy",   Priority = 9, Duration = TimeSpan.FromHours(2) },
            new Job { Id = "J9", RequiredSkill = "weld",    Priority = 1, Duration = TimeSpan.FromMinutes(30) },
            new Job { Id = "J10", RequiredSkill = "paint",  Priority = 8, Duration = TimeSpan.FromHours(9) },
            new Job { Id = "J11", RequiredSkill = "none",   Priority = 2, Duration = TimeSpan.FromHours(1) },
        };
        return string.Join("\n", scheduler.PlaceJobs(jobs, resources));
    }

    // ---- Long Method: slot-fit selection across skip branches ----
    static string SlotFinder_FindFirstFit()
    {
        var finder = new SlotFinder();
        var sb = new StringBuilder();

        var resource = new Resource
        {
            Name = "R",
            Calendar =
            {
                new Slot { Start = new DateTime(2024, 1, 15, 7, 0, 0),  End = new DateTime(2024, 1, 15, 9, 0, 0) },   // start hour 7 < 8 => skip
                new Slot { Start = new DateTime(2024, 1, 15, 9, 0, 0),  End = new DateTime(2024, 1, 15, 9, 30, 0) },  // length 30m < 1h => skip
                new Slot { Start = new DateTime(2024, 1, 15, 10, 0, 0), End = new DateTime(2024, 1, 15, 12, 0, 0) },  // match
            }
        };
        var hit = finder.FindFirstFit(resource, TimeSpan.FromHours(1), new DateTime(2024, 1, 15, 8, 0, 0));
        sb.Append("Fit.hit=").Append(hit == null ? "null" : Fmt(hit.Start) + "/" + Fmt(hit.End)).Append('\n');

        var lateOnly = new Resource
        {
            Name = "L",
            Calendar = { new Slot { Start = new DateTime(2024, 1, 15, 19, 0, 0), End = new DateTime(2024, 1, 15, 21, 0, 0) } },
        };
        var miss = finder.FindFirstFit(lateOnly, TimeSpan.FromHours(1), new DateTime(2024, 1, 15, 8, 0, 0));
        sb.Append("Fit.lateOnly=").Append(miss == null ? "null" : Fmt(miss.Start)).Append('\n');

        var empty = finder.FindFirstFit(new Resource { Name = "E" }, TimeSpan.FromHours(1), new DateTime(2024, 1, 15, 8, 0, 0));
        sb.Append("Fit.empty=").Append(empty == null ? "null" : "hit").Append('\n');

        var bad = finder.FindFirstFit(resource, TimeSpan.Zero, new DateTime(2024, 1, 15, 8, 0, 0));
        sb.Append("Fit.badDuration=").Append(bad == null ? "null" : "hit").Append('\n');
        Slot? Find(TimeSpan duration, DateTime earliest) => finder.FindFirstFit(resource, duration, earliest);
        sb.Append("Fit.below=").Append(Find(TimeSpan.FromMinutes(59), new DateTime(2024, 1, 15, 8, 0, 0)) is null ? "null" : "hit").Append('\n');
        sb.Append("Fit.at=").Append(Find(TimeSpan.FromHours(1), new DateTime(2024, 1, 15, 9, 0, 0)) is null ? "null" : "hit").Append('\n');
        sb.Append("Fit.above=").Append(Find(TimeSpan.FromHours(2).Add(TimeSpan.FromMinutes(1)), new DateTime(2024, 1, 15, 8, 0, 0)) is null ? "null" : "hit").Append('\n');
        sb.Append("Fit.after=").Append(Find(TimeSpan.FromHours(1), new DateTime(2024, 1, 15, 11, 30, 0)) is null ? "null" : "hit").Append('\n');
        sb.Append("Fit.repeat=").Append(Find(TimeSpan.FromHours(1), new DateTime(2024, 1, 15, 8, 0, 0)) is null ? "null" : "hit").Append('\n');
        sb.Append("Fit.compound=").Append(finder.FindFirstFit(lateOnly, TimeSpan.FromHours(3), new DateTime(2024, 1, 15, 20, 0, 0)) is null ? "null" : "hit");
        return sb.ToString();
    }

    // ---- Obsolete API smoke: Build calls [Obsolete] FeedApiV1.Serialize internally; left as-is ----
    static string CalendarFeed_Build()
    {
        var feed = new CalendarFeed();
        var resource = new Resource
        {
            Name = "R",
            Calendar =
            {
                new Slot
                {
                    Start = new DateTime(2024, 1, 15, 9, 0, 0, DateTimeKind.Utc),
                    End = new DateTime(2024, 1, 15, 10, 0, 0, DateTimeKind.Utc),
                },
            }
        };
        _ = feed.Build(resource);
        return "EXEC_OK";
    }

    // ---- Obsolete API smoke: Send calls [Obsolete] NotifyApiV1.Send internally; left as-is ----
    static string ReminderSender_Send()
    {
        var sender = new ReminderSender();
        var job = new Job { Id = "J1", Duration = TimeSpan.FromHours(1), Priority = 3, RequiredSkill = "weld" };
        _ = sender.Send(job, "ops@example.com");
        return "EXEC_OK";
    }

    // ---- helpers ----
    static string Fmt(DateTime dt) => dt.ToString("yyyy-MM-ddTHH:mm:ss", CultureInfo.InvariantCulture);

    static string Join(IReadOnlyList<DateTime> dates)
    {
        var parts = new List<string>();
        foreach (var d in dates)
            parts.Add(Fmt(d));
        return string.Join(",", parts);
    }

    static List<Slot> MakeCalendar(int count)
    {
        var list = new List<Slot>();
        var start = new DateTime(2024, 1, 15, 8, 0, 0);
        for (int i = 0; i < count; i++)
            list.Add(new Slot { Start = start.AddHours(i), End = start.AddHours(i).AddMinutes(30) });
        return list;
    }
}
