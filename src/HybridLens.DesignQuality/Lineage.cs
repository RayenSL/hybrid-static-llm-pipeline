namespace HybridLens.DesignQuality;

public sealed record LineageCandidate(string Before, string After, string Evidence, int SharedStatements);
public sealed record LineageResult(string Status, LineageCandidate[] Candidates, string[] UnmatchedBefore,
    string[] UnmatchedAfter, string[] TargetSeeds, string[] ReachableAddedCallables,
    string Interpretation);

public static class Lineage
{
    public static LineageResult Compare(FileFacts before, FileFacts after, string target, string antiPattern)
    {
        if (before.Status != "measured" || after.Status != "measured")
            return new("unavailable", [], [], [], [], [], "Semantic compilation unavailable; no lineage claim.");
        var candidates = new List<LineageCandidate>();
        foreach (var b in before.Callables)
        foreach (var a in after.Callables)
        {
            var shared = b.Statements.Intersect(a.Statements).Count();
            if (b.Id == a.Id) candidates.Add(new(b.Id, a.Id, "same_declaration_id", shared));
            else if (b.BodyFingerprint == a.BodyFingerprint && b.TokenCount > 0)
                candidates.Add(new(b.Id, a.Id, "identical_body_candidate", shared));
            else if (shared >= 2)
                candidates.Add(new(b.Id, a.Id, "shared_statements_candidate", shared));
        }
        // Target detector names omit namespaces for methods. Suffix matching is audited for uniqueness.
        var seeds = before.Callables.Where(c => antiPattern == "god_class"
            ? c.Owner == "T:" + target || c.Owner.EndsWith("." + target, StringComparison.Ordinal)
            : c.Id.Split('(')[0] == "M:" + target || c.Id.Split('(')[0].EndsWith("." + target, StringComparison.Ordinal))
            .Select(c => c.Id).ToArray();
        var matched = candidates.Where(c => seeds.Contains(c.Before) && c.Evidence == "same_declaration_id").Select(c => c.After).ToHashSet();
        var baselineIds = before.Callables.Select(c => c.Id).ToHashSet();
        var added = after.Callables.Where(c => !baselineIds.Contains(c.Id)).Select(c => c.Id).ToHashSet();
        var reachable = new HashSet<string>();
        var queue = new Queue<string>(matched);
        var seen = new HashSet<string>(matched);
        var byId = after.Callables.GroupBy(c => c.Id).ToDictionary(g => g.Key, g => g.First());
        while (queue.TryDequeue(out var current))
        {
            if (!byId.TryGetValue(current, out var callable)) continue;
            foreach (var call in callable.Calls)
                if (added.Contains(call) && seen.Add(call)) { reachable.Add(call); queue.Enqueue(call); }
        }
        return new(seeds.Length == 0 || (antiPattern == "long_method" && seeds.Length != 1) ? "target_ambiguous" : "candidates_only",
            candidates.ToArray(), before.Callables.Where(c => !candidates.Any(l => l.Before == c.Id)).Select(c => c.Id).ToArray(),
            after.Callables.Where(c => !candidates.Any(l => l.After == c.Id)).Select(c => c.Id).ToArray(), seeds,
            reachable.Order().ToArray(),
            "Declaration continuity, exact-body matches, statement overlap and reachability are evidence, not confirmed responsibility lineage. Primary descendant endpoint requires adjudication; disappearance is never success.");
    }
}
