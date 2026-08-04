namespace CharacterizationPilot;

public sealed class CheckoutCalculator
{
    public decimal Calculate(
        decimal subtotal,
        int itemCount,
        bool isMember,
        bool hasCoupon,
        bool weekend,
        bool expedited,
        string destination,
        int loyaltyYears,
        bool fragile,
        bool giftWrap,
        bool firstOrder,
        bool seasonalSale)
    {
        if (subtotal < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(subtotal));
        }

        if (itemCount < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(itemCount));
        }

        var total = subtotal;

        if (isMember)
        {
            total *= 0.95m;
        }

        if (hasCoupon && subtotal >= 50m)
        {
            total -= 7.50m;
        }

        if (itemCount >= 10)
        {
            total *= 0.97m;
        }

        if (weekend)
        {
            total += 2m;
        }

        if (expedited)
        {
            total += 14m;
        }

        if (string.Equals(destination, "international", StringComparison.OrdinalIgnoreCase))
        {
            total += 25m;
        }

        if (loyaltyYears >= 5)
        {
            total -= 3m;
        }

        if (fragile)
        {
            total += 4.25m;
        }

        if (giftWrap)
        {
            total += 3.50m;
        }

        if (firstOrder)
        {
            total *= 0.98m;
        }

        if (seasonalSale)
        {
            total *= 0.90m;
        }

        return decimal.Round(total, 2, MidpointRounding.AwayFromZero);
    }
}
