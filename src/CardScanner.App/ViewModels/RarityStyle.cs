using Avalonia;
using Avalonia.Media;

namespace CardScanner.App.ViewModels;

/// <summary>Rarity badges in the classic set-symbol colors: black common, silver uncommon, gold rare,
/// red-orange mythic, purple special / timeshifted / bonus.</summary>
public static class RarityStyle
{
    private static IBrush Grad(string a, string b) => new LinearGradientBrush
    {
        StartPoint = new RelativePoint(0, 0, RelativeUnit.Relative),
        EndPoint = new RelativePoint(0, 1, RelativeUnit.Relative),
        GradientStops = { new GradientStop(Color.Parse(a), 0), new GradientStop(Color.Parse(b), 1) },
    };

    public static IBrush Background(string rarity) => rarity switch
    {
        "uncommon" => Grad("#E4ECF2", "#8B9AA8"),
        "rare" => Grad("#F4DD8D", "#B08A2E"),
        "mythic" => Grad("#F9A03F", "#C8321A"),
        "special" or "bonus" => Grad("#A57BE0", "#5B2A9E"),
        _ => Grad("#2A2A2A", "#050505"),
    };

    public static IBrush Foreground(string rarity) => new SolidColorBrush(Color.Parse(rarity switch
    {
        "uncommon" or "rare" => "#111111",
        _ => "#FFFFFF",
    }));

    /// <summary>Thin light edge so the black common badge still shows on the dark background.</summary>
    public static IBrush Border(string rarity) => new SolidColorBrush(Color.Parse(rarity is "common" or "" ? "#D1D5DB" : "#00000000"));

    public static int Order(string rarity) => rarity switch
    {
        "mythic" => 0, "special" or "bonus" => 1, "rare" => 2, "uncommon" => 3, "common" => 4, _ => 5,
    };
}
