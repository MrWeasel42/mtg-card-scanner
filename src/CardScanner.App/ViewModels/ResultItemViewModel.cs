using System.Collections.ObjectModel;
using Avalonia.Media;
using Avalonia.Media.Imaging;
using CardScanner.Core.Catalog;
using CardScanner.Core.Recognition;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace CardScanner.App.ViewModels;

public enum Verdict { None, TopCorrect, LowerCorrect, NameOnly, NotListed }

/// <summary>One photo's result: the straightened card, the top matches, and the user's verdict.</summary>
public partial class ResultItemViewModel : ObservableObject
{
    private readonly IdentifyViewModel _owner;
    private Bitmap? _fullImage;

    public RecognitionResult? Result { get; }
    public string Photo { get; }
    /// <summary>Downsized copy for the list (saves memory).</summary>
    public Bitmap? CardImage { get; }
    /// <summary>Full-resolution straightened photo, loaded the first time the compare view needs it.</summary>
    public Bitmap? FullImage => _fullImage ??= Images.Full(Result?.CardImageJpeg);
    public string? Error { get; }
    public bool HasError => Error is not null;
    public bool HasResult => Result is not null;
    public ObservableCollection<CandidateViewModel> Candidates { get; } = [];
    public CandidateViewModel? Top => Candidates.FirstOrDefault();
    public ObservableCollection<CandidateViewModel> Others { get; } = [];

    public string Notes
    {
        get
        {
            if (Result is null) return "";
            var notes = new List<string>();
            if (!Result.CardOutlineFound) notes.Add("Couldn't find the card's edges — used the whole photo. Try a plain, contrasting background.");
            if (Result.UpsideDown) notes.Add("Card was upside down (handled).");
            notes.Add($"{Result.Elapsed.TotalSeconds:0.0} s");
            return string.Join("  ·  ", notes);
        }
    }

    /// <summary>What the scanner read off the card, shown so you can see why it chose what it chose.</summary>
    public string ReadText
    {
        get
        {
            if (Result is null) return "";
            var name = Result.NameRead is { Length: > 0 } n ? $"“{n}”" : "couldn't read";
            var coll = Result.Collector.Raw is { Length: > 0 } c ? $"“{c}”" : "couldn't read";
            var foil = Result.FoilFromCollector switch { true => " · ★ foil", false => " · • non-foil", _ => "" };
            var border = Result.BorderColor is { } b ? $"   ·   Border: {b}" : "";
            return $"Read name: {name}   ·   Collector line: {coll}{foil}{border}";
        }
    }

    /// <summary>Whether the current filter tab shows this result.</summary>
    [ObservableProperty] private bool _isShown = true;

