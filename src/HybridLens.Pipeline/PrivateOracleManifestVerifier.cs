using System.Security.Cryptography;
using System.Text.RegularExpressions;

namespace HybridLens.Pipeline;

/// <summary>Verifies every SHA-256 entry frozen in the private-oracle Markdown manifest.</summary>
public static partial class PrivateOracleManifestVerifier
{
    public static string Verify(string manifestPath)
    {
        var fullManifest = Path.GetFullPath(manifestPath);
        var text = File.ReadAllText(fullManifest);
        var version = Regex.Match(text, @"Manifest version:\s*([^\r\n]+)", RegexOptions.IgnoreCase).Groups[1].Value.Trim();
        if (version.Length == 0) throw new InvalidDataException("private-oracle manifest has no version");

        var hashText = ActiveHashBlock(text, version);
        var entries = HashEntryRegex().Matches(hashText);
        if (entries.Count == 0) throw new InvalidDataException("private-oracle manifest contains no SHA-256 entries");
        var repositoryRoot = Path.GetDirectoryName(Path.GetDirectoryName(fullManifest)!)!;
        foreach (Match entry in entries)
        {
            var expected = entry.Groups[1].Value.ToLowerInvariant();
            var relative = entry.Groups[2].Value.Replace('/', Path.DirectorySeparatorChar);
            var path = Path.GetFullPath(Path.Combine(repositoryRoot, relative));
            if (!File.Exists(path)) throw new InvalidDataException($"private-oracle file is missing: {relative}");
            var actual = Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(path)));
            if (!string.Equals(actual, expected, StringComparison.Ordinal))
                throw new InvalidDataException($"private-oracle hash mismatch: {relative}");
            if (path.EndsWith("SHA256SUMS.txt", StringComparison.OrdinalIgnoreCase))
                VerifyChecksumIndex(path, repositoryRoot);
        }
        return version;
    }

    private static string ActiveHashBlock(string text, string version)
    {
        const string marker = "## SHA-256 (active)";
        if (!version.StartsWith("2.", StringComparison.Ordinal) || !text.Contains(marker, StringComparison.Ordinal))
            return text;

        var start = text.IndexOf(marker, StringComparison.Ordinal) + marker.Length;
        var end = text.IndexOf("\n## ", start, StringComparison.Ordinal);
        return end < 0 ? text[start..] : text[start..end];
    }

    private static void VerifyChecksumIndex(string indexPath, string repositoryRoot)
    {
        var listed = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var line in File.ReadLines(indexPath))
        {
            var match = Regex.Match(line, @"^([0-9a-fA-F]{64})\s{2}([^\r\n]+)$");
            if (!match.Success) throw new InvalidDataException($"invalid checksum-index line: {line}");
            var relative = match.Groups[2].Value.Replace('/', Path.DirectorySeparatorChar);
            var path = Path.GetFullPath(Path.Combine(repositoryRoot, relative));
            if (!path.StartsWith(Path.GetFullPath(repositoryRoot) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException($"checksum-index path escapes repository: {relative}");
            if (!File.Exists(path)) throw new InvalidDataException($"checksum-index file is missing: {relative}");
            var actual = Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(path)));
            if (!string.Equals(actual, match.Groups[1].Value, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException($"checksum-index hash mismatch: {relative}");
            listed.Add(Path.GetRelativePath(repositoryRoot, path));
        }

        if (Path.GetFileName(indexPath).Equals("GOLDEN_SHA256SUMS.txt", StringComparison.OrdinalIgnoreCase))
        {
            var goldenDirectory = Path.Combine(repositoryRoot, "layer3", "golden");
            var actualFiles = Directory.EnumerateFiles(goldenDirectory, "*.golden")
                .Select(path => Path.GetRelativePath(repositoryRoot, path))
                .ToHashSet(StringComparer.OrdinalIgnoreCase);
            if (!actualFiles.SetEquals(listed))
                throw new InvalidDataException("golden checksum index does not exactly cover the golden directory");
        }
    }

    [GeneratedRegex(@"(?m)^([0-9a-fA-F]{64})\s{2}([^\r\n]+)$")]
    private static partial Regex HashEntryRegex();
}
