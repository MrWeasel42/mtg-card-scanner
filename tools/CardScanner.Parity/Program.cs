// Usage: CardScanner.Parity <photos dir> <catalog pictures dir> <out.json>
// For every photo: the recognizer's full result, then the checks the app runs once the candidates' pictures are on
// disk (crop refine against the top match, the ★/• mark, the close-up detail compare of look-alike printings).
using System.Globalization;
using System.Text.Json;
using CardScanner.Core;
using CardScanner.Core.Catalog;
using CardScanner.Core.Recognition;
using CardScanner.Core.Vision;
using OpenCvSharp;

var photosDir = args[0];
var picsDir = args[1];
var outPath = args[2];
var paths = new AppPaths(Path.Combine(Path.GetTempPath(), "mtgscan-parity"));
var manifest = await new CatalogUpdater(paths).UpdateAsync(new Progress<DownloadProgress>(_ => { }));
Console.WriteLine($"Catalog {manifest.CatalogVersion}");
using var rec = Recognizer.Load(paths);
var inv = CultureInfo.InvariantCulture;
var results = new List<object>();
Directory.CreateDirectory(picsDir);
using var http = CatalogUpdater.CreateHttpClient();
// Same as the app's ThumbnailCache: Scryfall's "large" picture, else "normal".
async Task FetchAsync(CardInfo c)
{
    var f = Path.Combine(picsDir, c.Id + "_large.jpg");
    if (File.Exists(f) || !c.ImageUrl.StartsWith("https://")) return;
    foreach (var url in new[] { c.ImageUrl.Replace("/normal/", "/large/"), c.ImageUrl })
    {
        try { await File.WriteAllBytesAsync(f, await http.GetByteArrayAsync(url)); return; }
        catch (Exception) { }
    }
}
foreach (var file in Directory.GetFiles(photosDir, "*.jpg").OrderBy(f => f, StringComparer.Ordinal))
{
    var r = rec.IdentifyFile(file);
    var top = r.Best;
    foreach (var c in r.Candidates) await FetchAsync(c.Card);
    object? refine = null, star = null, detail = null;
    string? Pic(CardInfo c) { var p = Path.Combine(picsDir, c.Id + "_large.jpg"); return File.Exists(p) ? p : null; }
    var cardJpeg = r.CardImageJpeg;
    if (top is not null && Pic(top.Card) is { } refPath && r.CardOutlineFound)
    {
        var corners = r.OutlineCorners.Split(' ', StringSplitOptions.RemoveEmptyEntries).Select(p => p.Split(','))
            .Select(xy => new Point2f(float.Parse(xy[0], inv), float.Parse(xy[1], inv))).ToArray();
        using var photo = Cv2.ImRead(file, ImreadModes.Color);
        using var reference = Cv2.ImRead(refPath, ImreadModes.Color);
        var better = CropRefine.Refine(photo, corners, reference, r.UpsideDown);
        refine = better?.Select(p => new[] { p.X, p.Y }).ToArray();
        var j = Recognizer.RefineCrop(r, refPath);
        if (j is not null) cardJpeg = j;
    }
    var (st, dot) = StarMark.Score(cardJpeg);
    star = new[] { st, dot };
    if (top is not null)
    {
        var group = r.Candidates.Where(c => c.Card.Name == top.Card.Name && Pic(c.Card) is not null)
            .Select(c => (c.Card.Id, Pic(c.Card)!)).ToList();
        if (group.Count >= 2) detail = DetailCompare.Score(cardJpeg, group).Select(x => new { id = x.Id, score = x.Score }).ToList();
    }
    results.Add(new
    {
        file = Path.GetFileName(file),
        ms = (int)r.Elapsed.TotalMilliseconds,
        outline = r.CardOutlineFound, method = r.OutlineMethod, corners = r.OutlineCorners,
        upsideDown = r.UpsideDown, nameRead = r.NameRead,
        collector = new
        {
            raw = r.Collector.Raw, numbers = r.Collector.Numbers.OrderBy(x => x, StringComparer.Ordinal).ToList(),
            sets = r.Collector.SetCodes.OrderBy(x => x, StringComparer.Ordinal).ToList(), foil = r.Collector.Foil,
            year = r.Collector.CopyrightYear, lang = r.Collector.Language, totals = r.Collector.SetTotals.OrderBy(x => x).ToList(),
        },
        border = r.BorderColor, list = r.ListSymbolScore, shootingStar = r.ShootingStarScore,
        pinned = r.Pinned, pinReason = r.PinReason, flagReason = r.FlagReason,
        candidates = r.Candidates.Select(c => new
        {
            id = c.Card.Id, name = c.Card.Name, set = c.Card.SetCode, number = c.Card.CollectorNumber,
            score = c.Score, sim = c.ImageSimilarity, nameMatched = c.NameMatched, numberMatched = c.NumberMatched, setMatched = c.SetMatched,
        }).ToList(),
        refine, star, detail,
    });
    Console.WriteLine($"{Path.GetFileName(file)}: {top?.Card.Name} {top?.Card.SetCode} #{top?.Card.CollectorNumber}{(r.Pinned ? " PIN" : "")} {(int)r.Elapsed.TotalMilliseconds} ms");
}
File.WriteAllText(outPath, JsonSerializer.Serialize(new { catalog = manifest.CatalogVersion, results },
    new JsonSerializerOptions { WriteIndented = true }));
