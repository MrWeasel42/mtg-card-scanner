using System.Globalization;
using System.Text.Json.Serialization;

namespace CardScanner.Core.Sorting;

/// <summary>Quick presets that fill the bins in one go (each bin can then be edited on its own).</summary>
[JsonConverter(typeof(JsonStringEnumConverter))]
public enum SortBy { Price, Alphabet, Color, Rarity, Set }

/// <summary>What one bin's rule looks at.</summary>
[JsonConverter(typeof(JsonStringEnumConverter))]
public enum RuleKind { Price, Color, Letters, Rarity, Set, Type, Anything }

/// <summary>
/// The rule for one bin: which cards it takes. Bins are tried in order from the feeder (bin 1 first); the first
/// bin whose rule fits gets the card. Anything no bin takes, and every flagged card, goes to the end bin.
/// </summary>
public sealed class BinRule
{
    public RuleKind Kind { get; set; } = RuleKind.Price;
    /// <summary>Your own name for the bin; blank = described from the rule.</summary>
    public string Name { get; set; } = "";
    /// <summary>Price range in USD, both ends included: Min &lt;= price &lt;= Max (either end may be open). A card on
    /// the edge between two bins goes to the first of them: "$0–0.50" takes a $0.50 card, "$0.51–1" the next cent up.</summary>
    public decimal? Min { get; set; }
    public decimal? Max { get; set; }
    /// <summary>W, U, B, R, G, M (multicolour), C (colourless), L (lands). A card counts as one of these (front face).</summary>
    public List<string> Colors { get; set; } = [];
    /// <summary>First letters of the name, e.g. "A-F" or "A-F, Q". "#" = starts with a number or symbol.</summary>
    public string Letters { get; set; } = "";
    /// <summary>common, uncommon, rare, mythic, special (special also covers bonus).</summary>
    public List<string> Rarities { get; set; } = [];
    /// <summary>Set codes, e.g. MH3, MH2.</summary>
    public List<string> Sets { get; set; } = [];
    /// <summary>Card types on the front face: Creature, Instant, Sorcery, Artifact, Enchantment, Planeswalker, Land, Battle.</summary>
    public List<string> Types { get; set; } = [];

    public static readonly string[] ColorCodes = ["W", "U", "B", "R", "G", "M", "C", "L"];
    public static readonly string[] ColorNames = ["White", "Blue", "Black", "Red", "Green", "Multicolor", "Colorless", "Lands"];
    public static readonly string[] RarityCodes = ["common", "uncommon", "rare", "mythic", "special"];
    public static readonly string[] TypeNames = ["Creature", "Instant", "Sorcery", "Artifact", "Enchantment", "Planeswalker", "Land", "Battle"];

    public BinRule Clone() => new()
    {
        Kind = Kind, Name = Name, Min = Min, Max = Max, Colors = [.. Colors], Letters = Letters,
        Rarities = [.. Rarities], Sets = [.. Sets], Types = [.. Types],
    };

    [JsonIgnore] public string Label => Name.Trim() is { Length: > 0 } n ? n : Describe();

    public string Describe()
    {
        static string M(decimal d) => "$" + (d == Math.Floor(d) ? d.ToString("0", CultureInfo.InvariantCulture) : d.ToString("0.##", CultureInfo.InvariantCulture));
        switch (Kind)
        {
            case RuleKind.Price:
                return (Min, Max) switch
                {
                    (null, null) => "Any price",
                    (null, { } hi) => $"Up to {M(hi)}",
                    ({ } lo, null) => $"Over {M(lo)}",
                    ({ } lo, { } hi) => $"{M(lo)}–{M(hi)[1..]}",
                };
            case RuleKind.Color:
                return Colors.Count == 0 ? "No colours picked"
                     : string.Join(" + ", ColorCodes.Where(Colors.Contains).Select(c => ColorNames[Array.IndexOf(ColorCodes, c)]));
            case RuleKind.Letters:
                var parts = LetterRanges().Select(r => r == "#" ? "Numbers / symbols" : r.Length == 3 ? $"{r[0]}–{r[2]}" : r).ToList();
                return parts.Count == 0 ? "No letters set" : string.Join(", ", parts);
            case RuleKind.Rarity:
                return Rarities.Count == 0 ? "No rarity picked"
                     : string.Join(" + ", RarityCodes.Where(Rarities.Contains).Select(r => r == "special" ? "Special / bonus" : char.ToUpperInvariant(r[0]) + r[1..]));
            case RuleKind.Set:
                return Sets.Count == 0 ? "No sets listed" : string.Join(", ", Sets.Select(s => s.ToUpperInvariant()));
            case RuleKind.Type:
                return Types.Count == 0 ? "No types picked" : string.Join(" + ", TypeNames.Where(Types.Contains));
            default:
                return "Everything else";
        }
    }

