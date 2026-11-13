using Avalonia;
using Avalonia.Media;
using Avalonia.Media.Imaging;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace CardScanner.App.ViewModels;

/// <summary>
/// The big side-by-side view: your photo next to one candidate printing, with a zoom on the
/// bottom of both cards (collector line, List symbol, copyright line) and arrows to flip
/// through the other candidates.
/// </summary>
public partial class CompareViewModel : ObservableObject
{
    /// <summary>The bottom slice shown by "Bottom of card": the last 30% of the card.</summary>
    private const double BottomFraction = 0.30;

    private readonly Action _close;
    private readonly Action<CompareViewModel> _advance;
    private readonly Func<CompareViewModel, Task>? _flip;
    public ResultItemViewModel Item { get; }

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(Title), nameof(Subtitle), nameof(Extra), nameof(Rarity), nameof(HasRarity), nameof(RarityBrush), nameof(Counter), nameof(RightShown), nameof(IsChosen))]
    private CandidateViewModel _candidate;

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(LeftShown), nameof(RightShown), nameof(ZoomLabel))]
    private bool _bottomOnly;

    /// <param name="advance">Called after the card is marked (or skipped): moves on to the next card
    /// still waiting in the queue, or closes the view when there's none.</param>
    public CompareViewModel(ResultItemViewModel item, CandidateViewModel candidate, Action close,
        Action<CompareViewModel> advance, bool bottomOnly = false, string queueText = "",
        Func<CompareViewModel, Task>? flip = null, Action<CompareViewModel>? back = null,
        CompareLayout layout = CompareLayout.Left, Action<CompareLayout>? saveLayout = null)
    {
        _flip = flip;
        _back = back;
        _layout = layout;
        _saveLayout = saveLayout;
        Item = item;
        _candidate = candidate;
        _close = close;
        _advance = advance;
        _bottomOnly = bottomOnly;
        QueueText = queueText;
    }

    /// <summary>e.g. "12 cards left to verify".</summary>
    public string QueueText { get; }
    public string PhotoName => Item.ScanLabel;

    // ---- Layout: info + buttons in a panel on the left (default), on the right, or across the top ----
    private readonly Action<CompareLayout>? _saveLayout;
    public IReadOnlyList<string> LayoutOptions => LayoutList;
    private static readonly IReadOnlyList<string> LayoutList = ["Panel on the left", "Panel on the right", "Tags on top"];

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(IsTopLayout), nameof(IsPanelLayout), nameof(PanelColumn), nameof(LayoutChoice))]
    private CompareLayout _layout;

    partial void OnLayoutChanged(CompareLayout value) => _saveLayout?.Invoke(value);

    public bool IsTopLayout => Layout == CompareLayout.Top;
    public bool IsPanelLayout => !IsTopLayout;
    public int PanelColumn => Layout == CompareLayout.Right ? 2 : 0;
    public string LayoutChoice
    {
        get => LayoutList[Layout switch { CompareLayout.Right => 1, CompareLayout.Top => 2, _ => 0 }];
        set => Layout = Array.IndexOf(LayoutList.ToArray(), value) switch { 1 => CompareLayout.Right, 2 => CompareLayout.Top, _ => CompareLayout.Left };
    }

    // ---- Last card: back to the previous card to fix a mis-click ----
    private readonly Action<CompareViewModel>? _back;
    public bool CanGoBack => _back is not null;

    [RelayCommand]
    private void LastCard() => _back?.Invoke(this);

    public string Title => Candidate.Name;
    public string Subtitle => Candidate.SetLabel;
    public string Extra => Candidate.Extra;
    public string Rarity => Candidate.Rarity;
    public bool HasRarity => Candidate.HasRarity;
    public Avalonia.Media.IBrush RarityBrush => Candidate.RarityBrush;
    public string Counter => $"Option {Candidate.Rank} of {Item.Candidates.Count}";
    public bool IsChosen => Candidate.IsChosen;
    public string ZoomLabel => BottomOnly ? "🔍 Show whole card" : "🔍 Zoom: bottom of card";

    public IImage? LeftShown => Shown(Item.FullImage);
    public IImage? RightShown => Shown(Candidate.FullImage);

    private IImage? Shown(Bitmap? full)
    {
        if (full is null || !BottomOnly) return full;
        var size = full.PixelSize;
        int top = (int)(size.Height * (1 - BottomFraction));
        return new CroppedBitmap(full, new PixelRect(0, top, size.Width, size.Height - top));
    }

    [RelayCommand] private void ToggleZoom() => BottomOnly = !BottomOnly;

    [RelayCommand]
    private void Next() => Move(+1);

    [RelayCommand]
    private void Previous() => Move(-1);

    private void Move(int step)
    {
        var list = Item.Candidates;
        int i = list.IndexOf(Candidate);
        Candidate = list[(i + step + list.Count) % list.Count];
    }

    [RelayCommand]
    private void PickThis()
    {
        Item.Choose(Candidate);
        _advance(this);
    }

    /// <summary>Right card, but none of the listed printings is the one.</summary>
    [RelayCommand]
    private void NameOnly()
    {
        Item.Choose(null, Verdict.NameOnly);
        _advance(this);
    }

    [RelayCommand]
    private void WrongCard()
    {
        Item.Choose(null);
        _advance(this);
    }

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(FlipLabel))]
    private bool _isFlipping;

    public string FlipLabel => IsFlipping ? "↻ Flipping…" : "↻ Flip card";
    public bool CanFlip => _flip is not null && Item.CanFlip;

    /// <summary>Card upside down? Identify it again turned around, staying in this view.</summary>
    [RelayCommand]
    private async Task Flip()
    {
        if (_flip is null || IsFlipping) return;
        IsFlipping = true;
        try { await _flip(this); }
        finally { IsFlipping = false; }
    }

    /// <summary>Leave this card unmarked and look at the next one.</summary>
    [RelayCommand]
    private void Skip() => _advance(this);

    [RelayCommand]
    private void Close() => _close();
}
