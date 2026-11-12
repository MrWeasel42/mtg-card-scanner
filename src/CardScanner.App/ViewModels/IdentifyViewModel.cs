using System.Collections.ObjectModel;
using System.Globalization;
using Avalonia.Media.Imaging;
using CardScanner.Core;
using CardScanner.Core.Recognition;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace CardScanner.App.ViewModels;

public enum ReviewFilter { Queue, Good, Done, All }

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

    public ObservableCollection<ResultItemViewModel> Results { get; } = [];

    [ObservableProperty] private bool _isBusy;
    [ObservableProperty] private string _busyText = "";
    [ObservableProperty] private string _scoreText = "Drop some card photos in to get started.";

    public IdentifyViewModel(Recognizer recognizer, AppPaths paths)
    {
        _recognizer = recognizer;
        _paths = paths;
        _thumbs = new ThumbnailCache(paths);
        _logPath = Path.Combine(paths.LogsDir, "identify_results_v2.csv");
        Results.CollectionChanged += (_, _) => { OnPropertyChanged(nameof(HasResults)); ApplyFilter(); };
    }

    public bool HasResults => Results.Count > 0;

    // ---- Review queue: unsure cards show up, and drop off once verified ----

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(IsQueue), nameof(IsGood), nameof(IsDone), nameof(IsAll))]
    private ReviewFilter _filter = ReviewFilter.Queue;

    public bool IsQueue => Filter == ReviewFilter.Queue;
    public bool IsGood => Filter == ReviewFilter.Good;
    public bool IsDone => Filter == ReviewFilter.Done;
    public bool IsAll => Filter == ReviewFilter.All;

    [ObservableProperty] private string _queueLabel = "To verify";
    [ObservableProperty] private string _goodLabel = "📌 Pinned";
    [ObservableProperty] private string _doneLabel = "✓ Done";
    [ObservableProperty] private string _allLabel = "All";
    [ObservableProperty] private string _emptyFilterText = "";
    [ObservableProperty] private bool _canAcceptGood;

    partial void OnFilterChanged(ReviewFilter value) => ApplyFilter();

    [RelayCommand]
    private void SetFilter(string name) => Filter = Enum.Parse<ReviewFilter>(name);

    private static bool Matches(ResultItemViewModel r, ReviewFilter f) => f switch
    {
        // Anything the scanner couldn't pin down (flagged, unpinned, or failed), not yet marked.
        ReviewFilter.Queue => r.Verdict == Verdict.None && !r.IsPinned,
        ReviewFilter.Good => r.Verdict == Verdict.None && r.IsPinned,
        ReviewFilter.Done => r.Verdict != Verdict.None,
        _ => true,
    };

    internal void ApplyFilter()
    {
        foreach (var r in Results) r.IsShown = Matches(r, Filter);
        int Count(ReviewFilter f) => Results.Count(r => Matches(r, f));
        int q = Count(ReviewFilter.Queue);
        QueueLabel = $"To verify ({q})";
        GoodLabel = $"📌 Pinned ({Count(ReviewFilter.Good)})";
        DoneLabel = $"✓ Done ({Count(ReviewFilter.Done)})";
        AllLabel = $"All ({Results.Count})";
        CanAcceptGood = Count(ReviewFilter.Good) > 0;
        EmptyFilterText = !HasResults || Count(Filter) > 0 ? "" : Filter switch
        {
            ReviewFilter.Queue => "Queue's clear, nothing left to verify. 🎉 Peek at the Pinned tab if you want to double-check those.",
            ReviewFilter.Good => "No unmarked pinned cards left.",
            ReviewFilter.Done => "Nothing marked yet.",
            _ => "",
        };
    }

    /// <summary>Marks every pinned card that isn't marked yet as correct, in one go.</summary>
    [RelayCommand]
    private void AcceptGood()
    {
        foreach (var r in Results.Where(r => Matches(r, ReviewFilter.Good) && r.Top is not null).ToList())
            r.Choose(r.Top);
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
                var file = files[i];
                ResultItemViewModel item;
                try
                {
                    var result = await Task.Run(() => _recognizer.IdentifyFile(file));
                    item = new ResultItemViewModel(result, this);
                }
                catch (Exception ex)
                {
                    Log.Error($"Identify {file}", ex);
                    item = ResultItemViewModel.Failed(Path.GetFileName(file), ex.Message, this);
                }
                Results.Insert(0, item);
                _ = item.LoadThumbnailsAsync(_thumbs);
            }
        }
        finally
        {
            IsBusy = false;
            _gate.Release();
        }
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
            var replacement = new ResultItemViewModel(result, this) { WasFlipped = true };
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

    internal void OpenCompare(ResultItemViewModel item, CandidateViewModel candidate, bool bottomOnly = false) =>
        Compare = new CompareViewModel(item, candidate, () => Compare = null, AdvanceCompare, bottomOnly, QueueText(item), FlipInCompare);

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
                w.WriteLine("time,folder,photo,rank_of_correct,correct_id,correct_name,correct_set,correct_number,top_id,top_name,top_set,top_number,top_score,name_margin,outline_found,upside_down,flipped_by_user,pinned,flag,name_read,collector_read,foil_read,ms");
            var top = item.Result?.Best;
            var right = rank > 0 ? item.Result!.Candidates[rank - 1] : null;
            string rightName = right?.Card.Name ?? (rank == -1 ? top?.Card.Name ?? "" : "");
            string[] cols =
            [
                DateTime.Now.ToString("s"), item.Result?.Folder ?? "", item.Photo, rank.ToString(),
                right?.Card.Id ?? "", rightName, right?.Card.SetCode ?? "", right?.Card.CollectorNumber ?? "",
                top?.Card.Id ?? "", top?.Card.Name ?? "", top?.Card.SetCode ?? "", top?.Card.CollectorNumber ?? "",
                (top?.Score ?? 0).ToString("0.0000", CultureInfo.InvariantCulture),
                (item.Result?.NameMargin ?? 0).ToString("0.0000", CultureInfo.InvariantCulture),
                (item.Result?.CardOutlineFound ?? false).ToString(), (item.Result?.UpsideDown ?? false).ToString(),
                item.WasFlipped.ToString(), (item.Result?.Pinned ?? false).ToString(), item.Result?.FlagReason ?? "",
                item.Result?.NameRead ?? "", item.Result?.Collector.Raw ?? "", item.Result?.FoilFromCollector?.ToString() ?? "",
                ((int)(item.Result?.Elapsed.TotalMilliseconds ?? 0)).ToString(),
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
