using System.Globalization;
using System.Text.Json.Serialization;

namespace CardScanner.Core.Sorting;

/// <summary>What the bins are sorted by.</summary>
[JsonConverter(typeof(JsonStringEnumConverter))]
public enum SortBy { Price, Alphabet, Color, Rarity, Set }

/// <summary>
/// The machine's bins. Bins are numbered from the feeder: 1 is the first door, the last bin in use is the end of
/// the line and always takes the Flagged cards (not identified, not sure, no price). Turning bins off (the 3-bin
/// prototype uses 3 of the 9) sends anything meant for a bin that's off to the end bin as well.
/// </summary>
public sealed class BinSetup
{
    public const int MaxBins = 9;

    /// <summary>How many bins the machine has switched on, counted from the feeder (2..9).</summary>
    public int BinsInUse { get; set; } = 3;
    public SortBy By { get; set; } = SortBy.Price;
    /// <summary>Price bracket edges in USD: [1, 5, 10, 25, 50] gives Under $1, $1–5, $5–10, $10–25, $25–50, $50+.</summary>
    public List<decimal> PriceBreaks { get; set; } = [1m, 5m, 10m, 25m, 50m];
    /// <summary>Letter ranges by the card's name, one bin each, such as "A-F".</summary>
    public List<string> AlphaRanges { get; set; } = ["A-F", "G-K", "L-R", "S-Z"];
    /// <summary>Set codes for each bin, such as "MH3, MH2". Everything else goes to "Other sets".</summary>
    public List<string> SetGroups { get; set; } = [];

    public BinSetup Clone() => new()
    {
        BinsInUse = BinsInUse, By = By, PriceBreaks = [.. PriceBreaks], AlphaRanges = [.. AlphaRanges], SetGroups = [.. SetGroups],
    };

    public int FlaggedBin => Math.Clamp(BinsInUse, 1, MaxBins);
}

/// <summary>What the rules look at for one card (the printing and finish as identified).</summary>
public sealed record CardFacts(
    string Name,
    decimal? Price,
    string Colors,
    string TypeLine,
    string Rarity,
    string SetCode,
    string CollectorNumber,
    bool Flagged,
    string? FlagReason = null);

/// <summary>Where a card goes. <see cref="WantedBin"/> is where the rules would put it with all 9 bins on (0 = Flagged).</summary>
public sealed record BinChoice(int Bin, string Label, int WantedBin, string Reason)
{
    public bool Rerouted => WantedBin != 0 && WantedBin != Bin;
}

public static class BinSorter
{
    public static readonly string[] ColorCategories = ["White", "Blue", "Black", "Red", "Green", "Multicolor", "Colorless", "Lands"];
    public static readonly string[] RarityCategories = ["Common", "Uncommon", "Rare", "Mythic", "Special / bonus"];

    /// <summary>The categories the rules sort into, in bin order (bin 1 first). The Flagged bin isn't listed.</summary>
    public static List<string> Categories(BinSetup s) => s.By switch
    {
        SortBy.Price => PriceCategories(s.PriceBreaks),
        SortBy.Alphabet => [.. s.AlphaRanges.Select(Norm).Where(r => r.Length > 0), "Other (numbers, symbols)"],
        SortBy.Color => [.. ColorCategories],
        SortBy.Rarity => [.. RarityCategories],
        SortBy.Set => [.. s.SetGroups.Select(g => string.Join(", ", SetCodes(g))).Where(g => g.Length > 0), "Other sets"],
        _ => [],
    };

    /// <summary>Label for each bin 1..9 as the machine is set up now ("off" past the bins in use).</summary>
    public static List<string> BinLabels(BinSetup s)
    {
        var cats = Categories(s);
        var labels = new List<string>();
        for (int b = 1; b <= BinSetup.MaxBins; b++)
        {
            if (b > s.BinsInUse) labels.Add("off");
            else if (b == s.FlaggedBin)
            {
                var extra = cats.Skip(s.BinsInUse - 1).ToList();
                labels.Add(extra.Count == 0 ? "Flagged" : $"Flagged + {string.Join(", ", extra)}");
            }
            else labels.Add(b - 1 < cats.Count ? cats[b - 1] : "(unused)");
        }
        return labels;
    }

