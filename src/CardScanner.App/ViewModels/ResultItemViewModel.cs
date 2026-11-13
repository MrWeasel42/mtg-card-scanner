using System.Collections.ObjectModel;
using Avalonia.Media;
using Avalonia.Media.Imaging;
using CardScanner.Core.Catalog;
using CardScanner.Core.Recognition;
using CardScanner.Core.Vision;
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
    /// <summary>Order the card came in (1 = first card scanned this session). Shown as "Scan 0001".</summary>
    public int ScanNumber { get; set; }
    public string ScanLabel => ScanNumber > 0 ? $"Scan {ScanNumber:0000}" : Photo;
    /// <summary>When you marked it: the Done tab lists the most recent first.</summary>
    public DateTime? VerifiedAt { get; set; }
    public CandidateViewModel? Chosen => Candidates.FirstOrDefault(c => c.IsChosen);

    /// <summary>Search box: card name (any candidate), set code / name, scan number or photo file name.</summary>
    internal bool MatchesSearch(string query)
    {
        var q = query.Trim();
        if (q.Length == 0) return true;
        bool Has(string? s) => s is not null && s.Contains(q, StringComparison.OrdinalIgnoreCase);
        if (Has(Photo) || Has(ScanLabel) || ScanNumber.ToString("0000").Contains(q.TrimStart('#'))) return true;
        var shown = Chosen ?? Top;
        return Candidates.Any(c => Has(c.Card.Name)) || Has(shown?.Card.SetCode) || Has(shown?.Card.SetLabel);
    }
    /// <summary>The straightened card as JPEG: from the outline at first, replaced by the overlay-straightened
    /// version once the top match's catalog image is available.</summary>
    private byte[]? _cardJpeg;
    /// <summary>Downsized copy for the list (saves memory).</summary>
    [ObservableProperty] private Bitmap? _cardImage;
    /// <summary>Full-resolution straightened photo, loaded the first time the compare view needs it.</summary>
    public Bitmap? FullImage => _fullImage ??= Images.Full(_cardJpeg);
    public bool Straightened { get; private set; }
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

    // ---- Detail check: close-up comparison against each look-alike printing's catalog image ----

    /// <summary>Pinned by the detail check (set symbol, text box, artist line) after the images loaded.</summary>
    private bool _detailPinned;
    private string? _detailNote;
    public string DetailPick { get; private set; } = "";
    public double DetailMargin { get; private set; }

    public bool IsPinned => Result?.Pinned == true || _detailPinned;
    public string? PinReason => Result?.Pinned == true ? Result.PinReason : _detailPinned ? "card details (set symbol, text box, artist line)" : null;
    /// <summary>Pins that lean on more than a printed set code: worth a closer look when spot-checking.</summary>
    public bool IsSoftPin => IsPinned && PinReason is { } r && !r.StartsWith("name + set");
    public string PinText => IsSoftPin ? $"📌 Pinned by {PinReason}" : "📌 Pinned: name + set + number agree";
    public string? FlagReason => _detailPinned ? null : Result?.FlagReason;
    public bool IsFlagged => FlagReason is not null;
    public string? DetailNote => _detailNote;

    /// <summary>
    /// Once the candidates' catalog images are on disk: compare the photo up close against every printing
    /// of the top card. A clear lead moves that printing to the top; a big lead pins it. Never overrides a
    /// printing pinned by its printed set code and number.
    /// </summary>
    private async Task RunDetailCheckAsync()
    {
        if (Result is null || Top is null || Verdict != Verdict.None) return;
        var group = Candidates.Where(c => c.Card.Name == Top.Card.Name && c.ImagePath is not null).ToList();
        if (group.Count < 2) return;
        var jpeg = _cardJpeg ?? Result.CardImageJpeg;
        var scores = await Task.Run(() => DetailCompare.Score(jpeg, group.Select(c => (c.Card.Id, c.ImagePath!))));
        if (scores.Count < 2 || Verdict != Verdict.None) return;
        var ranked = scores.OrderByDescending(x => x.Score).ToList();
        // Summer Magic is pixel-identical to Revised (and Anthologies to 5th...): a small lead for one of
        // those rare reprints is noise, so the common printing keeps the spot.
        static bool Rare(CandidateViewModel c) => c.Card.SetCode is "sum" or "ath" or "brb" or "btd" or "dkm" or "ced" or "cei";
        var byId = group.ToDictionary(c => c.Card.Id);
        if (Rare(byId[ranked[0].Id]) && ranked[0].Score - ranked.Skip(1).FirstOrDefault(x => !Rare(byId[x.Id])).Score < DetailCompare.PinMargin)
        {
            var common = ranked.FirstOrDefault(x => !Rare(byId[x.Id]));
            if (common.Id is not null) { ranked.Remove(common); ranked.Insert(0, common); }
        }
        var pick = group.First(c => c.Card.Id == ranked[0].Id);
        DetailMargin = ranked[0].Score - ranked[1].Score;
        DetailPick = $"{pick.Card.SetCode} {pick.Card.CollectorNumber}";
        bool printedPin = Result.Pinned && Result.PinReason?.StartsWith("name + set + number") == true;
        if (printedPin || DetailMargin < DetailCompare.ReorderMargin) return;

        if (pick != Top)
        {
            var order = new List<CandidateViewModel> { pick };
            order.AddRange(Candidates.Where(c => c != pick));
            Rebuild(order);
            _detailNote = $"Close-up check preferred {pick.Card.SetCode.ToUpperInvariant()} #{pick.Card.CollectorNumber} over the picture match.";
        }
        if (DetailMargin >= DetailCompare.PinMargin && !Result.Pinned) _detailPinned = true;
        OnPropertyChanged(string.Empty);   // everything about this card may have changed
        RefreshFinish();
        _owner.ApplyFilter();
    }

    /// <summary>Re-number the candidates in a new order, keeping their pictures.</summary>
    private void Rebuild(List<CandidateViewModel> order)
    {
        var old = order.ToList();
        Candidates.Clear(); Others.Clear();
        int rank = 1;
        foreach (var o in old)
        {
            var vm = new CandidateViewModel(o.Source, rank++, this) { ImagePath = o.ImagePath, Thumbnail = o.Thumbnail };
            Candidates.Add(vm);
            if (vm.Rank > 1) Others.Add(vm);
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
        _cardJpeg = result.CardImageJpeg;
        CardImage = Images.Small(_cardJpeg, 420);
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

    /// <summary>The photo itself couldn't show the finish (before any "assume non-foil" setting).</summary>
    private bool _photoUnsure;

    internal void RefreshFinish()
    {
        if (SelectedCard is not { } card) return;
        var keep = _finishByUser ? SelectedFinish?.Key : null;
        bool? foilMark = Result?.FoilFromCollector ?? _markFoil;
        var (key, reason, sure) = Finish.Detect(card, foilMark, Result?.ShootingStarScore);
        if (_markFoil is { } m && Result?.FoilFromCollector is null && sure)
            reason = m ? "★ found in the photo" : "• found in the photo";
        var options = Finish.OptionsFor(card);
        _photoUnsure = !sure && options.Count > 1;
        if (_photoUnsure && _owner.AssumeNonFoil && options.Any(o => o.Key == "nonfoil"))
        {
            key = "nonfoil"; reason = "assumed non-foil (setting)"; sure = true;
        }
        FinishDetectedKey = key; FinishReason = reason;
        _settingFinish = true;
        FinishOptions = options;
        SelectedFinish = FinishOptions.FirstOrDefault(o => o.Key == keep) ?? FinishOptions.FirstOrDefault(o => o.Key == key);
        _settingFinish = false;
        FinishUnsure = !sure && FinishOptions.Count > 1 && !_finishByUser;
        FinishNote = FinishOptions.Count <= 1 ? $"({reason})" : sure ? $"detected: {reason}" : reason;
        OnPropertyChanged(nameof(HasFinishChoice));
    }

    // ---- Condition: set by hand, NM unless you say otherwise. Doesn't count as verifying the card. ----
    public IReadOnlyList<string> Conditions => ConditionList;
    public static readonly IReadOnlyList<string> ConditionList = ["Near Mint", "Lightly Played", "Moderately Played", "Heavily Played", "Damaged"];
    public static string ConditionCode(string c) => c switch
    {
        "Lightly Played" => "LP", "Moderately Played" => "MP", "Heavily Played" => "HP", "Damaged" => "DMG", _ => "NM",
    };
    [ObservableProperty] private string _condition = "Near Mint";
    [ObservableProperty] private bool _altered;
    [ObservableProperty] private bool _misprint;
    partial void OnConditionChanged(string value) => RecordIfVerified();
    partial void OnAlteredChanged(bool value) => RecordIfVerified();
    partial void OnMisprintChanged(bool value) => RecordIfVerified();
    private void RecordIfVerified() { if (Verdict != Verdict.None) _owner.Record(this, _lastRank); }

    /// <summary>The printing on screen for this card: what you picked, or the top match.</summary>
    public CardInfo? ShownCard => (Chosen ?? Top)?.Card;
    /// <summary>Price of that printing in the finish set for this card (for the price filter and sort).</summary>
    public decimal? Price => ShownCard is not { } c ? null : SelectedFinish?.Key switch
    {
        "foil" => c.PriceUsdFoil ?? c.PriceUsd,
        "etched" => c.PriceUsdEtched ?? c.PriceUsdFoil ?? c.PriceUsd,
        _ => c.PriceUsd ?? c.PriceUsdFoil,
    };

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
        foreach (var c in Candidates.ToList())
        {
            c.ImagePath = await cache.GetPathAsync(c.Card);
            c.Thumbnail = Images.SmallFromFile(c.ImagePath, 360);
        }
        try { await StraightenAsync(); }
        catch (Exception ex) { Log.Error($"Straighten {Photo}", ex); }
        try { await CheckStarAsync(); }
        catch (Exception ex) { Log.Error($"Star check {Photo}", ex); }
        try { await RunDetailCheckAsync(); }
        catch (Exception ex) { Log.Error($"Detail check {Photo}", ex); }
    }

    /// <summary>The text reader missed the ★ / • : look for the mark itself in the straightened photo.</summary>
    private bool? _markFoil;
    private async Task CheckStarAsync()
    {
        if (Result is null || Result.FoilFromCollector is not null || !_photoUnsure) return;
        var jpeg = _cardJpeg ?? Result.CardImageJpeg;
        var score = await Task.Run(() => StarMark.Score(jpeg));
        if (StarMark.Read(score) is not { } foil) return;
        _markFoil = foil;
        RefreshFinish();
        _owner.ApplyFilter();
    }

    /// <summary>Line the photo up with the top match's catalog image to get a properly square crop.</summary>
    private async Task StraightenAsync()
    {
        if (Result is null || Top?.ImagePath is not { } refPath) return;
        var r = Result;
        var jpeg = await Task.Run(() => Recognizer.RefineCrop(r, refPath));
        if (jpeg is null) return;
        _cardJpeg = jpeg;
        _fullImage = null;
        CardImage = Images.Small(jpeg, 420);
        Straightened = true;
        OnPropertyChanged(nameof(FullImage));
        _owner.SaveStraightenedCrop(this, jpeg);
    }

    internal void Choose(CandidateViewModel? chosen, Verdict? verdict = null)
    {
        foreach (var c in Candidates) c.IsChosen = c == chosen;
        VerifiedAt = DateTime.Now;
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
    public Candidate Source { get; } = candidate;
    private Bitmap? _fullImage;

    public ResultItemViewModel Owner { get; } = owner;
    public CardInfo Card { get; } = candidate.Card;
    public int Rank { get; } = rank;
    public string Name => Card.Name;
    public string SetLabel => Card.SetLabel;
    public string Rarity => Card.RarityLabel;
    public bool HasRarity => Rarity.Length > 0;
    public IBrush RarityBackground => RarityStyle.Background(Card.Rarity);
    public IBrush RarityForeground => RarityStyle.Foreground(Card.Rarity);
    public IBrush RarityBorder => RarityStyle.Border(Card.Rarity);
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