    /// <summary>"A-F, Q, #" → ["A-F", "Q", "#"].</summary>
    public List<string> LetterRanges() =>
        Letters.ToUpperInvariant().Split([',', ';', ' '], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Select(r => new string(r.Where(ch => char.IsLetter(ch) || ch is '-' or '#').ToArray()))
            .Where(r => r.Length > 0).ToList();

    public bool Matches(CardFacts c)
    {
        switch (Kind)
        {
            case RuleKind.Price:
                return c.Price is { } p && (Min is not { } lo || p >= lo) && (Max is not { } hi || p <= hi);
            case RuleKind.Color:
                return Colors.Contains(ColorCodes[BinSorter.ColorIndex(c.Colors, c.TypeLine)]);
            case RuleKind.Letters:
            {
                char first = BinSorter.FirstLetter(c.Name);
                return LetterRanges().Any(r => r == "#" ? first == '\0' : InRange(first, r));
            }
            case RuleKind.Rarity:
            {
                var r = c.Rarity.ToLowerInvariant();
                if (r is not ("common" or "uncommon" or "rare" or "mythic")) r = "special";
                return Rarities.Contains(r);
            }
            case RuleKind.Set:
                return Sets.Any(s => s.Equals(c.SetCode, StringComparison.OrdinalIgnoreCase));
            case RuleKind.Type:
            {
                var front = c.TypeLine.Split(" // ")[0].Split('—')[0];
                return Types.Any(t => front.Contains(t, StringComparison.OrdinalIgnoreCase));
            }
            default:
                return true;
        }
    }

    private static bool InRange(char c, string r)
    {
        if (c == '\0') return false;
        var parts = r.Split('-', StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length == 0) return false;
        char lo = parts[0][0], hi = parts.Length > 1 ? parts[^1][0] : parts[0][^1];
        return c >= lo && c <= hi;
    }
}

/// <summary>
/// The machine's bins. Bins are numbered from the feeder: 1 is the first door, the last bin in use is the end of
/// the line and always takes the Flagged cards (not identified, not sure, no price) and anything no other bin
/// takes. Turning bins off (the 3-bin prototype uses 3 of the 9) sends anything meant for a bin that's off to the
/// end bin as well.
/// </summary>
public sealed class BinSetup
{
    public const int MaxBins = 9;

    /// <summary>How many bins the machine has switched on, counted from the feeder (2..9).</summary>
    public int BinsInUse { get; set; } = 3;

    /// <summary>One rule per bin 1..8 (index 0 = bin 1); null = the bin takes nothing. Bin 9 is only ever the end bin.
    /// Empty on settings saved by older versions: filled from the preset below.</summary>
    public List<BinRule?> Rules { get; set; } = [];

    // The preset the rules were made from (and what older versions saved).
    public SortBy By { get; set; } = SortBy.Price;
    public List<decimal> PriceBreaks { get; set; } = [1m, 5m, 10m, 25m, 50m];
    public List<string> AlphaRanges { get; set; } = ["A-F", "G-K", "L-R", "S-Z"];
    public List<string> SetGroups { get; set; } = [];

    public BinSetup Clone() => new()
    {
        BinsInUse = BinsInUse, By = By, PriceBreaks = [.. PriceBreaks], AlphaRanges = [.. AlphaRanges], SetGroups = [.. SetGroups],
        Rules = [.. Rules.Select(r => r?.Clone())],
    };

    public int FlaggedBin => Math.Clamp(BinsInUse, 1, MaxBins);

    /// <summary>The rules, made from the preset if none were saved. Always MaxBins - 1 long.</summary>
    public List<BinRule?> EffectiveRules()
    {
        var rules = Rules.Count > 0 ? Rules : BinSorter.PresetRules(this);
        var list = rules.Take(MaxBins - 1).ToList();
        while (list.Count < MaxBins - 1) list.Add(null);
        return list;
    }

    /// <summary>Replaces the rules with the ones the preset makes.</summary>
    public void ApplyPreset(SortBy by)
    {
        By = by;
        Rules = BinSorter.PresetRules(this);
    }
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

/// <summary>Where a card goes. <see cref="WantedBin"/> is the bin whose rule took it, with every bin on (0 = Flagged).</summary>
public sealed record BinChoice(int Bin, string Label, int WantedBin, string Reason)
{
    public bool Rerouted => WantedBin != 0 && WantedBin != Bin;
}

public static class BinSorter
{
    public static readonly string[] ColorCategories = BinRule.ColorNames;
    public static readonly string[] RarityCategories = ["Common", "Uncommon", "Rare", "Mythic", "Special / bonus"];

    /// <summary>The bins' rules as labels, bin 1 first, skipping empty bins.</summary>
    public static List<string> Categories(BinSetup s) => [.. s.EffectiveRules().Where(r => r is not null).Select(r => r!.Label)];

    /// <summary>Label for each bin 1..9 as the machine is set up now ("off" past the bins in use).</summary>
    public static List<string> BinLabels(BinSetup s)
    {
        var rules = s.EffectiveRules();
        var labels = new List<string>();
        for (int b = 1; b <= BinSetup.MaxBins; b++)
        {
            if (b > s.BinsInUse) labels.Add("off");
            else if (b == s.FlaggedBin) labels.Add("Flagged + everything else");
            else labels.Add(rules[b - 1]?.Label ?? "(empty)");
        }
        return labels;
    }

