using Characterization;

// Golden-master / smoke characterisation runner for the Layer-3 behavioural instrument.
//   dotnet run -- --capture <goldenDir>   (author goldens from the pristine corpus, once)
//   dotnet run -- --check   <goldenDir>   (compare the current build to the frozen goldens)
// Exit code 0 = all pass; 1 = at least one behavioural regression / missing golden.

var rawDrivers = new List<(string Key, Func<string> Drive)>();
rawDrivers.AddRange(OrderingDrivers.All);
rawDrivers.AddRange(InventoryDrivers.All);
rawDrivers.AddRange(InvoicingDrivers.All);
rawDrivers.AddRange(NotificationsDrivers.All);
rawDrivers.AddRange(SchedulingDrivers.All);
rawDrivers.AddRange(V2Drivers.All);
var drivers = PrivateCaseCatalog.Expand(rawDrivers).ToList();
drivers.Sort((a, b) => string.CompareOrdinal(a.Key, b.Key));

var mode = args.Length > 0 ? args[0] : "--check";
var dir  = args.Length > 1 ? args[1] : "golden";
Directory.CreateDirectory(dir);

static string SafeName(string key)
{
    foreach (var c in Path.GetInvalidFileNameChars()) key = key.Replace(c, '_');
    return key.Replace(' ', '_');
}

static string Trunc(string s)
{
    s = s.Replace("\r", "").Replace("\n", "\\n");
    return s.Length <= 240 ? s : s[..240] + "…";
}

var failed = 0;
foreach (var (key, drive) in drivers)
{
    string actual;
    try { actual = drive(); }
    catch (Exception ex) { actual = $"__EXCEPTION__ {ex.GetType().Name}: {ex.Message}"; }

    var path = Path.Combine(dir, SafeName(key) + ".golden");
    if (mode == "--capture")
    {
        File.WriteAllText(path, actual);
        var flag = actual.StartsWith("__EXCEPTION__") ? "  <-- THREW on pristine!" : "";
        Console.WriteLine($"CAPTURE  {key}  ({actual.Length} chars){flag}");
    }
    else
    {
        if (!File.Exists(path)) { Console.WriteLine($"MISSING-GOLDEN  {key}"); failed++; continue; }
        var expected = File.ReadAllText(path);
        if (expected == actual) { Console.WriteLine($"PASS  {key}"); }
        else
        {
            Console.WriteLine($"REGRESSION  {key}");
            Console.WriteLine($"    expected: {Trunc(expected)}");
            Console.WriteLine($"    actual:   {Trunc(actual)}");
            failed++;
        }
    }
}
Console.WriteLine(mode == "--capture"
    ? $"captured {drivers.Count} driver(s)"
    : (failed == 0 ? "ALL PASS" : $"{failed} REGRESSION(S)"));
return failed == 0 ? 0 : 1;
