using System.Globalization;
using System.Text;
using CardScanner.App.ViewModels;

namespace CardScanner.App;

/// <summary>
/// The export formats. Each writes one file for a set of reviewed cards. Formats follow what each site's own
/// import expects (ManaBox: its own export's columns; Moxfield and Deckbox: their collection CSVs; TCGplayer: a
/// Mass Entry list; General: everything we know about each card).
/// </summary>
public static class CsvExport
{
    public sealed record Format(string Key, string Title, string Description, string FileSuffix);

    public static readonly Format[] Formats =
    [
        new("ManaBox", "ManaBox", "Exact printing by Scryfall ID, with finish, condition and language. Import in ManaBox: Collection → Import → CSV.", "ManaBox.csv"),
        new("Moxfield", "Moxfield", "Moxfield collection import (Collection → Import → CSV). Unreviewed flagged cards are tagged needs-check.", "Moxfield.csv"),
        new("Deckbox", "Deckbox", "Deckbox inventory import (also read by many other collection sites).", "Deckbox.csv"),
        new("TCGplayer", "TCGplayer list", "A Mass Entry list (1 Card Name [SET]) to paste at tcgplayer.com/massentry to price or buy the cards. TCGplayer has no collection import for non-sellers.", "TCGplayer Mass Entry.txt"),
        new("Roca", "ROCA / TCGplayer", "Same columns as a ROCA Sorter export: one row per scan with TCGplayer product ID, bin, REJECT for flagged cards, confidence and photo. Good for comparing runs and for TCGplayer-based tools.", "ROCA style.csv"),
        new("General", "General CSV", "One row per scanned card with everything: printing, finish, price, colors, type, bin, why it was flagged.", "All details.csv"),
    ];

    private sealed record Row(CardScanner.Core.Catalog.CardInfo Card, string Finish, string Condition, bool Altered, bool Misprint,
                              bool Unchecked, int Qty);

    private static string Q(string? v) => "\"" + (v ?? "").Replace("\"", "\"\"") + "\"";

    /// <summary>Writes the chosen formats into dir. Returns the files written and the card count.</summary>
    public static (List<string> Files, int Cards, int Unreviewed) Write(IReadOnlyList<ResultItemViewModel> items, string dir, string baseName,
                                                                        IEnumerable<string> formats)
    {
        var usable = items.Where(r => r.HasResult && r.ShownCard is not null && r.Verdict is not (Verdict.NotListed or Verdict.NameOnly)).ToList();
        var rows = usable
            .GroupBy(r => (r.ShownCard!.Id, Finish: r.SelectedFinish?.Key ?? "nonfoil", r.Condition, r.Altered, r.Misprint,
                           Unchecked: r.Verdict == Verdict.None && (r.Bin?.WantedBin == 0 || r.IsFlagged)))
            .Select(g => new Row(g.First().ShownCard!, g.Key.Finish, g.Key.Condition, g.Key.Altered, g.Key.Misprint, g.Key.Unchecked, g.Count()))
            .OrderBy(r => r.Card.Name).ToList();
        var files = new List<string>();
        if (rows.Count == 0) return (files, 0, 0);
        Directory.CreateDirectory(dir);
        foreach (var f in Formats.Where(f => formats.Contains(f.Key)))
        {
            string text = f.Key switch
            {
                "ManaBox" => ManaBox(rows),
                "Moxfield" => Moxfield(rows),
                "Deckbox" => Deckbox(rows),
                "TCGplayer" => Tcgplayer(rows),
                "Roca" => Roca(items),
                _ => General(usable),
            };
            var path = Path.Combine(dir, $"{baseName} - {f.FileSuffix}");
            File.WriteAllText(path, text, new UTF8Encoding(false));
            files.Add(path);
        }
        return (files, rows.Sum(r => r.Qty), rows.Where(r => r.Unchecked).Sum(r => r.Qty));
    }

