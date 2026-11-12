using System.Text.RegularExpressions;

namespace CardScanner.Core.Recognition;

/// <summary>
/// What we could read from the small print at the bottom-left of a card, e.g.
/// "R 0381 DSK • EN" or "147/269 R ELD EN". Older cards have no collector line.
/// </summary>
public sealed partial record CollectorLine(string Raw, HashSet<string> Numbers, HashSet<string> SetCodes, bool? Foil)
{
    public static readonly CollectorLine Empty = new("", [], [], null);

    public bool HasAny => Numbers.Count > 0 || SetCodes.Count > 0;

    public static CollectorLine Parse(string raw)
    {
        var up = raw.ToUpperInvariant();
        var numbers = new HashSet<string>();
        foreach (Match m in Number().Matches(up))
        {
            var n = m.Groups[1].Value.Replace('O', '0').TrimStart('0');
            if (n.Length > 0) numbers.Add(n);
        }
        var sets = new HashSet<string>();
        bool? foil = null;
        foreach (Match m in SetAndLanguage().Matches(up))
        {
            var s = m.Groups[1].Value;
            if (s.EndsWith("EN") && s.Length > 4) s = s[..^2]; // "LTREN" -> "LTR"
            if (s.Length >= 3 && !s.All(char.IsDigit)) sets.Add(s.ToLowerInvariant());
            var mark = m.Groups[2].Value;
            if (mark is "★" or "*") foil = true;
            else if (mark is "·" or "•" or "." && foil is null) foil = false;
        }
        return new CollectorLine(raw, numbers, sets, foil);
    }

    // "R0381", "RO325", "0015", "147/269R", "C 0198"
    [GeneratedRegex(@"(?<![A-Z0-9])[CURMLSTPB]?\s?([0-9O]{1,4})(?:\s*/\s*[0-9O]{1,4})?\s?[CURMLSTPB]?(?![0-9])")]
    private static partial Regex Number();

    // "DSK • EN", "ECL★EN", "SLDEN", "LTR·EN"
    [GeneratedRegex(@"([A-Z0-9]{3,5})\s*([·•★*.]?)\s*EN\b")]
    private static partial Regex SetAndLanguage();
}