    public static BinChoice Choose(BinSetup s, CardFacts c)
    {
        int flagged = s.FlaggedBin;
        if (c.Flagged) return new BinChoice(flagged, "Flagged", 0, c.FlagReason ?? "flagged");

        int cat;
        string why;
        switch (s.By)
        {
            case SortBy.Price:
                if (c.Price is not { } p) return new BinChoice(flagged, "Flagged", 0, "no price");
                var breaks = s.PriceBreaks.OrderBy(x => x).ToList();
                cat = breaks.Count(edge => p >= edge);
                why = $"${p.ToString("0.00", CultureInfo.InvariantCulture)}";
                break;
            case SortBy.Alphabet:
            {
                char first = FirstLetter(c.Name);
                var ranges = s.AlphaRanges.Select(Norm).Where(r => r.Length > 0).ToList();
                cat = ranges.FindIndex(r => InRange(first, r));
                if (cat < 0) cat = ranges.Count;
                why = $"starts with {(first == '\0' ? "?" : first.ToString())}";
                break;
            }
            case SortBy.Color:
                cat = ColorIndex(c.Colors, c.TypeLine);
                why = ColorCategories[cat];
                break;
            case SortBy.Rarity:
                cat = c.Rarity.ToLowerInvariant() switch { "common" => 0, "uncommon" => 1, "rare" => 2, "mythic" => 3, _ => 4 };
                why = c.Rarity;
                break;
            case SortBy.Set:
            {
                var groups = s.SetGroups.Select(SetCodes).Where(g => g.Count > 0).ToList();
                cat = groups.FindIndex(g => g.Contains(c.SetCode.ToUpperInvariant()));
                if (cat < 0) cat = groups.Count;
                why = c.SetCode.ToUpperInvariant();
                break;
            }
            default:
                return new BinChoice(flagged, "Flagged", 0, "no rule");
        }

        var cats = Categories(s);
        string label = cat < cats.Count ? cats[cat] : "?";
        int wanted = cat + 1;                                      // with every bin on
        if (wanted < flagged) return new BinChoice(wanted, label, wanted, why);
        // its bin is switched off (or there are more categories than bins): it rides to the end bin
        string note = wanted <= s.BinsInUse ? "shares the end bin with Flagged"
                    : wanted <= BinSetup.MaxBins - 1 ? $"bin {wanted} is off" : "more categories than bins";
        return new BinChoice(flagged, label, wanted, $"{why} · {note}");
    }

    public static List<string> PriceCategories(IEnumerable<decimal> breaksIn)
    {
        var b = breaksIn.Where(x => x > 0).Distinct().OrderBy(x => x).ToList();
        static string N(decimal d) => d == Math.Floor(d) ? d.ToString("0", CultureInfo.InvariantCulture) : d.ToString("0.##", CultureInfo.InvariantCulture);
        static string M(decimal d) => "$" + N(d);
        if (b.Count == 0) return ["Any price"];
        var list = new List<string> { $"Under {M(b[0])}" };
        for (int i = 1; i < b.Count; i++) list.Add($"{M(b[i - 1])}–{N(b[i])}");
        list.Add($"{M(b[^1])}+");
        return list;
    }

    /// <summary>0 White … 4 Green, 5 Multicolor, 6 Colorless, 7 Lands (any card whose type line has Land).</summary>
    public static int ColorIndex(string colors, string typeLine)
    {
        if (typeLine.Contains("Land", StringComparison.OrdinalIgnoreCase)) return 7;
        var cs = "WUBRG".Where(ch => colors.Contains(ch)).ToList();
        return cs.Count switch { 0 => 6, 1 => "WUBRG".IndexOf(cs[0]), _ => 5 };
    }

    private static char FirstLetter(string name)
    {
        name = name.Replace("Æ", "AE").Replace("æ", "ae").Replace("Œ", "OE").Replace("œ", "oe");
        foreach (var ch in name.Normalize(System.Text.NormalizationForm.FormD))
            if (char.IsLetter(ch)) return char.ToUpperInvariant(ch);
            else if (char.IsDigit(ch)) return '\0';
        return '\0';
    }

    private static string Norm(string r) => new(r.ToUpperInvariant().Where(ch => char.IsLetter(ch) || ch == '-').ToArray());

    private static bool InRange(char c, string r)
    {
        if (c == '\0') return false;
        var parts = r.Split('-', StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length == 0) return false;
        char lo = parts[0][0], hi = parts.Length > 1 ? parts[^1][0] : parts[0][^1];
        return c >= lo && c <= hi;
    }

    private static List<string> SetCodes(string group) =>
        group.Split([',', ' ', ';', '/'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
             .Select(x => x.ToUpperInvariant()).Distinct().ToList();
}