    private static string ManaCond(string c) => c switch
    {
        "Lightly Played" => "lightly_played", "Moderately Played" => "moderately_played",
        "Heavily Played" => "heavily_played", "Damaged" => "damaged", _ => "near_mint",
    };
    private static string Cond(string c) => string.IsNullOrEmpty(c) ? "Near Mint" : c;
    private static string TF(bool b) => b ? "true" : "false";

    // Same columns, order and values as a ManaBox export (checked against one).
    private static string ManaBox(List<Row> rows)
    {
        var sb = new StringBuilder("Name,Set code,Set name,Collector number,Foil,Rarity,Quantity,ManaBox ID,Scryfall ID,Purchase price,Misprint,Altered,Signed,Condition,Language,Proxy,Purchase price currency\n");
        foreach (var r in rows)
            sb.Append($"{Q(r.Card.Name)},{r.Card.SetCode.ToUpperInvariant()},{Q(r.Card.SetName)},{r.Card.CollectorNumber},{(r.Finish == "nonfoil" ? "normal" : r.Finish)},{r.Card.Rarity},{r.Qty},,{r.Card.Id},,{TF(r.Misprint)},{TF(r.Altered)},false,{ManaCond(r.Condition)},{r.Card.Lang},false,\n");
        return sb.ToString();
    }

    // Moxfield's own collection export columns.
    private static string Moxfield(List<Row> rows)
    {
        var sb = new StringBuilder("\"Count\",\"Tradelist Count\",\"Name\",\"Edition\",\"Condition\",\"Language\",\"Foil\",\"Tags\",\"Last Modified\",\"Collector Number\",\"Alter\",\"Proxy\",\"Purchase Price\"\n");
        foreach (var r in rows)
        {
            string foil = r.Finish switch { "foil" => "foil", "etched" => "etched", _ => "" };
            sb.Append($"\"{r.Qty}\",\"0\",{Q(r.Card.Name)},\"{r.Card.SetCode.ToLowerInvariant()}\",{Q(Cond(r.Condition))},{Q(r.Card.LanguageName)},\"{foil}\",\"{(r.Unchecked ? "needs-check" : "")}\",\"\",{Q(r.Card.CollectorNumber)},\"{(r.Altered ? "True" : "False")}\",\"False\",\"\"\n");
        }
        return sb.ToString();
    }

    private static string Deckbox(List<Row> rows)
    {
        var sb = new StringBuilder("Count,Tradelist Count,Name,Edition,Card Number,Condition,Language,Foil,Signed,Artist Proof,Altered Art,Misprint,Promo,Textless,My Price\n");
        foreach (var r in rows)
            sb.Append($"{r.Qty},0,{Q(r.Card.Name)},{Q(r.Card.SetName)},{r.Card.CollectorNumber},{Cond(r.Condition)},{r.Card.LanguageName},{(r.Finish == "nonfoil" ? "" : "foil")},,,{(r.Altered ? "altered" : "")},{(r.Misprint ? "misprint" : "")},,,\n");
        return sb.ToString();
    }

    // TCGplayer Mass Entry: "2 Lightning Bolt [M11]". Double-faced cards go by their front face's name.
    private static string Tcgplayer(List<Row> rows)
    {
        var sb = new StringBuilder();
        foreach (var g in rows.GroupBy(r => (Name: r.Card.Name.Split(" // ")[0], Set: r.Card.SetCode.ToUpperInvariant())))
            sb.Append($"{g.Sum(r => r.Qty)} {g.Key.Name} [{g.Key.Set}]\n");
        return sb.ToString();
    }