    public bool IsPinned => Result?.Pinned == true;
    /// <summary>Pins that lean on more than a printed set code: worth a closer look when spot-checking.</summary>
    public bool IsSoftPin => IsPinned && Result?.PinReason is { } r && !r.StartsWith("name + set");
    public string PinText => IsSoftPin ? $"📌 Pinned by {Result!.PinReason}" : "📌 Pinned: name + set + number agree";
    public bool IsFlagged => Result?.Flagged == true;
    public string? FlagReason => Result?.FlagReason;

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(VerdictText), nameof(IsReviewed), nameof(VerdictBrush))]
    private Verdict _verdict;

    public bool IsReviewed => Verdict != Verdict.None;

    public IBrush VerdictBrush => Verdict switch
    {
        Verdict.TopCorrect => new SolidColorBrush(Color.Parse("#22C55E")),
        Verdict.LowerCorrect => new SolidColorBrush(Color.Parse("#F5B942")),
        Verdict.NameOnly => new SolidColorBrush(Color.Parse("#FB923C")),
        Verdict.NotListed => new SolidColorBrush(Color.Parse("#F87171")),
        _ => Brushes.Transparent,
    };

    public string VerdictText => Verdict switch
    {
        Verdict.TopCorrect => "✓ Exact printing was the top match",
        Verdict.LowerCorrect => $"✓ Exact printing was #{Candidates.ToList().FindIndex(c => c.IsChosen) + 1}",
        Verdict.NameOnly => "≈ Right card, wrong printing",
        Verdict.NotListed => "✗ Wrong card",
        _ => "",
    };

    public ResultItemViewModel(RecognitionResult result, IdentifyViewModel owner)
    {
        _owner = owner;
        Result = result;
        Photo = string.IsNullOrEmpty(result.Folder) ? result.Source : $"{result.Folder} / {result.Source}";
        CardImage = Images.Small(result.CardImageJpeg, 420);
        int rank = 1;
        foreach (var c in result.Candidates)
        {
            var vm = new CandidateViewModel(c, rank++, this);
            Candidates.Add(vm);
            if (vm.Rank > 1) Others.Add(vm);
        }
        RefreshFinish();
    }

    // ---- Finish (foil / non-foil / etched) for the printing currently selected ----

    private bool _finishByUser, _settingFinish;
    private int _lastRank;

    /// <summary>The printing this result currently stands for: the one you picked, else the top match.</summary>
    public CardInfo? SelectedCard => (Candidates.FirstOrDefault(c => c.IsChosen) ?? Top)?.Card;

    [ObservableProperty] private IReadOnlyList<Finish.Option> _finishOptions = [];
    [ObservableProperty] private Finish.Option? _selectedFinish;
    [ObservableProperty] private string _finishNote = "";
    [ObservableProperty] private bool _finishUnsure;
    public string FinishDetectedKey { get; private set; } = "";
    public string FinishReason { get; private set; } = "";
    public bool HasFinishChoice => FinishOptions.Count > 1;

    private void RefreshFinish()
    {
        if (SelectedCard is not { } card) return;
        var keep = _finishByUser ? SelectedFinish?.Key : null;
        var (key, reason, sure) = Finish.Detect(card, Result?.FoilFromCollector, Result?.ShootingStarScore);
        FinishDetectedKey = key; FinishReason = reason;
        _settingFinish = true;
        FinishOptions = Finish.OptionsFor(card);
        SelectedFinish = FinishOptions.FirstOrDefault(o => o.Key == keep) ?? FinishOptions.FirstOrDefault(o => o.Key == key);
        _settingFinish = false;
        FinishUnsure = !sure && FinishOptions.Count > 1;
        FinishNote = FinishOptions.Count <= 1 ? $"({reason})" : sure ? $"detected: {reason}" : reason;
        OnPropertyChanged(nameof(HasFinishChoice));
    }

    partial void OnSelectedFinishChanged(Finish.Option? value)
    {
        if (_settingFinish || value is null) return;
        _finishByUser = true;
        FinishUnsure = false;
        _owner.ApplyFilter();
        FinishNote = value.Key == FinishDetectedKey ? $"detected: {FinishReason}" : "set by you";
        if (Verdict != Verdict.None) _owner.Record(this, _lastRank);   // keep the log up to date
    }

    private ResultItemViewModel(string photo, string error, IdentifyViewModel owner)
    {
        _owner = owner;
        Photo = photo;
        Error = error;
    }

    public static ResultItemViewModel Failed(string photo, string error, IdentifyViewModel owner) => new(photo, error, owner);

    public async Task LoadThumbnailsAsync(ThumbnailCache cache)
    {
        foreach (var c in Candidates)
        {
            c.ImagePath = await cache.GetPathAsync(c.Card);
            c.Thumbnail = Images.SmallFromFile(c.ImagePath, 360);
        }
    }

    internal void Choose(CandidateViewModel? chosen, Verdict? verdict = null)
    {
        foreach (var c in Candidates) c.IsChosen = c == chosen;
        Verdict = verdict ?? (chosen is null ? Verdict.NotListed : chosen.Rank == 1 ? Verdict.TopCorrect : Verdict.LowerCorrect);
        OnPropertyChanged(nameof(VerdictText));
        int rank = Verdict switch { Verdict.NameOnly => -1, _ => chosen?.Rank ?? 0 };
        _lastRank = rank;
        RefreshFinish();
        _owner.Record(this, rank);
    }

    internal void OpenCompare(CandidateViewModel candidate) => _owner.OpenCompare(this, candidate);

    [RelayCommand] private void MarkTopCorrect() => Choose(Top);
    [RelayCommand] private void MarkNameOnly() => Choose(null, Verdict.NameOnly);
    [RelayCommand] private void MarkNotListed() => Choose(null);
    [RelayCommand] private void Compare() { if (Top is { } t) OpenCompare(t); }
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(FlipLabel))]
    private bool _isFlipping;

    public string FlipLabel => IsFlipping ? "↻ Flipping…" : "↻ Flip";

    /// <summary>Re-identify turned around. Takes a few seconds, so show it's working and ignore extra clicks.</summary>
    [RelayCommand]
    private async Task Flip()
    {
        if (IsFlipping) return;
        IsFlipping = true;
        try { await _owner.FlipAsync(this); }
        finally { IsFlipping = false; }
    }

    /// <summary>True if the user turned this card around with the Flip button.</summary>
    public bool WasFlipped { get; init; }
    public bool CanFlip => Result?.FilePath is not null;
}

