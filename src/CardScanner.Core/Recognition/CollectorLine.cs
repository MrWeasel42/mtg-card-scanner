using System.Text.RegularExpressions;

namespace CardScanner.Core.Recognition;

/// <summary>
/// What we could read from the small print at the bottom-left of a card, e.g.
/// "R 0381 DSK • EN" or "147/269 R ELD EN". Older cards have no collector line.
/// </summary>
public sealed partial record CollectorLine(string Raw, HashSet<string> Numbers, HashSet<string> SetCodes, bool? Foil, int? CopyrightYear = null)
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
            if (s.Length >= 3 && !s.All(char.IsDigit)) sets.Add(s.ToLowerInvariant());
            var mark = m.Groups[2].Value;
            if (mark is "★" or "*") foil = true;
            else if (mark is "·" or "•" or "." && foil is null) foil = false;
        }
        // Old cards print a copyright year ("©1995", "1993-2005"): the latest year is the print year.
        int? year = null;
        foreach (Match m in Year().Matches(up))
            if (int.TryParse(m.Value, out var y) && y is >= 1993 and <= 2030) year = Math.Max(year ?? 0, y);
        return new CollectorLine(raw, numbers, sets, foil, year);
    }

    /// <summary>Adds the number printed after "Wizards of the Coast" on older and retro frames.</summary>
    public CollectorLine WithCopyrightNumbers(string copyrightLine)
    {
        var nums = new HashSet<string>(Numbers);
        foreach (Match m in AfterCoast().Matches(copyrightLine.ToUpperInvariant()))
        {
            var n = m.Groups[1].Value.Replace('O', '0').TrimStart('0');
            if (n.Length > 0) nums.Add(n);
        }
        int? year = CopyrightYear;
        foreach (Match m in Year().Matches(copyrightLine))
            if (int.TryParse(m.Value, out var y) && y is >= 1993 and <= 2030) year = Math.Max(year ?? 0, y);
        return this with { Raw = (Raw + " | " + copyrightLine).Trim(' ', '|'), Numbers = nums, CopyrightYear = year };
    }

    // "COAST, INC. 128/350", "COAST 14", "C0AST LLC 72/145"
    [GeneratedRegex(@"C[O0][A-Z]{1,3}T[^0-9]{0,12}?([0-9O]{1,4})(?:\s*/\s*[0-9O]{1,4})?")]
    private static partial Regex AfterCoast();

    // "R0381", "RO325", "0015", "147/269R", "C 0198", "MC360" (OCR noise before the number)
    [GeneratedRegex(@"(?<![A-Z0-9])[A-Z]{0,2}\s?([0-9O]*[0-9][0-9O]*)(?:\s*/\s*[0-9O]{1,4})?\s?[CURMLSTPB]?(?![0-9])")]
    private static partial Regex Number();

    // "DSK • EN", "ECL★EN", "SLDEN", "LTR·EN", "LTCENCALDER" (artist name glued on), "SOA*JP" (Japanese
    // showcase printings found in English boosters)
    [GeneratedRegex(@"(?<![A-Z0-9])([A-Z0-9]{3,5}?)\s*([·•★*.]?)\s*(?:EN|JP)(?![A-Z0-9]*[·•★])")]
    private static partial Regex SetAndLanguage();

    [GeneratedRegex(@"(?<![0-9])(19|20)[0-9]{2}(?![0-9])")]
    private static partial Regex Year();
}
