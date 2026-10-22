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
            if (slot.Start < notBefore)
                continue;
            var length = slot.End - slot.Start;
            if (length < duration)
                continue;
            if (slot.Start.Hour < 8 || slot.Start.Hour > 18)
                continue;
            if (length >= duration && slot.End.Hour <= 20)
                return slot;
        }

        if (resource.Calendar.Count > 100)
            return null;
        return null;
    }
}
