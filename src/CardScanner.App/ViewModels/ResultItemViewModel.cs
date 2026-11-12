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
            if (Result.UsedInnerOutline) notes.Add("Looked like a sleeve — used the card inside it.");
            notes.Add($"{Result.Elapsed.TotalMilliseconds:0} ms");
            return string.Join("  ·  ", notes);
        }
    }

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
        _owner.Record(this, rank);
    }

    internal void OpenCompare(CandidateViewModel candidate) => _owner.OpenCompare(this, candidate);

    [RelayCommand] private void MarkTopCorrect() => Choose(Top);
    [RelayCommand] private void MarkNameOnly() => Choose(null, Verdict.NameOnly);
    [RelayCommand] private void MarkNotListed() => Choose(null);
    [RelayCommand] private void Compare() { if (Top is { } t) OpenCompare(t); }
    [RelayCommand] private Task Flip() => _owner.FlipAsync(this);

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
    public string ScoreText => $"{candidate.Score * 100:0.0}% match";

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
