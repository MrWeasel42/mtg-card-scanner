using System.Collections.ObjectModel;
using System.Globalization;
using Avalonia.Media.Imaging;
using CardScanner.Core;
using CardScanner.Core.Recognition;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace CardScanner.App.ViewModels;

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
        _logPath = Path.Combine(paths.LogsDir, "identify_results.csv");
        Results.CollectionChanged += (_, _) => OnPropertyChanged(nameof(HasResults));
    }

    public bool HasResults => Results.Count > 0;

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
    internal async Task FlipAsync(ResultItemViewModel item)
    {
        if (item.Result?.FilePath is not { } file) return;
        int index = Results.IndexOf(item);
        if (index < 0) return;
        bool nowUpsideDown = !item.Result.UpsideDown;
        try
        {
            var result = await Task.Run(() => _recognizer.IdentifyFile(file, forceUpsideDown: nowUpsideDown));
            var replacement = new ResultItemViewModel(result, this) { WasFlipped = true };
            Results[index] = replacement;
            _ = replacement.LoadThumbnailsAsync(_thumbs);
            UpdateScore();
        }
        catch (Exception ex) { Log.Error($"Flip {file}", ex); }
    }

    // ---- Compare view (big side-by-side) ----

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(IsComparing))]
    private CompareViewModel? _compare;

    public bool IsComparing => Compare is not null;

    internal void OpenCompare(ResultItemViewModel item, CandidateViewModel candidate) =>
        Compare = new CompareViewModel(item, candidate, () => Compare = null);

    [RelayCommand]
    private void CloseCompare() => Compare = null;

    /// <summary>Called when the user marks a result. rank = 1-based position of the exact printing,
    /// -1 = right card but the exact printing wasn't listed, 0 = wrong card.</summary>
    internal void Record(ResultItemViewModel item, int rank)
    {
        UpdateScore();
        try
        {
            bool newFile = !File.Exists(_logPath);
            using var w = new StreamWriter(_logPath, append: true);
            if (newFile)
                w.WriteLine("time,folder,photo,rank_of_correct,correct_id,correct_name,correct_set,correct_number,top_id,top_name,top_set,top_number,top_score,name_margin,outline_found,upside_down,flipped_by_user,used_inner_outline,ms");
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
                item.WasFlipped.ToString(), (item.Result?.UsedInnerOutline ?? false).ToString(),
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
