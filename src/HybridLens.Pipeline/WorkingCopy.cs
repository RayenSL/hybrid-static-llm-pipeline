namespace HybridLens.Pipeline;

/// <summary>
/// Materialises an isolated copy of a solution tree so one repaired file can be measured without
/// touching the pristine source and without any two artefacts observing each other.
///
/// What the copy omits decides whether the measurement is valid at all. A solution built with
/// <c>--no-restore</c> must retain <c>obj</c>, because that is where <c>project.assets.json</c> lives
/// and nothing else regenerates it; omit it and MSBuild stops at NETSDK1004 before the repaired file
/// is ever compiled. Retaining it is sound: the copied assets file resolves to the machine-wide
/// package cache, while the sources and project files compiled are the copy's own.
/// </summary>
public static class WorkingCopy
{
    /// <summary>Directories omitted unless the caller declares otherwise.</summary>
    public static readonly string[] DefaultSkipDirectories = ["bin", "obj", ".git", ".vs", ".idea"];

    /// <summary>Copies <paramref name="source"/> to <paramref name="destination"/>, skipping any path
    /// that contains one of <paramref name="skipDirectories"/> as a segment.</summary>
    public static void Create(string source, string destination, IReadOnlyList<string>? skipDirectories = null)
    {
        var skip = skipDirectories is { Count: > 0 } declared ? declared : DefaultSkipDirectories;
        source = Path.GetFullPath(source);
        Directory.CreateDirectory(destination);
        foreach (var file in Directory.EnumerateFiles(source, "*", SearchOption.AllDirectories))
        {
            var relative = Path.GetRelativePath(source, file);
            if (IsSkipped(relative, skip)) continue;
            var target = Path.Combine(destination, relative);
            Directory.CreateDirectory(Path.GetDirectoryName(target)!);
            File.Copy(file, target, overwrite: true);
        }
    }

    public static bool IsSkipped(string relativePath, IReadOnlyList<string> skipDirectories) =>
        relativePath
            .Split(['\\', '/'], StringSplitOptions.RemoveEmptyEntries)
            .Any(segment => skipDirectories.Contains(segment, StringComparer.OrdinalIgnoreCase));

    /// <summary>Deletes a materialised copy. Best effort: the target is a temporary directory.</summary>
    public static void TryDelete(string path)
    {
        try { if (Directory.Exists(path)) Directory.Delete(path, recursive: true); }
        catch { /* best effort */ }
    }

    /// <summary>
    /// Throws when the build arguments cannot succeed against the declared skip list, so the caller
    /// fails before spending a campaign rather than recording failures the model never caused.
    /// </summary>
    public static void GuardRestoreArguments(
        IReadOnlyList<string> buildArguments, IReadOnlyList<string>? skipDirectories, string subject)
    {
        if (buildArguments.Contains("--no-restore", StringComparer.Ordinal) &&
            (skipDirectories ?? DefaultSkipDirectories).Contains("obj", StringComparer.OrdinalIgnoreCase))
            throw new InvalidDataException(
                $"{subject} builds with --no-restore, so the working copy must retain obj; "
                + "declare the skip list without it");
    }
}
