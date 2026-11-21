using System.Collections.ObjectModel;
using System.Globalization;
using System.Text;
using System.Text.Json;
using CardScanner.Core;
using CardScanner.Core.Sorting;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace CardScanner.App.ViewModels;

/// <summary>What gets saved for a scan session (data folder\Sessions\&lt;date&gt; &lt;name&gt;\session.json).</summary>
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
    public List<string> Exports { get; set; } = [];
    /// <summary>Set lock: only these sets were considered (empty = the whole catalog).</summary>
    public List<string> SetLock { get; set; } = [];
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
    [ObservableProperty] private bool _setupOpen;
    [ObservableProperty] private string _setupName = "";
    [ObservableProperty] private bool _setupCatalog = true;
    /// <summary>Optional set lock for the session: "HOB, HOC".</summary>
    [ObservableProperty] private string _setupSetLock = "";
    [ObservableProperty] private string _setupSetLockInfo = "";
    partial void OnSetupSetLockChanged(string value)
    {
        if (_recognizer is null) { SetupSetLockInfo = ""; return; }   // (page tests run without a catalog)
        var (known, unknown) = _recognizer.CheckSets(SplitSets(value));
        SetupSetLockInfo = known.Count == 0 && unknown.Count == 0 ? "Off: every set is considered."
            : string.Join(" · ", known.Select(k => $"{k.ToUpperInvariant()} ({_recognizer.PrintingsInSet(k)} printings)"))
              + (unknown.Count > 0 ? $"  ⚠ not a set code: {string.Join(", ", unknown.Select(u => u.ToUpperInvariant()))}" : "");
    }
    private static IEnumerable<string> SplitSets(string text) =>
        text.Split([',', ' ', ';', '/', '\n'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
    /// <summary>The bins, as a clickable picture of the machine (Start panel and Settings).</summary>
    public BinEditorViewModel BinEditor { get; } = new();

    private BinSetup SetupToBins() => BinEditor.ToSetup();
    private void BinsToSetup(BinSetup b) => BinEditor.Load(b);

    [RelayCommand]
    private void OpenSessionSetup()
    {
        SetupName = $"Scan {DateTime.Now:MMM d, h:mm tt}";
        SetupSetLock = "";
        OnSetupSetLockChanged("");
        SetupCatalog = _settings.CatalogMode;
        BinsToSetup(_settings.Bins);
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
        var lockSets = _recognizer is null ? [] : _recognizer.CheckSets(SplitSets(SetupSetLock)).Known;
        BeginSession(string.IsNullOrWhiteSpace(SetupName) ? $"Scan {DateTime.Now:MMM d, h:mm tt}" : SetupName.Trim(), SetupCatalog, bins, lockSets);
    }

    /// <summary>Starts a session (from the start panel, or from the phone / machine with the last setup).</summary>
    private void BeginSession(string name, bool catalog, BinSetup bins, List<string>? setLock = null)
    {
        if (_recognizer is not null) _recognizer.SetLock = setLock is { Count: > 0 } ? new HashSet<string>(setLock) : null;
        _session = new SessionRecord
        {
            Id = DateTime.Now.ToString("yyyyMMdd_HHmmss"), Name = name, Catalog = catalog, Started = DateTime.Now, Bins = bins.Clone(),
            SetLock = setLock ?? [],
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

    // ---- used by the Home and Settings pages ----
    internal UiSettings Settings => _settings;
    internal CardScanner.Core.Catalog.CardCatalog Catalog => _recognizer.Catalog;
    internal ThumbnailCache Thumbs => _thumbs;
    internal AppPaths AppPaths => _paths;
    /// <summary>Set by the main window: the ⚙ button on this page opens the Settings page.</summary>
    public Action? RequestSettings { get; set; }
    [RelayCommand] private void OpenSettings() => RequestSettings?.Invoke();

    /// <summary>Fills the bin-setup fields from the saved default (Settings page).</summary>
    internal void LoadSetupDefaults()
    {
        SetupCatalog = _settings.CatalogMode;
        BinsToSetup(_settings.Bins);
    }

    /// <summary>Saves the bin-setup fields as the default for new sessions (and for the phone / machine).</summary>
    internal void SaveSetupDefaults()
    {
        _settings.Bins = SetupToBins();
        _settings.CatalogMode = SetupCatalog;
        _settings.Save();
    }

    internal static string ExportFolder => ExportRoot;

    private static string ExportRoot => Log.Paths.SessionsDir;

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
        SessionTitle = $"{(_session.Catalog ? "📋 Catalog" : "🗂 Sort")} · {_session.Name}" +
            (_session.SetLock.Count > 0 ? $" · 🔒 {string.Join(", ", _session.SetLock.Select(x => x.ToUpperInvariant()))}" : "") + (SessionPaused ? " · paused" : "") +
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
        if (_recognizer is not null) _recognizer.SetLock = null;
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

    /// <summary>Outside a session: every identified card on the list, to data folder\Exports.</summary>

    /// <summary>Writes the chosen export formats (see <see cref="CsvExport"/>). Cards marked "not listed" or "only the
    /// name is right" are left out; flagged cards nobody reviewed go in with their best guess.</summary>
    private void WriteExports(List<ResultItemViewModel> items, string dir, SessionRecord? s, IEnumerable<string>? formats = null)
    {
        var chosen = (formats ?? _settings.ExportFormats).ToList();
        if (chosen.Count == 0) chosen = ["ManaBox"];
        string baseName = s is null ? "cards" : string.Concat(s.Name.Select(c => Path.GetInvalidFileNameChars().Contains(c) ? '-' : c));
        try
        {
            var (files, cards, unreviewed) = CsvExport.Write(items, dir, baseName, chosen);
            if (files.Count == 0) { ExportText = "Nothing to export yet."; return; }
            if (s is not null)
            {
                s.Exports = files;
                s.ManaBoxCsv = files.FirstOrDefault(f => f.EndsWith("ManaBox.csv"));
                s.MoxfieldCsv = files.FirstOrDefault(f => f.EndsWith("Moxfield.csv"));
            }
            var names = CsvExport.Formats.Where(f => chosen.Contains(f.Key)).Select(f => f.Title);
            ExportText = $"Saved {cards} cards ({string.Join(", ", names)}) to {dir}" +
                         (unreviewed > 0 ? $" · {unreviewed} unreviewed flagged card{(unreviewed == 1 ? "" : "s")} included as best guesses" : "");
        }
        catch (Exception ex) { Log.Error("Write export", ex); ExportText = $"Couldn't save the files: {ex.Message}"; }
    }

    // ---- Export window ----
    public partial class ExportChoice(CsvExport.Format format, bool on) : ObservableObject
    {
        public CsvExport.Format Format { get; } = format;
        [ObservableProperty] private bool _isOn = on;
    }
    public ObservableCollection<ExportChoice> ExportChoices { get; } = [];
    [ObservableProperty] private bool _exportOpen;
    [ObservableProperty] private string _exportScopeText = "";

    private List<ResultItemViewModel> ExportItems() => SessionActive ? [.. _sessionItems] : [.. Results];

    [RelayCommand]
    private void ExportCsv()
    {
        ExportChoices.Clear();
        foreach (var f in CsvExport.Formats) ExportChoices.Add(new ExportChoice(f, _settings.ExportFormats.Contains(f.Key)));
        int n = ExportItems().Count(r => r.HasResult);
        ExportScopeText = SessionActive ? $"The {n} cards in this session ({SessionTitle})." : $"The {n} identified cards on the list.";
        ExportOpen = true;
    }

    [RelayCommand] private void CancelExport() => ExportOpen = false;

    [RelayCommand]
    private void DoExport()
    {
        var chosen = ExportChoices.Where(c => c.IsOn).Select(c => c.Format.Key).ToList();
        if (chosen.Count == 0) { ExportScopeText = "Pick at least one format."; return; }
        _settings.ExportFormats = chosen;
        _settings.Save();
        ExportOpen = false;
        var dir = SessionActive && _sessionDir.Length > 0 ? _sessionDir : Path.Combine(_paths.ExportsDir, $"{DateTime.Now:yyyy-MM-dd HHmm} export");
        WriteExports(ExportItems(), dir, SessionActive ? _session : null, chosen);
        try { System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo("explorer.exe", $"\"{dir}\"") { UseShellExecute = true }); }
        catch (Exception ex) { Log.Error("Open export folder", ex); }
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
        if (await HandleMachineRequestAsync(req) is { } machineReply) return machineReply;
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

        var dir = Path.Combine(_paths.PhonePhotosDir, DateTime.Now.ToString("yyyy-MM-dd"));
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
            // Let the straighten, ★/• and card-detail checks finish first: they can pin the card or settle its
            // finish, which changes its bin (they took ~1 s and used to land after the bin was already chosen).
            try { await Task.WhenAny(item.LoadThumbnailsAsync(_thumbs), Task.Delay(TimeSpan.FromSeconds(12))); }
            catch (Exception ex) { Log.Error("Checks before bin", ex); }
            card = item.ShownCard ?? card;
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
