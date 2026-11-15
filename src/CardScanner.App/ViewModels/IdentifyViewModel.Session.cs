using System.Collections.ObjectModel;
using System.Globalization;
using System.Text;
using System.Text.Json;
using CardScanner.Core;
using CardScanner.Core.Sorting;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace CardScanner.App.ViewModels;

/// <summary>What gets saved for a scan session (Documents\MTG Card Scanner\&lt;date&gt; &lt;name&gt;\session.json).</summary>
public sealed class SessionRecord
{
    public string Id { get; set; } = "";
    public string Name { get; set; } = "";
    public bool Catalog { get; set; } = true;
    public DateTime Started { get; set; }
    public DateTime? Ended { get; set; }
    public BinSetup Bins { get; set; } = new();
    public int Cards { get; set; }
    public int Flagged { get; set; }
    public int NoCardPhotos { get; set; }
    public Dictionary<int, int> BinCounts { get; set; } = [];
    public string? ManaBoxCsv { get; set; }
    public string? MoxfieldCsv { get; set; }
}

/// <summary>One bin's tile in the session panel.</summary>
public sealed partial class BinTile : ObservableObject
{
    public int Bin { get; init; }
    [ObservableProperty] private string _label = "";
    [ObservableProperty] private int _count;
    [ObservableProperty] private bool _isFlaggedBin;
    [ObservableProperty] private bool _isOff;
}

/// <summary>
/// Scan sessions. A session has a name, a mode (Catalog: identify, sort and export a CSV; Sort: bins only) and
/// bin rules. Every card scanned while it runs gets a bin (shown on the card, in the log, and sent to the phone or
/// the machine). The session only ends when you press Stop: then the flagged cards are reviewed and Finish writes
/// the CSVs. The phone app and the machine's Pi join whatever session is running, or start one with the last setup.
/// </summary>
public partial class IdentifyViewModel
{
    // ---- state ----
    [ObservableProperty] [NotifyPropertyChangedFor(nameof(ShowStartSession), nameof(SessionRunning))] private bool _sessionActive;
    [ObservableProperty] [NotifyPropertyChangedFor(nameof(ShowStartSession), nameof(SessionRunning))] private bool _sessionReviewing;
    [ObservableProperty] [NotifyPropertyChangedFor(nameof(PauseLabel))] private bool _sessionPaused;
    [ObservableProperty] private string _sessionTitle = "";
    [ObservableProperty] private string _sessionStats = "";
    [ObservableProperty] private string _flaggedLabel = "";
    [ObservableProperty] private string _reviewBanner = "";
    [ObservableProperty] private string _exportText = "";
    public ObservableCollection<BinTile> BinTiles { get; } = [];
    public bool ShowStartSession => !SessionActive;
    public bool SessionRunning => SessionActive && !SessionReviewing;
    public string PauseLabel => SessionPaused ? "▶ Resume" : "⏸ Pause";

    private SessionRecord? _session;
    private string _sessionDir = "";
    private readonly List<ResultItemViewModel> _sessionItems = [];
    private readonly Dictionary<string, (ResultItemViewModel Item, string File)> _phoneItems = [];
    private bool _stopRequested;
    private string? _lastCardId;

    // ---- start panel ----
    public static readonly string[] SortByList = ["Price", "Alphabet", "Color", "Rarity", "Set"];
    public static readonly int[] BinCountList = [2, 3, 4, 5, 6, 7, 8, 9];
    [ObservableProperty] private bool _setupOpen;
    [ObservableProperty] private string _setupName = "";
    [ObservableProperty] private bool _setupCatalog = true;
    [ObservableProperty] private int _setupBinsInUse = 3;
    [ObservableProperty] private string _setupSortBy = "Price";
    [ObservableProperty] private string _setupPriceBreaks = "1, 5, 10, 25, 50";
    [ObservableProperty] private string _setupAlphaRanges = "A-F, G-K, L-R, S-Z";
    [ObservableProperty] private string _setupSetGroups = "";
    [ObservableProperty] private string _setupPreview = "";
    public bool SetupIsPrice => SetupSortBy == "Price";
    public bool SetupIsAlpha => SetupSortBy == "Alphabet";
    public bool SetupIsSet => SetupSortBy == "Set";

