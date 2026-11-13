using Microsoft.Data.Sqlite;

namespace CardScanner.Core.Catalog;

/// <summary>One printing of a card, as stored in the catalog.</summary>
public sealed record CardInfo(
    string Id,
    string Name,
    string SetCode,
    string SetName,
    string CollectorNumber,
    string ReleasedAt,
    string Frame,
    string Finishes,
    string PromoTypes,
    string SpecialFoil,
    decimal? PriceUsd,
    decimal? PriceUsdFoil,
    decimal? PriceUsdEtched,
    string ImageUrl,
    string Rarity = "")
{
    /// <summary>Rarity of this exact printing: common, uncommon, rare, mythic, special or bonus.</summary>
    public string RarityLabel => Rarity is { Length: > 0 } r ? char.ToUpperInvariant(r[0]) + r[1..] : "";
    public string SetLabel => $"{SetName} ({SetCode.ToUpperInvariant()}) #{CollectorNumber}";
    public bool IsListReprint => SetCode is "plst" or "ulst";
    public string? BestPriceText => PriceUsd is { } p ? $"${p:0.00}" : PriceUsdFoil is { } f ? $"${f:0.00} foil" : null;
}

/// <summary>Read-only access to the card database.</summary>
public sealed class CardCatalog : IDisposable
{
    private readonly SqliteConnection _con;
    private const string Columns =
        "id, name, set_code, set_name, collector_number, released_at, frame, finishes, promo_types, " +
        "special_foil, price_usd, price_usd_foil, price_usd_etched, image_url, rarity";

    public CardCatalog(string dbPath)
    {
        _con = new SqliteConnection(new SqliteConnectionStringBuilder
        {
            DataSource = dbPath,
            Mode = SqliteOpenMode.ReadOnly,
            Pooling = false,
        }.ToString());
        _con.Open();
    }

    public CardInfo? Get(string id) => GetMany([id]).GetValueOrDefault(id);

    public Dictionary<string, CardInfo> GetMany(IReadOnlyCollection<string> ids)
    {
        var result = new Dictionary<string, CardInfo>();
        if (ids.Count == 0) return result;
        using var cmd = _con.CreateCommand();
        var names = ids.Select((_, i) => "$p" + i).ToList();
        cmd.CommandText = $"SELECT {Columns} FROM cards WHERE id IN ({string.Join(",", names)})";
        int k = 0;
        foreach (var id in ids) cmd.Parameters.AddWithValue(names[k++], id);
        using var r = cmd.ExecuteReader();
        while (r.Read())
        {
            var card = Read(r);
            result[card.Id] = card;
        }
        return result;
    }

    /// <summary>All printings with this exact name (for the "pick the right one" list in review).</summary>
    public List<CardInfo> PrintingsOf(string name)
    {
        using var cmd = _con.CreateCommand();
        cmd.CommandText = $"SELECT {Columns} FROM cards WHERE name = $n ORDER BY released_at";
        cmd.Parameters.AddWithValue("$n", name);
        using var r = cmd.ExecuteReader();
        var list = new List<CardInfo>();
        while (r.Read()) list.Add(Read(r));
        return list;
    }

    private static CardInfo Read(SqliteDataReader r) => new(
        r.GetString(0), r.GetString(1), r.GetString(2), r.GetString(3), r.GetString(4),
        Str(r, 5), Str(r, 6), Str(r, 7), Str(r, 8), Str(r, 9),
        Dec(r, 10), Dec(r, 11), Dec(r, 12), Str(r, 13), Str(r, 14));

    private static string Str(SqliteDataReader r, int i) => r.IsDBNull(i) ? "" : r.GetString(i);
    private static decimal? Dec(SqliteDataReader r, int i) => r.IsDBNull(i) ? null : (decimal)r.GetDouble(i);

    public void Dispose() => _con.Dispose();
}
