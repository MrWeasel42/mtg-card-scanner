using System.Collections.ObjectModel;
using System.Globalization;
using Avalonia.Media.Imaging;
using CardScanner.Core;
using CardScanner.Core.Recognition;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace CardScanner.App.ViewModels;

public enum ReviewFilter { Queue, Good, Finish, Done, All }

/// <summary>
/// "Identify photos" page: drop in photos, see the top matches, mark each one right or wrong.
/// Every verdict is written to logs/identify_log.csv so accuracy can be measured on real cards.
/// </summary>
public partial class IdentifyViewModel : ObservableObject
{
    public static readonly string[] ImageExtensions = [".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"];

    private readonly Recognizer _recognizer;
    private readonly AppPaths _paths;
    private readonly ThumbnailCache _thumbs;
    private readonly SemaphoreSlim _gate = new(1, 1);
    private readonly string _logPath;
    private int _scanCount;
    private readonly UiSettings _settings;

    public ObservableCollection<ResultItemViewModel> Results { get; } = [];

    [ObservableProperty] private bool _isBusy;
    [ObservableProperty] private string _busyText = "";
    [ObservableProperty] private string _scoreText = "Drop some card photos in to get started.";

    public IdentifyViewModel(Recognizer recognizer, AppPaths paths)
    {
        _recognizer = recognizer;
        _paths = paths;
        _thumbs = new ThumbnailCache(paths);
        _logPath = Path.Combine(paths.LogsDir, "identify_results_v6.csv");
        _settings = UiSettings.Load(paths);
        PhoneLink.Instance.StatusChanged += t => Avalonia.Threading.Dispatcher.UIThread.Post(() => PhoneLinkStatus = t);
        PhoneLinkStatus = PhoneLink.Instance.Status;
        PhoneLink.Instance.Handler = HandlePhoneScanAsync;
        if (_settings.PhoneLink) PhoneLink.Instance.Start();
        Results.CollectionChanged += (_, _) => { OnPropertyChanged(nameof(HasResults)); ApplyFilter(); };
    }

    public bool HasResults => Results.Count > 0;

