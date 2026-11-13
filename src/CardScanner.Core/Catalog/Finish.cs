namespace CardScanner.Core.Catalog;

/// <summary>Foil / non-foil / etched: what a printing came in, and what this copy probably is.</summary>
public static class Finish
{
    public sealed record Option(string Key, string Label)
    {
        public override string ToString() => Label;
    }

    /// <summary>The finishes this printing was actually made in (Scryfall's "finishes"), with special foil
    /// names where known (surge foil, galaxy foil, ...).</summary>
    public static IReadOnlyList<Option> OptionsFor(CardInfo card)
    {
        var keys = Keys(card);
        return keys.Select(k => k switch
        {
            "nonfoil" => new Option(k, "Non-foil"),
            "foil" => new Option(k, string.IsNullOrEmpty(card.SpecialFoil) ? "Foil" : $"Foil ({card.SpecialFoil})"),
            "etched" => new Option(k, "Etched foil"),
            "glossy" => new Option(k, "Glossy"),
            _ => new Option(k, k),
        }).ToList();
    }

    /// <summary>
    /// Best guess at this copy's finish, and why. Uses what's certain first: a printing that only came one
    /// way, then the ★ (foil) / • (non-foil) printed between set code and language on newer cards.
    /// Otherwise it can't tell from a photo (that needs the machine's lighting) and says so.
    /// </summary>
    public static (string Key, string Reason, bool Sure) Detect(CardInfo card, bool? collectorFoil)
    {
        var keys = Keys(card);
        if (keys.Count == 1)
            return (keys[0], keys[0] == "nonfoil" ? "only made as non-foil" : "only made as foil", true);
        if (collectorFoil == true && keys.Contains("foil")) return ("foil", "★ in the collector line", true);
        if (collectorFoil == true && keys.Contains("etched")) return ("etched", "★ in the collector line", true);
        if (collectorFoil == false && keys.Contains("nonfoil")) return ("nonfoil", "• in the collector line", true);
        return (keys.Contains("nonfoil") ? "nonfoil" : keys[0], "couldn't tell from the photo — check it", false);
    }

    private static List<string> Keys(CardInfo card)
    {
        var keys = card.Finishes.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).ToList();
        return keys.Count > 0 ? keys : ["nonfoil", "foil"];
    }
}