    partial void OnSetupSortByChanged(string value) { OnPropertyChanged(nameof(SetupIsPrice)); OnPropertyChanged(nameof(SetupIsAlpha)); OnPropertyChanged(nameof(SetupIsSet)); UpdatePreview(); }
    partial void OnSetupBinsInUseChanged(int value) => UpdatePreview();
    partial void OnSetupPriceBreaksChanged(string value) => UpdatePreview();
    partial void OnSetupAlphaRangesChanged(string value) => UpdatePreview();
    partial void OnSetupSetGroupsChanged(string value) => UpdatePreview();

    private BinSetup SetupToBins()
    {
        var b = new BinSetup
        {
            BinsInUse = Math.Clamp(SetupBinsInUse, 2, BinSetup.MaxBins),
            By = Enum.TryParse<SortBy>(SetupSortBy, out var by) ? by : SortBy.Price,
        };
        var breaks = SetupPriceBreaks.Split([',', ' ', ';'], StringSplitOptions.RemoveEmptyEntries)
            .Select(t => decimal.TryParse(t.Trim().TrimStart('$'), NumberStyles.Number, CultureInfo.InvariantCulture, out var d) ? d : -1)
            .Where(d => d > 0).Distinct().OrderBy(d => d).ToList();
        if (breaks.Count > 0) b.PriceBreaks = breaks;
        var alpha = SetupAlphaRanges.Split([',', ';'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).ToList();
        if (alpha.Count > 0) b.AlphaRanges = alpha;
        b.SetGroups = SetupSetGroups.Split(['\n', '\r', '|'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).ToList();
        return b;
    }

    private void BinsToSetup(BinSetup b)
    {
        SetupBinsInUse = b.BinsInUse;
        SetupSortBy = b.By.ToString();
        SetupPriceBreaks = string.Join(", ", b.PriceBreaks.Select(d => d.ToString("0.##", CultureInfo.InvariantCulture)));
        SetupAlphaRanges = string.Join(", ", b.AlphaRanges);
        SetupSetGroups = string.Join("\n", b.SetGroups);
    }

    private void UpdatePreview()
    {
        var labels = BinSorter.BinLabels(SetupToBins());
        SetupPreview = string.Join("\n", labels.Select((l, i) => $"Bin {i + 1}: {l}"));
    }

    [RelayCommand]
    private void OpenSessionSetup()
    {
        SetupName = $"Scan {DateTime.Now:MMM d, h:mm tt}";
        SetupCatalog = _settings.CatalogMode;
        BinsToSetup(_settings.Bins);
        UpdatePreview();
        SetupOpen = true;
    }

    [RelayCommand]
    private void CancelSessionSetup() => SetupOpen = false;

    [RelayCommand]
    private void StartSessionFromSetup()
    {
        var bins = SetupToBins();
        _settings.Bins = bins.Clone();
        _settings.CatalogMode = SetupCatalog;
        _settings.Save();
        SetupOpen = false;
        BeginSession(string.IsNullOrWhiteSpace(SetupName) ? $"Scan {DateTime.Now:MMM d, h:mm tt}" : SetupName.Trim(), SetupCatalog, bins);
    }

    /// <summary>Starts a session (from the start panel, or from the phone / machine with the last setup).</summary>
    private void BeginSession(string name, bool catalog, BinSetup bins)
    {
        _session = new SessionRecord
        {
            Id = DateTime.Now.ToString("yyyyMMdd_HHmmss"), Name = name, Catalog = catalog, Started = DateTime.Now, Bins = bins.Clone(),
        };
        var safe = string.Concat(name.Select(c => Path.GetInvalidFileNameChars().Contains(c) ? '-' : c)).Trim();
        _sessionDir = Path.Combine(ExportRoot, $"{DateTime.Now:yyyy-MM-dd HHmm} {safe}");
        try { Directory.CreateDirectory(_sessionDir); } catch (Exception ex) { Log.Error("Session folder", ex); }
        _sessionItems.Clear();
        _phoneItems.Clear();
        _stopRequested = false;
        _lastCardId = null;
        BinTiles.Clear();
        var labels = BinSorter.BinLabels(bins);
        for (int b = 1; b <= BinSetup.MaxBins; b++)
            BinTiles.Add(new BinTile { Bin = b, Label = labels[b - 1], IsFlaggedBin = b == bins.FlaggedBin, IsOff = b > bins.BinsInUse });
        SessionPaused = false;
        SessionReviewing = false;
        SessionActive = true;
        ExportText = "";
        SaveSession();
        UpdateSessionText();
    }

    private static string ExportRoot => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "MTG Card Scanner");

    /// <summary>Every card scanned during the session: give it a bin and count it.</summary>
    private void AddToSession(ResultItemViewModel item)
    {
        if (_session is null) return;
        var choice = ChooseBin(item);
        item.Bin = choice;
        item.SessionId = _session.Id;
        item.BinText = choice.WantedBin == 0 ? $"→ Bin {choice.Bin} · Flagged ({choice.Reason})"
                     : choice.Rerouted ? $"→ Bin {choice.Bin} · {choice.Label} ({choice.Reason})"
                     : $"→ Bin {choice.Bin} · {choice.Label}";
        if (item.Result is { } r) r.Folder = _session.Name;
        _sessionItems.Add(item);
        _session.Cards = _sessionItems.Count;
        Recount();
    }

    private BinChoice ChooseBin(ResultItemViewModel item)
    {
        var bins = _session!.Bins;
        var card = item.ShownCard;
        if (card is null || !item.HasResult) return new BinChoice(bins.FlaggedBin, "Flagged", 0, "no card read");
        bool listNoPrice = card.IsListReprint && item.Price is null;
        bool flagged = !item.IsPinned || (_session.Catalog && item.FinishUnsure) || listNoPrice;
        string? why = !item.IsPinned ? "not sure of the printing" : listNoPrice ? "List card with no price" : flagged ? "foil or not?" : null;
        return BinSorter.Choose(bins, new CardFacts(card.Name, item.Price, card.Colors, card.TypeLine, card.Rarity,
                                                    card.SetCode, card.CollectorNumber, flagged, why));
    }

    private void Recount()
    {
        if (_session is null) return;
        var counts = _sessionItems.Where(i => i.Bin is not null).GroupBy(i => i.Bin!.Bin).ToDictionary(g => g.Key, g => g.Count());
        _session.BinCounts = counts;
        _session.Flagged = _sessionItems.Count(i => i.Bin?.WantedBin == 0);
        foreach (var t in BinTiles) t.Count = counts.GetValueOrDefault(t.Bin);
        UpdateSessionText();
        SaveSession();
    }

    private void UpdateSessionText()
    {
        if (_session is null) return;
        var mins = Math.Max(0.5, (DateTime.Now - _session.Started).TotalMinutes);
        int n = _sessionItems.Count;
        int open = _sessionItems.Count(i => i.Bin?.WantedBin == 0 && i.Verdict == Verdict.None);
        SessionTitle = $"{(_session.Catalog ? "📋 Catalog" : "🗂 Sort")} · {_session.Name}" + (SessionPaused ? " · paused" : "") +
                       (SessionReviewing ? " · stopped" : "");
        SessionStats = $"{n} card{(n == 1 ? "" : "s")} · {n / mins:0.0} per minute" +
                       (_session.NoCardPhotos > 0 ? $" · {_session.NoCardPhotos} photo{(_session.NoCardPhotos == 1 ? "" : "s")} with no card skipped" : "");
        FlaggedLabel = $"⚑ Review flagged ({open})";
        ReviewBanner = open == 0 ? "All flagged cards are reviewed. Finish to save the session" + (_session.Catalog ? " and write the CSVs." : ".")
                                 : $"{open} flagged card{(open == 1 ? "" : "s")} to review. Mark each one, then Finish" + (_session.Catalog ? " to write the CSVs." : ".");
    }

    private void SaveSession()
    {
        if (_session is null || _sessionDir.Length == 0) return;
        try
        {
            File.WriteAllText(Path.Combine(_sessionDir, "session.json"),
                JsonSerializer.Serialize(_session, new JsonSerializerOptions { WriteIndented = true }));
        }
        catch (Exception ex) { Log.Error("Save session", ex); }
    }

    [RelayCommand]
    private void TogglePause() { SessionPaused = !SessionPaused; UpdateSessionText(); }

    [RelayCommand]
    private void ReviewFlagged() { Filter = ReviewFilter.Queue; }

    /// <summary>Stop: no more cards are taken (the phone / machine stop too); review the flagged ones, then Finish.</summary>
    [RelayCommand]
    private void StopSession()
    {
        if (_session is null) return;
        _stopRequested = true;
        SessionReviewing = true;
        SessionPaused = false;
        Filter = ReviewFilter.Queue;
        UpdateSessionText();
    }

    [RelayCommand]
    private void FinishSession()
    {
        if (_session is null) return;
        _session.Ended = DateTime.Now;
        if (_session.Catalog) WriteExports(_sessionItems, _sessionDir, _session);
        else ExportText = $"Sort session saved: {_sessionItems.Count} cards.";
        SaveSession();
        try { System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo("explorer.exe", $"\"{_sessionDir}\"") { UseShellExecute = true }); }
        catch (Exception ex) { Log.Error("Open session folder", ex); }
        SessionActive = false;
        SessionReviewing = false;
        _session = null;
        _stopRequested = false;
    }