public partial class CandidateViewModel(Candidate candidate, int rank, ResultItemViewModel owner) : ObservableObject
{
    private Bitmap? _fullImage;

    public ResultItemViewModel Owner { get; } = owner;
    public CardInfo Card { get; } = candidate.Card;
    public int Rank { get; } = rank;
    public string Name => Card.Name;
    public string SetLabel => Card.SetLabel;
    public string Extra
    {
        get
        {
            var parts = new List<string>();
            if (Card.IsListReprint) parts.Add("The List");
            if (!string.IsNullOrEmpty(Card.SpecialFoil)) parts.Add(Card.SpecialFoil);
            if (Card.PromoTypes.Contains("prerelease")) parts.Add("Prerelease");
            if (Card.PromoTypes.Contains("promopack")) parts.Add("Promo pack");
            parts.Add(Card.BestPriceText ?? "no price");
            return string.Join(" · ", parts);
        }
    }
    public string ScoreText
    {
        get
        {
            var why = new List<string>();
            if (candidate.NameMatched) why.Add("name");
            if (candidate.SetMatched) why.Add("set");
            if (candidate.NumberMatched) why.Add("number");
            var matched = why.Count > 0 ? $"matched {string.Join(" + ", why)} · " : "";
            return $"{matched}picture {candidate.ImageSimilarity * 100:0}%";
        }
    }

    public string? ImagePath { get; set; }
    public Bitmap? FullImage => _fullImage ??= Images.FullFromFile(ImagePath);

    [ObservableProperty] private Bitmap? _thumbnail;
    [ObservableProperty] private bool _isChosen;

    [RelayCommand] private void Pick() => Owner.Choose(this);
    [RelayCommand] private void Compare() => Owner.OpenCompare(this);
}

/// <summary>Helpers for decoding images at the right size.</summary>
internal static class Images
{
    public static Bitmap? Small(byte[]? bytes, int width)
    {
        if (bytes is null) return null;
        try { return Bitmap.DecodeToWidth(new MemoryStream(bytes), width, BitmapInterpolationMode.HighQuality); }
        catch { return null; }
    }

    public static Bitmap? Full(byte[]? bytes)
    {
        if (bytes is null) return null;
        try { return new Bitmap(new MemoryStream(bytes)); } catch { return null; }
    }

    public static Bitmap? SmallFromFile(string? path, int width)
    {
        if (path is null) return null;
        try { using var fs = File.OpenRead(path); return Bitmap.DecodeToWidth(fs, width, BitmapInterpolationMode.HighQuality); }
        catch { return null; }
    }

    public static Bitmap? FullFromFile(string? path)
    {
        if (path is null) return null;
        try { return new Bitmap(path); } catch { return null; }
    }
}