    // ---- Review queue: unsure cards show up, and drop off once verified ----

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(IsQueue), nameof(IsGood), nameof(IsFinish), nameof(IsDone), nameof(IsAll))]
    private ReviewFilter _filter = ReviewFilter.Queue;

    public bool IsQueue => Filter == ReviewFilter.Queue;
    public bool IsGood => Filter == ReviewFilter.Good;
    public bool IsFinish => Filter == ReviewFilter.Finish;
    public bool IsDone => Filter == ReviewFilter.Done;
    public bool IsAll => Filter == ReviewFilter.All;

    [ObservableProperty] private string _queueLabel = "To verify";
    [ObservableProperty] private string _goodLabel = "📌 Pinned";
    [ObservableProperty] private string _doneLabel = "✓ Done";
    [ObservableProperty] private string _finishLabel = "✨ Check finish";
    [ObservableProperty] private string _allLabel = "All";
    [ObservableProperty] private string _emptyFilterText = "";
    [ObservableProperty] private bool _canAcceptGood;

    partial void OnFilterChanged(ReviewFilter value) => ApplyFilter();

    /// <summary>Search box above the list: filters whichever tab is open.</summary>
    [ObservableProperty] private string _searchText = "";
    partial void OnSearchTextChanged(string value) => ApplyFilter();

    // ---- Filter menu (funnel button next to the search box): rarity, price, sort ----
    public IReadOnlyList<string> RarityOptions => RarityList;
    private static readonly IReadOnlyList<string> RarityList = ["All rarities", "Mythic", "Rare", "Uncommon", "Common", "Special / timeshifted"];
    public IReadOnlyList<string> PriceOptions => PriceList;
    private static readonly IReadOnlyList<string> PriceList = ["Any price", "Under $1", "$1 – $5", "$5 – $20", "$20 – $100", "$100 and up", "No price"];
    public IReadOnlyList<string> SortOptions => SortList;
    private static readonly IReadOnlyList<string> SortList =
        ["Newest first", "Scan order (0001 first)", "Name A–Z", "Price: high to low", "Price: low to high", "Rarity (mythic first)", "Set"];

    [ObservableProperty] private string _rarityFilter = "All rarities";
    [ObservableProperty] private string _priceFilter = "Any price";
    [ObservableProperty] private string _sortOrder = "Newest first";
    partial void OnRarityFilterChanged(string value) => FiltersChanged();
    partial void OnPriceFilterChanged(string value) => FiltersChanged();
    partial void OnSortOrderChanged(string value) => FiltersChanged();
    private void FiltersChanged() { OnPropertyChanged(nameof(FilterLabel)); ApplyFilter(); }

    /// <summary>Button text: shows how many filters are on.</summary>
    public string FilterLabel
    {
        get
        {
            int n = (RarityFilter != RarityList[0] ? 1 : 0) + (PriceFilter != PriceList[0] ? 1 : 0) + (SortOrder != SortList[0] ? 1 : 0);
            return n == 0 ? "Filter" : $"Filter ({n})";
        }
    }

    [RelayCommand]
    private void ResetFilters()
    {
        RarityFilter = RarityList[0]; PriceFilter = PriceList[0]; SortOrder = SortList[0]; SearchText = "";
    }

    private bool MatchesRarity(ResultItemViewModel r) => RarityFilter switch
    {
        "All rarities" => true,
        "Special / timeshifted" => r.ShownCard?.Rarity is "special" or "bonus",
        var f => string.Equals(r.ShownCard?.Rarity, f, StringComparison.OrdinalIgnoreCase),
    };

    private bool MatchesPrice(ResultItemViewModel r) => (PriceFilter, r.Price) switch
    {
        ("Any price", _) => true,
        ("No price", var p) => p is null,
        (_, null) => false,
        ("Under $1", var p) => p < 1,
        ("$1 – $5", var p) => p >= 1 && p < 5,
        ("$5 – $20", var p) => p >= 5 && p < 20,
        ("$20 – $100", var p) => p >= 20 && p < 100,
        (_, var p) => p >= 100,
    };

    private IEnumerable<ResultItemViewModel> Sorted(IEnumerable<ResultItemViewModel> items) => SortOrder switch
    {
        "Scan order (0001 first)" => items.OrderBy(r => r.ScanNumber),
        "Name A–Z" => items.OrderBy(r => r.ShownCard?.Name ?? "~").ThenBy(r => r.ScanNumber),
        "Price: high to low" => items.OrderByDescending(r => r.Price ?? -1),
        "Price: low to high" => items.OrderBy(r => r.Price ?? decimal.MaxValue),
        "Rarity (mythic first)" => items.OrderBy(r => RarityStyle.Order(r.ShownCard?.Rarity ?? "")).ThenBy(r => r.ShownCard?.Name),
        "Set" => items.OrderBy(r => r.ShownCard?.SetName ?? "~").ThenBy(r => r.ShownCard?.CollectorNumber.PadLeft(5, '0')),
        // Newest first: in Done, the card you marked most recently; elsewhere the newest scan.
        _ when Filter == ReviewFilter.Done => items.OrderByDescending(r => r.VerifiedAt ?? DateTime.MinValue),
        // Pinned tab: the "worth a glance" pins (no printed set code behind them) come first.
        _ when Filter == ReviewFilter.Good => items.OrderByDescending(r => r.IsSoftPin).ThenByDescending(r => r.ScanNumber),
        _ => items.OrderByDescending(r => r.ScanNumber),
    };

    /// <summary>What the list shows: the open tab, matching the search. Done lists the most recently
    /// marked card first so a mis-click is easy to find; the other tabs list newest scans first.</summary>
    public ObservableCollection<ResultItemViewModel> Shown { get; } = [];

    [RelayCommand]
    private void SetFilter(string name) => Filter = Enum.Parse<ReviewFilter>(name);

    private static bool Matches(ResultItemViewModel r, ReviewFilter f) => f switch
    {
        // Anything the scanner couldn't pin down (flagged, unpinned, or failed), not yet marked.
        ReviewFilter.Queue => r.Verdict == Verdict.None && !r.IsPinned,
        ReviewFilter.Good => r.Verdict == Verdict.None && r.IsPinned && !r.FinishUnsure,
        // Printing pinned, but foil / non-foil couldn't be read: just check the finish.
        ReviewFilter.Finish => r.Verdict == Verdict.None && r.IsPinned && r.FinishUnsure,
        ReviewFilter.Done => r.Verdict != Verdict.None,
        _ => true,
    };

    private bool _bulk;   // "Mark all pinned correct": filter once at the end, not once per card

    internal void ApplyFilter()
    {
        if (_bulk) return;
        foreach (var r in Results) r.IsShown = Matches(r, Filter) && r.MatchesSearch(SearchText) && MatchesRarity(r) && MatchesPrice(r);
        var list = Sorted(Results.Where(r => r.IsShown)).ToList();
        SyncShown(list);
        int Count(ReviewFilter f) => Results.Count(r => Matches(r, f));
        int q = Count(ReviewFilter.Queue);
        QueueLabel = $"To verify ({q})";
        GoodLabel = $"📌 Pinned ({Count(ReviewFilter.Good)})";
        DoneLabel = $"✓ Done ({Count(ReviewFilter.Done)})";
        FinishLabel = $"✨ Check finish ({Count(ReviewFilter.Finish)})";
        AllLabel = $"All ({Results.Count})";
        CanAcceptGood = Count(ReviewFilter.Good) > 0;
        EmptyFilterText = !HasResults ? "" : Count(Filter) > 0 ? (Shown.Count == 0 ? "Nothing in this tab matches the search / filters." : "") : Filter switch
        {
            ReviewFilter.Queue => "Queue's clear, nothing left to verify. 🎉 Peek at the Pinned tab if you want to double-check those.",
            ReviewFilter.Good => "No unmarked pinned cards left.",
            ReviewFilter.Done => "Nothing marked yet.",
            ReviewFilter.Finish => "No finishes left to check.",
            _ => "",
        };
    }

    /// <summary>Update the visible list in place (remove / move / insert) instead of rebuilding it, so
    /// marking a card doesn't redraw hundreds of cards (that made "This is the one" feel sluggish).</summary>
    private void SyncShown(List<ResultItemViewModel> list)
    {
        if (list.SequenceEqual(Shown)) return;
        var keep = list.ToHashSet();
        for (int i = Shown.Count - 1; i >= 0; i--)
            if (!keep.Contains(Shown[i])) Shown.RemoveAt(i);
        for (int i = 0; i < list.Count; i++)
        {
            if (i < Shown.Count && Shown[i] == list[i]) continue;
            int at = Shown.IndexOf(list[i]);
            if (at >= 0) Shown.Move(at, i);
            else Shown.Insert(i, list[i]);
        }
    }

    /// <summary>Marks every pinned card that isn't marked yet as correct, in one go.</summary>
    [RelayCommand]
    private void AcceptGood()
    {
        _bulk = true;
        try
        {
            foreach (var r in Results.Where(r => Matches(r, ReviewFilter.Good) && r.Top is not null).ToList())
                r.Choose(r.Top);
        }
        finally { _bulk = false; }
        UpdateScore();
        ApplyFilter();
    }

    public async Task AddFilesAsync(IEnumerable<string> paths)
    {
        var files = Expand(paths).ToList();
        if (files.Count == 0) return;

        await _gate.WaitAsync();
        try
        {
            IsBusy = true;
            for (int i = 0; i < files.Count; i++)
            {
                BusyText = $"Identifying {i + 1} of {files.Count}: {Path.GetFileName(files[i])}";
                await IdentifyOneAsync(files[i]);
            }
        }
        finally
        {
            IsBusy = false;
            _gate.Release();
        }
    }

    /// <summary>A photo sent by the phone app: identify it like a dropped file and hand the result back.
    /// Call on the UI thread.</summary>
    public async Task<ResultItemViewModel> AddPhonePhotoAsync(string file)
    {
        await _gate.WaitAsync();
        try
        {
            IsBusy = true;
            BusyText = $"Identifying phone scan: {Path.GetFileName(file)}";
            return await IdentifyOneAsync(file);
        }
        finally
        {
            IsBusy = false;
            _gate.Release();
        }
    }

    private async Task<ResultItemViewModel> IdentifyOneAsync(string file)
    {
        ResultItemViewModel item;
        try
        {
            var result = await Task.Run(() => _recognizer.IdentifyFile(file));
            item = new ResultItemViewModel(result, this);
            SaveCropDiagnostics(result);
        }
        catch (Exception ex)
        {
            Log.Error($"Identify {file}", ex);
            item = ResultItemViewModel.Failed(Path.GetFileName(file), ex.Message, this);
        }
        item.ScanNumber = ++_scanCount;
        Results.Insert(0, item);
        _ = item.LoadThumbnailsAsync(_thumbs);
        return item;
    }

    // ---- Settings (gear menu) ----

    /// <summary>Unsure finish → non-foil instead of "Check finish". Off by default.</summary>
    public bool AssumeNonFoil
    {
        get => _settings.AssumeNonFoil;
        set
        {
            if (_settings.AssumeNonFoil == value) return;
            _settings.AssumeNonFoil = value; _settings.Save();
            OnPropertyChanged();
            foreach (var r in Results) r.RefreshFinish();
            ApplyFilter();
        }
    }

    /// <summary>Listen for the Android scanner app on this network.</summary>
    public bool PhoneLinkOn
    {
        get => _settings.PhoneLink;
        set
        {
            if (_settings.PhoneLink == value) return;
            _settings.PhoneLink = value; _settings.Save();
            OnPropertyChanged();
            if (value) PhoneLink.Instance.Start(); else PhoneLink.Instance.Stop();
        }
    }

    [ObservableProperty] private string _phoneLinkStatus = "";

    /// <summary>A photo from the phone: saved under phone_scans/&lt;date&gt;/, identified like a dropped file,
    /// and summed up for the phone's screen. Runs off the UI thread; the page update runs on it.</summary>
    private async Task<object> HandlePhoneScanAsync(byte[] jpeg)
    {
        var dir = Path.Combine(_paths.Root, "phone_scans", DateTime.Now.ToString("yyyy-MM-dd"));
        Directory.CreateDirectory(dir);
        var file = Path.Combine(dir, $"phone_{DateTime.Now:HHmmss_fff}.jpg");
        await File.WriteAllBytesAsync(file, jpeg);
        return await Avalonia.Threading.Dispatcher.UIThread.InvokeAsync(async () =>
        {
            var item = await AddPhonePhotoAsync(file);
            var card = item.ShownCard;
            return (object)new
            {
                ok = item.HasResult && card is not null,
                scan = item.ScanLabel,
                name = card?.Name,
                set = card?.SetName,
                setCode = card?.SetCode.ToUpperInvariant(),
                number = card?.CollectorNumber,
                finish = item.SelectedFinish?.Label,
                finishUnsure = item.FinishUnsure,
                pinned = item.IsPinned,
                pinReason = item.PinReason,
                price = item.Price,
                error = item.Error ?? (card is null ? "No card found in the photo." : null),
            };
        });
    }

    private static IEnumerable<string> Expand(IEnumerable<string> paths)
    {
        foreach (var p in paths)
        {
            if (Directory.Exists(p))
            {
                foreach (var f in Directory.EnumerateFiles(p).Order())
                    if (ImageExtensions.Contains(Path.GetExtension(f).ToLowerInvariant())) yield return f;
            }
            else if (File.Exists(p))
            {
                yield return p;
            }
        }
    }

    /// <summary>
    /// Keeps a copy of each straightened card (what the scanner actually looked at) in logs/crops, plus how
    /// its outline was found, so crop problems can be investigated from the files alone.
    /// </summary>
    private void SaveCropDiagnostics(RecognitionResult result)
    {
        try
        {
            var dir = Path.Combine(_paths.LogsDir, "crops");
            Directory.CreateDirectory(dir);
            var safe = string.Concat($"{result.Folder}_{Path.GetFileNameWithoutExtension(result.Source)}".Split(Path.GetInvalidFileNameChars()));
            File.WriteAllBytes(Path.Combine(dir, safe + ".jpg"), result.CardImageJpeg);
            var index = Path.Combine(dir, "crops.csv");
            bool newFile = !File.Exists(index);
            using var w = new StreamWriter(index, append: true);
            if (newFile) w.WriteLine("time,photo,outline_method,corners_tl_tr_br_bl,upside_down,app_version");
            w.WriteLine(string.Join(",", new[]
            {
                DateTime.Now.ToString("s"), $"{result.Folder} / {result.Source}", result.OutlineMethod,
                result.OutlineCorners, result.UpsideDown.ToString(),
                typeof(IdentifyViewModel).Assembly.GetName().Version?.ToString(3) ?? "",
            }.Select(Csv)));
        }
        catch (Exception ex) { Log.Error("Save crop diagnostics", ex); }
    }

    /// <summary>Overwrite the saved crop with the overlay-straightened one (diagnostics).</summary>
    internal void SaveStraightenedCrop(ResultItemViewModel item, byte[] jpeg)
    {
        try
        {
            if (item.Result is not { } r) return;
            var dir = Path.Combine(_paths.LogsDir, "crops");
            Directory.CreateDirectory(dir);
            var safe = string.Concat($"{r.Folder}_{Path.GetFileNameWithoutExtension(r.Source)}".Split(Path.GetInvalidFileNameChars()));
            File.WriteAllBytes(Path.Combine(dir, safe + "_straightened.jpg"), jpeg);
        }
        catch (Exception ex) { Log.Error("Save straightened crop", ex); }
    }

    /// <summary>Re-identifies a photo with the card turned the other way up, replacing its result.</summary>
    internal async Task<ResultItemViewModel?> FlipAsync(ResultItemViewModel item)
    {
        if (item.Result?.FilePath is not { } file) return null;
        int index = Results.IndexOf(item);
        if (index < 0) return null;
        bool nowUpsideDown = !item.Result.UpsideDown;
        // The recognizer handles one photo at a time: wait for any batch that's still running.
        await _gate.WaitAsync();
        try
        {
            var result = await Task.Run(() => _recognizer.IdentifyFile(file, forceUpsideDown: nowUpsideDown));
            var replacement = new ResultItemViewModel(result, this) { WasFlipped = true, ScanNumber = item.ScanNumber };
            Results[index] = replacement;
            await replacement.LoadThumbnailsAsync(_thumbs);
            UpdateScore();
            return replacement;
        }
        catch (Exception ex) { Log.Error($"Flip {file}", ex); return null; }
        finally { _gate.Release(); }
    }

    /// <summary>Flip from the big compare view: re-identify upside down and stay in the compare view.</summary>
    private async Task FlipInCompare(CompareViewModel from)
    {
        var replacement = await FlipAsync(from.Item);
        if (replacement?.Top is { } top) OpenCompare(replacement, top, from.BottomOnly);
    }

    // ---- Compare view (big side-by-side) ----

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(IsComparing))]
    private CompareViewModel? _compare;

    public bool IsComparing => Compare is not null;

    /// <summary>Where the compare view puts the card info and buttons. Remembered between runs.</summary>
    public CompareLayout Layout
    {
        get => _settings.Layout;
        set { _settings.Layout = value; _settings.Save(); }
    }

    internal void OpenCompare(ResultItemViewModel item, CandidateViewModel candidate, bool bottomOnly = false) =>
        Compare = new CompareViewModel(item, candidate, () => Compare = null, AdvanceCompare, bottomOnly, QueueText(item), FlipInCompare,
            HasHistory ? GoBack : null, Layout, l => Layout = l);

    private static bool Waiting(ResultItemViewModel r) => r.IsShown && r.Verdict == Verdict.None && r.Top is not null;

    private string QueueText(ResultItemViewModel current)
    {
        int left = Results.Count(r => Waiting(r) || r == current && r.Verdict == Verdict.None);
        return left == 1 ? "Last card to check" : $"{left} cards left to check";
    }

    /// <summary>After marking (or skipping) a card in the big view, go straight to the next card
    /// still waiting in this tab, keeping the zoom setting. Closes when nothing's left.</summary>
    private void AdvanceCompare(CompareViewModel from)
    {
        _history.Add(from.Item);
        int start = Results.IndexOf(from.Item);
        for (int k = 1; k <= Results.Count; k++)
        {
            var next = Results[(start + k + Results.Count) % Results.Count];
            if (next == from.Item || !Waiting(next)) continue;
            OpenCompare(next, next.Top!, from.BottomOnly);
            return;
        }
        Compare = null;
    }

    [RelayCommand]
    private void CloseCompare() => Compare = null;

    /// <summary>Cards already looked at in the compare view, most recent last ("◀ Last card").</summary>
    private readonly List<ResultItemViewModel> _history = [];
    private bool HasHistory => _history.Any(Results.Contains);

    /// <summary>Back to the card before this one (to fix a mis-click), showing what you picked for it.</summary>
    private void GoBack(CompareViewModel from)
    {
        while (_history.Count > 0)
        {
            var prev = _history[^1];
            _history.RemoveAt(_history.Count - 1);
            if (!Results.Contains(prev) || prev.Top is null) continue;
            OpenCompare(prev, prev.Chosen ?? prev.Top, from.BottomOnly);
            return;
        }
    }

    /// <summary>Called when the user marks a result. rank = 1-based position of the exact printing,
    /// -1 = right card but the exact printing wasn't listed, 0 = wrong card.</summary>
    internal void Record(ResultItemViewModel item, int rank)
    {
        UpdateScore();
        ApplyFilter();
        try
        {
            bool newFile = !File.Exists(_logPath);
            using var w = new StreamWriter(_logPath, append: true);
            if (newFile)
                w.WriteLine("time,folder,photo,rank_of_correct,correct_id,correct_name,correct_set,correct_number,top_id,top_name,top_set,top_number,top_score,name_margin,outline_found,upside_down,flipped_by_user,pinned,flag,name_read,collector_read,foil_read,ms,pin_reason,border,runner_up_set,runner_up_number,runner_up_score,app_version,finish,finish_detected,finish_reason,list_symbol_score,shooting_star_score,outline_method,detail_pick,detail_margin,straightened,rarity,condition,altered,misprint,image_sim");
            // What you saw: the current top (after any detail-check reordering), not the first guess.
            var top = item.Top?.Source;
            var second = item.Candidates.Skip(1).FirstOrDefault()?.Source;
            // rank is the position in the list as shown (after any detail-check reordering)
            var right = rank > 0 && rank <= item.Candidates.Count ? item.Candidates[rank - 1].Source : null;
            string rightName = right?.Card.Name ?? (rank == -1 ? top?.Card.Name ?? "" : "");
            string[] cols =
            [
                DateTime.Now.ToString("s"), item.Result?.Folder ?? "", item.Photo, rank.ToString(),
                right?.Card.Id ?? "", rightName, right?.Card.SetCode ?? "", right?.Card.CollectorNumber ?? "",
                top?.Card.Id ?? "", top?.Card.Name ?? "", top?.Card.SetCode ?? "", top?.Card.CollectorNumber ?? "",
                (top?.Score ?? 0).ToString("0.0000", CultureInfo.InvariantCulture),
                (item.Result?.NameMargin ?? 0).ToString("0.0000", CultureInfo.InvariantCulture),
                (item.Result?.CardOutlineFound ?? false).ToString(), (item.Result?.UpsideDown ?? false).ToString(),
                item.WasFlipped.ToString(), item.IsPinned.ToString(), item.FlagReason ?? "",
                item.Result?.NameRead ?? "", item.Result?.Collector.Raw ?? "", item.Result?.FoilFromCollector?.ToString() ?? "",
                ((int)(item.Result?.Elapsed.TotalMilliseconds ?? 0)).ToString(),
                item.PinReason ?? "", item.Result?.BorderColor ?? "",
                second?.Card.SetCode ?? "", second?.Card.CollectorNumber ?? "",
                (second?.Score ?? 0).ToString("0.0000", CultureInfo.InvariantCulture),
                typeof(IdentifyViewModel).Assembly.GetName().Version?.ToString(3) ?? "",
                item.SelectedFinish?.Key ?? "", item.FinishDetectedKey, item.FinishReason,
                (item.Result?.ListSymbolScore ?? 0).ToString("0.000", CultureInfo.InvariantCulture),
                (item.Result?.ShootingStarScore ?? 0).ToString("0.000", CultureInfo.InvariantCulture),
                item.Result?.OutlineMethod ?? "",
                item.DetailPick, item.DetailMargin.ToString("0.000", CultureInfo.InvariantCulture),
                item.Straightened.ToString(),
                (right?.Card ?? top?.Card)?.Rarity ?? "", ResultItemViewModel.ConditionCode(item.Condition),
                item.Altered.ToString(), item.Misprint.ToString(),
                (top?.ImageSimilarity ?? 0).ToString("0.000", CultureInfo.InvariantCulture),
            ];
            w.WriteLine(string.Join(",", cols.Select(Csv)));
        }
        catch (Exception ex) { Log.Error("Write identify log", ex); }
    }

    private static string Csv(string s) => s.Contains(',') || s.Contains('"') ? $"\"{s.Replace("\"", "\"\"")}\"" : s;

    private void UpdateScore()
    {
        var reviewed = Results.Where(r => r.Verdict != Verdict.None).ToList();
        if (reviewed.Count == 0) { ScoreText = "Mark each result ✓ or pick the right card to track accuracy."; return; }
        int n = reviewed.Count;
        int top1 = reviewed.Count(r => r.Verdict == Verdict.TopCorrect);
        int top5 = reviewed.Count(r => r.Verdict is Verdict.TopCorrect or Verdict.LowerCorrect);
        int name = reviewed.Count(r => r.Verdict != Verdict.NotListed);
        string Pct(int k) => $"{k}/{n} ({100.0 * k / n:0}%)";
        ScoreText = $"Exact printing on top: {Pct(top1)}   ·   In top 5: {Pct(top5)}   ·   Right card: {Pct(name)}";
    }

    [RelayCommand]
    private void Clear()
    {
        Results.Clear();
        _scanCount = 0;
        _history.Clear();
        ScoreText = "Drop some card photos in to get started.";
    }

    [RelayCommand]
    private void OpenLogFolder()
    {
        try
        {
            System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(_paths.LogsDir) { UseShellExecute = true });
        }
        catch (Exception ex) { Log.Error("Open log folder", ex); }
    }
}
