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

        var entries = HashEntryRegex().Matches(text);
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
        }
        return version;
    }

    [GeneratedRegex(@"(?m)^([0-9a-fA-F]{64})\s{2}([^\r\n]+)$")]
    private static partial Regex HashEntryRegex();
}
