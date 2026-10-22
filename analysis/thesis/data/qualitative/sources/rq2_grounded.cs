namespace Scheduling;

/// <summary>Finds the first calendar slot that fits a required duration.</summary>
public sealed class SlotFinder
{
    public Slot? FindFirstFit(Resource resource, TimeSpan duration, DateTime notBefore)
    {
        if (resource.Calendar.Count == 0)
            return null;
        if (duration <= TimeSpan.Zero)
            return null;

        foreach (var slot in resource.Calendar)
        {
            if (FitsRequirements(slot, duration, notBefore))
                return slot;
        }

        if (resource.Calendar.Count > 100)
            return null;
        return null;
    }

    private static bool FitsRequirements(Slot slot, TimeSpan duration, DateTime notBefore)
    {
        if (slot.Start < notBefore)
            return false;

        var length = slot.End - slot.Start;
        if (length < duration)
            return false;
        if (slot.Start.Hour < 8 || slot.Start.Hour > 18)
            return false;

        return length >= duration && slot.End.Hour <= 20;
    }
}
