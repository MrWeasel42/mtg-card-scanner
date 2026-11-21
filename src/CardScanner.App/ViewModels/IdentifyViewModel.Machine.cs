using System.Globalization;
using System.IO.Compression;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using CardScanner.Core.Catalog;

namespace CardScanner.App.ViewModels;

/// <summary>
/// The card sorter machine. The machine runs its own sessions (bins, review, CSVs, its touchscreen); this PC is
/// its identifier while the app is open:
///   POST /api/identify     one photo → the card, its top matches and finishes (nothing is added to a PC session)
///   POST /api/feedback     the review on the machine (right / other printing / wrong + note) → the accuracy log
///   POST /api/printings    every printing of a name;  POST /api/search  names containing some text
///   GET  /api/card-image/&lt;scryfall id&gt;   card picture for the machine's review screen
///   GET  /api/setup        the bin setup saved here, offered on the machine as "My PC setup"
/// And the backup: every finished machine session is copied to Sessions\Machine\ while the app runs.
/// </summary>
public partial class IdentifyViewModel
{
    private readonly Dictionary<string, (ResultItemViewModel Item, string File)> _machineItems = [];
    private readonly Queue<string> _machineOrder = new();
    private int _machineSeq;
    private string? _machineHost;
    private static readonly HttpClient MachineHttp = new() { Timeout = TimeSpan.FromSeconds(60) };