    // ROCA Sorter Max export: same header and value style (rejects first with Sequence ID 0 and bin REJECT,
    // then sorted cards numbered 1, 2, 3...). Names and set names are Scryfall's, not TCGplayer's.
    private static string Roca(IReadOnlyList<ResultItemViewModel> items)
    {
        var sb = new StringBuilder("Sequence ID,Output Bin ID,Rejected,TCGp Product ID,OmniChannel ID,Product Line,Set Name,Card Name,Number,Rarity,Condition ID,Condition,Finish,TCG Market Price,Confidence,Image Path\n");
        static bool Known(ResultItemViewModel r) => r.HasResult && r.ShownCard is not null && r.Verdict is not (Verdict.NotListed or Verdict.NameOnly);
        static bool Rejected(ResultItemViewModel r) => !Known(r) || (r.IsFlagged && r.Verdict == Verdict.None);
        var ordered = items.Where(r => r.HasResult).OrderBy(r => !Rejected(r)).ThenBy(r => r.ScanNumber).ToList();
        int seq = 0;
        foreach (var r in ordered)
        {
            bool rej = Rejected(r);
            var c = Known(r) ? r.ShownCard : null;
            string finish = r.SelectedFinish?.Key ?? "nonfoil";
            string tcgId = c is null ? "" : finish == "etched" && c.TcgplayerEtchedId.Length > 0 ? c.TcgplayerEtchedId
                         : c.TcgplayerId.Length > 0 ? c.TcgplayerId : "Unavailable";
            string cond = Cond(r.Condition);
            int condId = cond switch { "Lightly Played" => 2, "Moderately Played" => 3, "Heavily Played" => 4, "Damaged" => 5, _ => 1 };
            string rarity = c?.Rarity switch
            {
                "common" => "C", "uncommon" => "U", "rare" => "R", "mythic" => "M", "special" => "S", null or "" => "",
                var x => x[..1].ToUpperInvariant(),
            };
            sb.Append(string.Join(",", new[]
            {
                rej ? "0" : (++seq).ToString(CultureInfo.InvariantCulture),
                rej ? "REJECT" : r.Bin?.Bin.ToString(CultureInfo.InvariantCulture) ?? "",
                rej ? "Y" : "N",
                tcgId, "", c is null ? "" : "Magic", Q(c?.SetName), Q(c?.Name), Q(c?.CollectorNumber), rarity,
                condId.ToString(CultureInfo.InvariantCulture), cond,
                c is null ? "" : finish switch { "foil" => "Foil", "etched" => "Etched", _ => "Normal" },
                (r.Price ?? 0m).ToString("0.##", CultureInfo.InvariantCulture),
                c is null ? "None" : r.IsFlagged ? "FAIR" : "GOOD",
                Q(r.Photo),
            }));
            sb.Append('\n');
        }
        return sb.ToString();
    }

    private static string General(List<ResultItemViewModel> items)
    {
        var sb = new StringBuilder("Scan,Name,Set code,Set name,Collector number,Finish,Rarity,Language,Condition,Altered,Misprint,Price USD,Colors,Type,Bin,Bin label,Bin reason,Pinned by,Flagged,Reviewed,Scryfall ID,Photo\n");
        foreach (var r in items.OrderBy(i => i.ScanNumber))
        {
            var c = r.ShownCard!;
            sb.Append(string.Join(",", new[]
            {
                Q(r.ScanLabel), Q(c.Name), c.SetCode.ToUpperInvariant(), Q(c.SetName), Q(c.CollectorNumber), r.SelectedFinish?.Key ?? "nonfoil",
                c.Rarity, c.LanguageName, Q(Cond(r.Condition)), TF(r.Altered), TF(r.Misprint),
                r.Price?.ToString("0.00", CultureInfo.InvariantCulture) ?? "", c.Colors, Q(c.TypeLine),
                r.Bin?.Bin.ToString() ?? "", Q(r.Bin?.Label), Q(r.Bin?.Reason), Q(r.PinReason), Q(r.IsFlagged ? r.FlagReason : ""),
                TF(r.Verdict != Verdict.None), c.Id, Q(r.Photo),
            }));
            sb.Append('\n');
        }
        return sb.ToString();
    }
}