    public static BinChoice Choose(BinSetup s, CardFacts c)
    {
        int end = s.FlaggedBin;
        if (c.Flagged) return new BinChoice(end, "Flagged", 0, c.FlagReason ?? "flagged");
        var rules = s.EffectiveRules();
        for (int i = 0; i < rules.Count; i++)
        {
            var rule = rules[i];
            if (rule is null || !rule.Matches(c)) continue;
            int wanted = i + 1;
            string why = Why(rule, c);
            if (wanted < end) return new BinChoice(wanted, rule.Label, wanted, why);
            // its bin is switched off, or it's the end bin itself: it rides to the end
            string note = wanted == end ? "shares the end bin with Flagged" : $"bin {wanted} is off";
            return new BinChoice(end, rule.Label, wanted, $"{why} · {note}");
        }
        // No bin takes it. A price-sorted setup with no price for the card: that's a Flagged card.
        if (c.Price is null && rules.Any(r => r?.Kind == RuleKind.Price))
            return new BinChoice(end, "Flagged", 0, "no price");
        return new BinChoice(end, "Everything else", end, "no bin's rule fits");
    }

    private static string Why(BinRule rule, CardFacts c) => rule.Kind switch
    {
        RuleKind.Price => $"${c.Price!.Value.ToString("0.00", CultureInfo.InvariantCulture)}",
        RuleKind.Color => ColorCategories[ColorIndex(c.Colors, c.TypeLine)],
        RuleKind.Letters => FirstLetter(c.Name) is var f && f != '\0' ? $"starts with {f}" : "starts with a number / symbol",
        RuleKind.Rarity => c.Rarity,
        RuleKind.Set => c.SetCode.ToUpperInvariant(),
        RuleKind.Type => c.TypeLine.Split(" // ")[0],
        _ => rule.Label,
    };

    /// <summary>Rules for bins 1..8 from a preset (categories past bin 8 go to the end bin).</summary>
    public static List<BinRule?> PresetRules(BinSetup s)
    {
        var list = new List<BinRule?>();
        switch (s.By)
        {
            case SortBy.Price:
            {
                var b = s.PriceBreaks.Where(x => x > 0).Distinct().OrderBy(x => x).ToList();
                if (b.Count == 0) { list.Add(new BinRule { Kind = RuleKind.Price }); break; }
                list.Add(new BinRule { Kind = RuleKind.Price, Max = b[0] });
                for (int i = 1; i < b.Count; i++) list.Add(new BinRule { Kind = RuleKind.Price, Min = b[i - 1], Max = b[i] });
                list.Add(new BinRule { Kind = RuleKind.Price, Min = b[^1] });
                break;
            }
            case SortBy.Alphabet:
                foreach (var r in s.AlphaRanges.Where(r => r.Trim().Length > 0)) list.Add(new BinRule { Kind = RuleKind.Letters, Letters = r.Trim() });
                list.Add(new BinRule { Kind = RuleKind.Letters, Letters = "#" });
                break;
            case SortBy.Color:
                foreach (var code in BinRule.ColorCodes) list.Add(new BinRule { Kind = RuleKind.Color, Colors = [code] });
                break;
            case SortBy.Rarity:
                foreach (var r in BinRule.RarityCodes) list.Add(new BinRule { Kind = RuleKind.Rarity, Rarities = [r] });
                break;
            case SortBy.Set:
                foreach (var g in s.SetGroups)
                {
                    var codes = g.Split([',', ' ', ';', '/'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
                                 .Select(x => x.ToUpperInvariant()).Distinct().ToList();
                    if (codes.Count > 0) list.Add(new BinRule { Kind = RuleKind.Set, Sets = codes });
                }
                list.Add(new BinRule { Kind = RuleKind.Anything, Name = "Other sets" });
                break;
        }
        return list.Take(BinSetup.MaxBins - 1).ToList();
    }

    /// <summary>Kept for older callers: price bracket labels.</summary>
    public static List<string> PriceCategories(IEnumerable<decimal> breaks) =>
        [.. PresetRules(new BinSetup { By = SortBy.Price, PriceBreaks = [.. breaks] }).Select(r => r!.Label)];

    /// <summary>0 White … 4 Green, 5 Multicolor, 6 Colorless, 7 Lands (the front face is a land). Double-faced
    /// cards go by their front face: a blue creature with a land on the back is Blue.</summary>
    public static int ColorIndex(string colors, string typeLine)
    {
        var front = typeLine.Split(" // ")[0];
        if (front.Contains("Land", StringComparison.OrdinalIgnoreCase)) return 7;
        var cs = "WUBRG".Where(ch => colors.Contains(ch)).ToList();
        return cs.Count switch { 0 => 6, 1 => "WUBRG".IndexOf(cs[0]), _ => 5 };
    }

    internal static char FirstLetter(string name)
    {
        name = name.Replace("Æ", "AE").Replace("æ", "ae").Replace("Œ", "OE").Replace("œ", "oe");
        foreach (var ch in name.Normalize(System.Text.NormalizationForm.FormD))
            if (char.IsLetter(ch)) return char.ToUpperInvariant(ch);
            else if (char.IsDigit(ch)) return '\0';
        return '\0';
    }
}