    private static object CardJson(CardInfo c) => new
    {
        id = c.Id, name = c.Name, setCode = c.SetCode, setName = c.SetName, number = c.CollectorNumber, rarity = c.Rarity,
        colors = c.Colors, typeLine = c.TypeLine, lang = c.Lang,
        finishes = c.Finishes.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries),
        prices = new { nonfoil = c.PriceUsd, foil = c.PriceUsdFoil, etched = c.PriceUsdEtched },
        imageUrl = c.ImageUrl,
    };

    private static JsonElement? BodyJson(PhoneLink.Request req)
    {
        try { return JsonDocument.Parse(req.Body.Length == 0 ? "{}"u8.ToArray() : req.Body).RootElement; }
        catch (JsonException) { return null; }
    }

    private static string Str(JsonElement? e, string name) =>
        e is { ValueKind: JsonValueKind.Object } o && o.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() ?? "" : "";

    /// <summary>Machine requests; null = not one of them.</summary>
    private async Task<(int, object)?> HandleMachineRequestAsync(PhoneLink.Request req)
    {
        var ui = Avalonia.Threading.Dispatcher.UIThread;
        switch (req.Path)
        {
            case "/api/identify":
                if (req.Body.Length < 1000) return (400, new { ok = false, error = "No photo in the request." });
                _machineHost = req.Peer;
                return await MachineIdentifyAsync(req.Body);
            case "/api/feedback":
                return await ui.InvokeAsync(() => MachineFeedback(BodyJson(req)));
            case "/api/printings":
            {
                var name = Str(BodyJson(req), "name");
                var list = await ui.InvokeAsync(() => Catalog.PrintingsOf(name));
                list.Reverse();                                  // newest first
                return (200, new { ok = true, printings = list.Take(60).Select(CardJson).ToList() });
            }
            case "/api/search":
            {
                var text = Str(BodyJson(req), "text");
                var list = await ui.InvokeAsync(() => Catalog.SearchNames(text));
                return (200, new { ok = true, cards = list.Select(CardJson).ToList() });
            }
            case "/api/setup":
                return (200, await ui.InvokeAsync(() => (object)new { ok = true, bins = _settings.Bins, catalog = _settings.CatalogMode }));
        }
        if (req.Path.StartsWith("/api/card-image/"))
        {
            var id = req.Path["/api/card-image/".Length..];
            var card = await ui.InvokeAsync(() => Catalog.Get(id));
            if (card is null) return (404, new { ok = false, error = "Unknown card." });
            var path = await _thumbs.GetPathAsync(card);
            if (path is null || !File.Exists(path)) return (404, new { ok = false, error = "No picture." });
            return (200, new PhoneLink.RawReply(await File.ReadAllBytesAsync(path), "image/jpeg"));
        }
        return null;
    }

    private async Task<(int, object)> MachineIdentifyAsync(byte[] jpeg)
    {
        var dir = Path.Combine(_paths.PhonePhotosDir, "Machine", DateTime.Now.ToString("yyyy-MM-dd"));
        Directory.CreateDirectory(dir);
        var file = Path.Combine(dir, $"machine_{DateTime.Now:HHmmss_fff}.jpg");
        await File.WriteAllBytesAsync(file, jpeg);
        var ui = Avalonia.Threading.Dispatcher.UIThread;
        return await ui.InvokeAsync(async () =>
        {
            var item = await IdentifyPhonePhotoAsync(file);
            var card = item.ShownCard;
            var r = item.Result;
            bool noCard = card is null || r is null ||
                          (!item.IsPinned && string.IsNullOrWhiteSpace(r.NameRead) && string.IsNullOrWhiteSpace(r.Collector.Raw));
            if (noCard)
            {
                try { File.Delete(file); } catch { }
                return (200, (object)new { ok = false, noCard = true, error = item.Error ?? "No card found in the photo." });
            }
            // the straighten, ★/• and card-detail checks can pin the card or settle its finish: let them finish
            try { await Task.WhenAny(item.LoadThumbnailsAsync(_thumbs), Task.Delay(TimeSpan.FromSeconds(12))); }
            catch (Exception ex) { Log.Error("Machine checks", ex); }
            card = item.ShownCard ?? card;
            var id = $"m{++_machineSeq}";
            _machineItems[id] = (item, file);
            _machineOrder.Enqueue(id);
            while (_machineOrder.Count > 3000) _machineItems.Remove(_machineOrder.Dequeue());
            return (200, (object)new
            {
                ok = true, id, noCard = false, pinned = item.IsPinned, pinReason = item.PinReason, flagReason = item.FlagReason,
                finish = item.SelectedFinish?.Key ?? "nonfoil", finishUnsure = item.FinishUnsure,
                finishes = item.FinishOptions.Select(o => new { key = o.Key, label = o.Label }).ToList(),
                card = CardJson(card!), candidates = item.Candidates.Take(8).Select(c => CardJson(c.Card)).ToList(),
                ms = (int)(r!.Elapsed.TotalMilliseconds),
            });
        });
    }

    private (int, object) MachineFeedback(JsonElement? b)
    {
        var id = Str(b, "id");
        if (!_machineItems.TryGetValue(id, out var e)) return (404, new { ok = false, error = "That scan isn't on this PC any more." });
        var item = e.Item;
        var verdict = Str(b, "verdict");
        var cardId = Str(b, "cardId");
        item.Result!.Folder = Str(b, "session");
        var cand = item.Candidates.FirstOrDefault(c => c.Card.Id == cardId);
        if (verdict == "wrong") item.Choose(null);
        else if (cand is not null) item.Choose(cand);
        else if (item.Top is { } top && Catalog.Get(cardId) is { } picked && picked.Name == top.Card.Name) item.Choose(null, Verdict.NameOnly);
        else item.Choose(null);
        var note = Str(b, "note");
        if (note.Length > 0)
        {
            try
            {
                var log = Path.Combine(_paths.LogsDir, "machine_notes.csv");
                bool fresh = !File.Exists(log);
                using var w = new StreamWriter(log, append: true);
                if (fresh) w.WriteLine("time,session,photo,top_id,top_name,correct_id,verdict,note");
                static string Q(string s) => "\"" + s.Replace("\"", "\"\"") + "\"";
                w.WriteLine(string.Join(",", DateTime.Now.ToString("s", CultureInfo.InvariantCulture), Q(Str(b, "session")), Q(e.File),
                    item.Top?.Card.Id ?? "", Q(item.Top?.Card.Name ?? ""), cardId, verdict, Q(note)));
            }
            catch (Exception ex) { Log.Error("Machine note", ex); }
        }
        return (200, new { ok = true });
    }

    // ---- backup: copy finished machine sessions to this PC ----

    /// <summary>Every minute while the app runs: copy any finished machine session not here yet into
    /// Sessions\Machine\&lt;its folder&gt; (CSVs, photos, session.json). Finds the machine at the address it last
    /// called from, or sorter.local.</summary>
    private async Task MachineBackupLoopAsync()
    {
        await Task.Delay(TimeSpan.FromSeconds(20));
        while (true)
        {
            try { await BackupMachineSessionsAsync(); }
            catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException or IOException) { }
            catch (Exception ex) { Log.Error("Machine backup", ex); }
            await Task.Delay(TimeSpan.FromSeconds(60));
        }
    }

    private async Task BackupMachineSessionsAsync()
    {
        foreach (var host in new[] { _machineHost, "sorter.local" }.Where(h => !string.IsNullOrEmpty(h)).Distinct())
        {
            string list;
            try { list = await MachineHttp.GetStringAsync($"http://{host}:8080/api/sessions"); }
            catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException) { continue; }
            using var doc = JsonDocument.Parse(list);
            var root = Path.Combine(ExportRoot, "Machine");
            foreach (var s in doc.RootElement.GetProperty("sessions").EnumerateArray())
            {
                if (s.GetProperty("state").GetString() != "finished") continue;
                var folder = string.Concat((s.GetProperty("folder").GetString() ?? "").Select(c => Path.GetInvalidFileNameChars().Contains(c) ? '-' : c));
                var sid = s.GetProperty("id").GetString();
                var dest = Path.Combine(root, folder);
                if (folder.Length == 0 || File.Exists(Path.Combine(dest, ".backed-up"))) continue;
                var zip = await MachineHttp.GetByteArrayAsync($"http://{host}:8080/api/sessions/{sid}/bundle.zip");
                Directory.CreateDirectory(dest);
                using (var ms = new MemoryStream(zip))
                using (var z = new ZipArchive(ms))
                    z.ExtractToDirectory(dest, overwriteFiles: true);
                await File.WriteAllTextAsync(Path.Combine(dest, ".backed-up"), DateTime.Now.ToString("s", CultureInfo.InvariantCulture));
            }
            _machineHost = host;
            return;
        }
    }
}
