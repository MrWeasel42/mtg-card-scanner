using System.Text;
using System.Text.RegularExpressions;
using Microsoft.Data.Sqlite;

namespace CardScanner.Core.Recognition;

/// <summary>Lightweight in-memory facts about every printing, for fast lookups while scanning.</summary>
public sealed record PrintingKey(string Id, string Name, string SetCode, string Number, string Layout,
    string SetType = "", string BorderColor = "", int ReleaseYear = 0)
{
    /// <summary>Printings that are rarely what's being scanned: collector-only reprints (Collectors'
    /// Edition, World Championship decks, Pro Tour collector sets, oversized cards) and the tiny
    /// Summer Magic print run, which looks just like Revised.</summary>
    public bool IsUnlikely => SetType == "memorabilia" || SetCode == "sum";
}

/// <summary>
/// In-memory index of every printing: by (normalised) card name, and by set code + collector number.
/// Name lookups tolerate OCR mistakes (fuzzy matching).
/// </summary>
public sealed partial class CardIndex
{
    private static readonly HashSet<string> NotRealCards = ["token", "double_faced_token", "emblem", "art_series"];

    private readonly Dictionary<string, List<PrintingKey>> _byName = new();
    private readonly Dictionary<string, List<PrintingKey>> _byCollector = new();
    private readonly string[] _names;
    private readonly Dictionary<int, List<int>> _namesByLength = new();

    public int Count { get; }

    public CardIndex(string dbPath)
    {
        using var con = new SqliteConnection($"Data Source={dbPath};Mode=ReadOnly;Pooling=False");
        con.Open();
        using var cmd = con.CreateCommand();
        cmd.CommandText = "SELECT id, name, set_code, collector_number, layout, set_type, border_color, released_at FROM cards";
        using var r = cmd.ExecuteReader();
        int n = 0;
        while (r.Read())
        {
            var released = r.IsDBNull(7) ? "" : r.GetString(7);
            var p = new PrintingKey(r.GetString(0), r.GetString(1), r.GetString(2), r.GetString(3),
                r.IsDBNull(4) ? "" : r.GetString(4), r.IsDBNull(5) ? "" : r.GetString(5), r.IsDBNull(6) ? "" : r.GetString(6),
                released.Length >= 4 && int.TryParse(released[..4], out var y) ? y : 0);
            n++;
            if (!NotRealCards.Contains(p.Layout))
            {
                // A card can be found by its full name or by any of its faces ("A // B").
                foreach (var face in p.Name.Split(" // ").Append(p.Name).Distinct())
                {
                    var key = Normalize(face);
                    if (key.Length == 0) continue;
                    if (!_byName.TryGetValue(key, out var list)) _byName[key] = list = [];
                    list.Add(p);
                }
            }
            var ck = CollectorKey(p.SetCode, p.Number);
            if (!_byCollector.TryGetValue(ck, out var cl)) _byCollector[ck] = cl = [];
            cl.Add(p);
        }
        Count = n;
        _names = [.. _byName.Keys];
        for (int i = 0; i < _names.Length; i++)
        {
            int len = _names[i].Length;
            if (!_namesByLength.TryGetValue(len, out var l)) _namesByLength[len] = l = [];
            l.Add(i);
        }
    }

    public IReadOnlyList<PrintingKey> PrintingsOfName(string normalizedName) =>
        _byName.TryGetValue(normalizedName, out var l) ? l : [];

    public IReadOnlyList<PrintingKey> PrintingsAt(string setCode, string number) =>
        _byCollector.TryGetValue(CollectorKey(setCode, number), out var l) ? l : [];

    /// <summary>Best-matching card name for some OCR text, with a 0..1 similarity score.</summary>
    public (string Name, double Score)? MatchName(string text, double minScore = 0.8)
    {
        var q = Normalize(text);
        if (q.Length < 3) return null;
        if (_byName.ContainsKey(q)) return (q, 1.0);
        string? best = null;
        double bestScore = minScore;
        // ratio = 2*LCS/(a+b) can only reach the threshold if the lengths are close enough.
        int minLen = (int)Math.Ceiling(q.Length * minScore / (2 - minScore));
        int maxLen = (int)Math.Floor(q.Length * (2 - minScore) / minScore);
        for (int len = minLen; len <= maxLen; len++)
        {
            if (!_namesByLength.TryGetValue(len, out var idxs)) continue;
            double upper = 2.0 * Math.Min(len, q.Length) / (len + q.Length);
            if (upper < bestScore) continue;
            foreach (var i in idxs)
            {
                double s = Similarity(q, _names[i]);
                if (s > bestScore) { bestScore = s; best = _names[i]; }
            }
        }
        return best is null ? null : (best, bestScore);
    }

    /// <summary>Same as rapidfuzz's fuzz.ratio / 100: 2 * LCS / (len a + len b).</summary>
    public static double Similarity(string a, string b)
    {
        if (a.Length == 0 && b.Length == 0) return 1;
        Span<int> prev = stackalloc int[b.Length + 1];
        Span<int> cur = stackalloc int[b.Length + 1];
        for (int i = 1; i <= a.Length; i++)
        {
            cur[0] = 0;
            for (int j = 1; j <= b.Length; j++)
                cur[j] = a[i - 1] == b[j - 1] ? prev[j - 1] + 1 : Math.Max(prev[j], cur[j - 1]);
            cur.CopyTo(prev);
        }
        return 2.0 * prev[b.Length] / (a.Length + b.Length);
    }

    /// <summary>Lowercase, "Æ" → "ae", accents and punctuation removed, single spaces.</summary>
    public static string Normalize(string s)
    {
        s = s.Replace("Æ", "Ae").Replace("æ", "ae").Normalize(NormalizationForm.FormD);
        var sb = new StringBuilder(s.Length);
        foreach (var ch in s)
        {
            if (char.GetUnicodeCategory(ch) == System.Globalization.UnicodeCategory.NonSpacingMark) continue;
            char c = char.ToLowerInvariant(ch);
            if (c is >= 'a' and <= 'z' or >= '0' and <= '9' or ' ') sb.Append(c);
        }
        return Spaces().Replace(sb.ToString(), " ").Trim();
    }

    public static string CollectorKey(string setCode, string number) =>
        setCode.ToLowerInvariant() + "|" + number.ToLowerInvariant().TrimStart('0');

    [GeneratedRegex(" {2,}")]
    private static partial Regex Spaces();
}