    [RelayCommand]
    private void OpenSessionsFolder()
    {
        try
        {
            Directory.CreateDirectory(ExportRoot);
            System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo("explorer.exe", $"\"{ExportRoot}\"") { UseShellExecute = true });
        }
        catch (Exception ex) { Log.Error("Open sessions folder", ex); }
    }

    /// <summary>Outside a session: every identified card on the list, to Documents\MTG Card Scanner.</summary>
    [RelayCommand]
    private void ExportCsv()
    {
        var dir = Path.Combine(ExportRoot, $"{DateTime.Now:yyyy-MM-dd HHmm} export");
        WriteExports(Results.ToList(), dir, null);
        try { System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo("explorer.exe", $"\"{dir}\"") { UseShellExecute = true }); }
        catch (Exception ex) { Log.Error("Open export folder", ex); }
    }

    /// <summary>ManaBox CSV (exact printing by Scryfall ID) and a Moxfield copy. Cards marked "not listed" or
    /// "only the name is right" are left out; flagged cards nobody reviewed go in with their best guess and are
    /// tagged "needs-check" in the Moxfield file.</summary>
    private void WriteExports(List<ResultItemViewModel> items, string dir, SessionRecord? s)
    {
        var rows = items.Where(r => r.HasResult && r.ShownCard is not null && r.Verdict is not (Verdict.NotListed or Verdict.NameOnly))
            .GroupBy(r => (r.ShownCard!.Id, Finish: r.SelectedFinish?.Key ?? "nonfoil", r.Condition,
                           Unchecked: r.Verdict == Verdict.None && r.Bin?.WantedBin == 0))
            .Select(g => (Card: g.First().ShownCard!, g.Key.Finish, g.Key.Condition, g.Key.Unchecked, Qty: g.Count()))
            .OrderBy(r => r.Card.Name).ToList();
        if (rows.Count == 0) { ExportText = "Nothing to export yet."; return; }
        try { Directory.CreateDirectory(dir); } catch { }
        static string Q(string? v) => "\"" + (v ?? "").Replace("\"", "\"\"") + "\"";
        static string ManaCond(string c) => c switch
        {
            "Lightly Played" => "lightly_played", "Moderately Played" => "moderately_played",
            "Heavily Played" => "heavily_played", "Damaged" => "damaged", _ => "near_mint",
        };
        var mb = new StringBuilder("Name,Set code,Collector number,Foil,Rarity,Quantity,Condition,Language,Scryfall ID\n");
        var mx = new StringBuilder("\"Count\",\"Name\",\"Edition\",\"Condition\",\"Language\",\"Foil\",\"Collector Number\",\"Tags\"\n");
        foreach (var (card, fin, cond, unchecked_, qty) in rows)
        {
            mb.Append($"{Q(card.Name)},{card.SetCode.ToUpperInvariant()},{Q(card.CollectorNumber)},{(fin == "nonfoil" ? "normal" : fin)},{card.Rarity},{qty},{ManaCond(cond)},English,{card.Id}\n");
            string mxFoil = fin switch { "foil" => "foil", "etched" => "etched", _ => "" };
            mx.Append($"\"{qty}\",{Q(card.Name)},\"{card.SetCode.ToLowerInvariant()}\",{Q(string.IsNullOrEmpty(cond) ? "Near Mint" : cond)},\"English\",\"{mxFoil}\",{Q(card.CollectorNumber)},\"{(unchecked_ ? "needs-check" : "")}\"\n");
        }
        string baseName = s is null ? "cards" : string.Concat(s.Name.Select(c => Path.GetInvalidFileNameChars().Contains(c) ? '-' : c));
        var pMb = Path.Combine(dir, $"{baseName} - ManaBox.csv");
        var pMx = Path.Combine(dir, $"{baseName} - Moxfield.csv");
        try
        {
            File.WriteAllText(pMb, mb.ToString(), new UTF8Encoding(false));
            File.WriteAllText(pMx, mx.ToString(), new UTF8Encoding(false));
            if (s is not null) { s.ManaBoxCsv = pMb; s.MoxfieldCsv = pMx; }
            int unchecked2 = rows.Where(r => r.Unchecked).Sum(r => r.Qty);
            ExportText = $"Saved {rows.Sum(r => r.Qty)} cards (ManaBox + Moxfield) to {dir}" +
                         (unchecked2 > 0 ? $" · {unchecked2} unreviewed flagged card{(unchecked2 == 1 ? "" : "s")} included as best guesses" : "");
        }
        catch (Exception ex) { Log.Error("Write export", ex); ExportText = $"Couldn't save the CSVs: {ex.Message}"; }
    }

    // ---- phone link / machine ----

    private object Status() => new
    {
        ok = true,
        active = SessionActive && !SessionReviewing,
        paused = SessionPaused,
        stop = _stopRequested,
        session = _session?.Name ?? "",
        mode = _session is null ? "" : _session.Catalog ? "Catalog" : "Sort",
        count = _sessionItems.Count,
        bins = _session is null ? new List<string>() : BinSorter.BinLabels(_session.Bins),
        binsInUse = _session?.Bins.BinsInUse ?? 0,
    };

    /// <summary>Requests from the phone or the machine. Runs off the UI thread; anything touching the page runs on it.</summary>
    private async Task<(int, object)> HandlePhoneRequestAsync(PhoneLink.Request req)
    {
        var ui = Avalonia.Threading.Dispatcher.UIThread;
        switch (req.Path)
        {
            case "/api/session/start":
                await ui.InvokeAsync(() =>
                {
                    // join a running session; otherwise start one with the last setup
                    if (!SessionActive || SessionReviewing)
                    {
                        if (SessionReviewing) FinishSession();
                        BeginSession($"Phone scan {DateTime.Now:MMM d, h:mm tt}", _settings.CatalogMode, _settings.Bins);
                    }
                    SessionPaused = false;
                    UpdateSessionText();
                });
                return (200, await ui.InvokeAsync(Status));
            case "/api/session/resume":
                await ui.InvokeAsync(() =>
                {
                    if (!SessionActive) BeginSession($"Phone scan {DateTime.Now:MMM d, h:mm tt}", _settings.CatalogMode, _settings.Bins);
                    SessionPaused = false;
                    UpdateSessionText();
                });
                return (200, await ui.InvokeAsync(Status));
            case "/api/session/stop":
                await ui.InvokeAsync(() => { if (SessionActive && !SessionReviewing) StopSession(); });
                return (200, new { ok = true });
            case "/api/status":
                return (200, await ui.InvokeAsync(Status));
            case "/api/undo":
                return await ui.InvokeAsync(() => UndoScan(Encoding.UTF8.GetString(req.Body).Trim()));
            case "/api/scan":
                break;
            default:
                return (404, new { ok = false, error = "Unknown request." });
        }

        // A scan. Stopped or paused on the PC: tell the sender, keep nothing.
        var (stop, paused, active) = await ui.InvokeAsync(() => (_stopRequested || SessionReviewing, SessionPaused, SessionActive));
        if (stop && active) return (409, new { ok = false, stop = true, error = "Scanning was stopped on the PC." });
        if (paused) return (409, new { ok = false, paused = true, error = "Paused on the PC." });
        if (!active) await ui.InvokeAsync(() => BeginSession($"Phone scan {DateTime.Now:MMM d, h:mm tt}", _settings.CatalogMode, _settings.Bins));

        var dir = Path.Combine(_paths.Root, "phone_scans", DateTime.Now.ToString("yyyy-MM-dd"));
        Directory.CreateDirectory(dir);
        var file = Path.Combine(dir, $"phone_{DateTime.Now:HHmmss_fff}.jpg");
        await File.WriteAllBytesAsync(file, req.Body);

        return await ui.InvokeAsync(async () =>
        {
            var item = await IdentifyPhonePhotoAsync(file);
            var card = item.ShownCard;
            var r = item.Result;
            // No card: nothing read and nothing pinned. Don't fill the review list with photos of the desk.
            bool noCard = card is null || r is null ||
                          (!item.IsPinned && string.IsNullOrWhiteSpace(r.NameRead) && string.IsNullOrWhiteSpace(r.Collector.Raw));
            if (noCard)
            {
                if (_session is not null) { _session.NoCardPhotos++; UpdateSessionText(); }
                try { File.Delete(file); } catch { }
                var fb = _session?.Bins.FlaggedBin ?? 0;
                return (200, (object)new { ok = false, noCard = true, error = "No card found in the photo.", bin = fb, binLabel = "No card", paused = SessionPaused, stop = _stopRequested });
            }
            Insert(item);
            bool repeat = card!.Id == _lastCardId;
            _lastCardId = card.Id;
            _phoneItems[item.ScanLabel] = (item, file);
            var b = item.Bin;
            return (200, (object)new
            {
                ok = true,
                scan = item.ScanLabel,
                name = card.Name,
                set = card.SetName,
                setCode = card.SetCode.ToUpperInvariant(),
                number = card.CollectorNumber,
                finish = item.SelectedFinish?.Label,
                finishUnsure = item.FinishUnsure,
                pinned = item.IsPinned,
                pinReason = item.PinReason,
                price = item.Price,
                rarity = card.RarityLabel,
                sameAsLast = repeat,
                count = _sessionItems.Count,
                session = _session?.Name,
                bin = b?.Bin ?? 0,
                binLabel = b is null ? "" : b.WantedBin == 0 ? "Flagged" : b.Label,
                binWanted = b?.WantedBin ?? 0,
                binReason = b?.Reason,
                flagged = b?.WantedBin == 0,
                paused = SessionPaused,
                stop = _stopRequested,
            });
        });
    }

    /// <summary>The phone's Undo: take a scan back off the list (only if you haven't reviewed it yet).</summary>
    private (int, object) UndoScan(string scan)
    {
        if (!_phoneItems.TryGetValue(scan, out var e)) return (404, new { ok = false, error = "That scan isn't on the PC list." });
        if (e.Item.Verdict != Verdict.None) return (409, new { ok = false, error = "Already reviewed on the PC; change it there." });
        Results.Remove(e.Item);
        _sessionItems.Remove(e.Item);
        _phoneItems.Remove(scan);
        _lastCardId = null;
        try { File.Delete(e.File); } catch { }
        if (_session is not null) _session.Cards = _sessionItems.Count;
        Recount();
        return (200, new { ok = true, scan });
    }
}
