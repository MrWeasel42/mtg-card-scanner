using System.Collections.ObjectModel;
using Avalonia.Media.Imaging;
using CardScanner.Core.Catalog;
using CardScanner.Core.Recognition;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace CardScanner.App.ViewModels;

public enum Verdict { None, TopCorrect, LowerCorrect, NotListed }

/// <summary>One photo's result: the straightened card, the top matches, and the user's verdict.</summary>
public partial class ResultItemViewModel : ObservableObject
{
    private readonly IdentifyViewModel _owner;

    public RecognitionResult? Result { get; }
    public string Photo { get; }
    public Bitmap? CardImage { get; }
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
    [NotifyPropertyChangedFor(nameof(VerdictText), nameof(IsReviewed))]
    private Verdict _verdict;

    public bool IsReviewed => Verdict != Verdict.None;

    public string VerdictText => Verdict switch
    {
        Verdict.TopCorrect => "✓ Top match was right",
        Verdict.LowerCorrect => $"✓ Right card was #{Candidates.ToList().FindIndex(c => c.IsChosen) + 1}",
        Verdict.NotListed => "✗ Right card wasn't in the list",
        _ => "",
    };

    public ResultItemViewModel(RecognitionResult result, Bitmap? image, IdentifyViewModel owner)
    {
        _owner = owner;
        Result = result;
        Photo = result.Source;
        CardImage = image;
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
            c.Thumbnail = await cache.GetAsync(c.Card);
    }

    internal void Choose(CandidateViewModel? chosen)
    {
        foreach (var c in Candidates) c.IsChosen = c == chosen;
        Verdict = chosen is null ? Verdict.NotListed : chosen.Rank == 1 ? Verdict.TopCorrect : Verdict.LowerCorrect;
        OnPropertyChanged(nameof(VerdictText));
        _owner.Record(this, chosen?.Rank ?? 0);
    }

    [RelayCommand] private void MarkTopCorrect() => Choose(Top);
    [RelayCommand] private void MarkNotListed() => Choose(null);
}

public partial class CandidateViewModel(Candidate candidate, int rank, ResultItemViewModel owner) : ObservableObject
{
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

    [ObservableProperty] private Bitmap? _thumbnail;
    [ObservableProperty] private bool _isChosen;

    [RelayCommand] private void Pick() => owner.Choose(this);
}
