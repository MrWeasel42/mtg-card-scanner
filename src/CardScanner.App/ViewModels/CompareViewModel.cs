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
    public ResultItemViewModel Item { get; }

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(Title), nameof(Subtitle), nameof(Extra), nameof(Counter), nameof(RightShown), nameof(IsChosen))]
    private CandidateViewModel _candidate;

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(LeftShown), nameof(RightShown), nameof(ZoomLabel))]
    private bool _bottomOnly;

    public CompareViewModel(ResultItemViewModel item, CandidateViewModel candidate, Action close)
    {
        Item = item;
        _candidate = candidate;
        _close = close;
    }

    public string Title => Candidate.Name;
    public string Subtitle => Candidate.SetLabel;
    public string Extra => Candidate.Extra;
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
        _close();
    }

    [RelayCommand]
    private void Close() => _close();
}
