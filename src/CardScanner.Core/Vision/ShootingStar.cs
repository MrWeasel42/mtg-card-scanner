using OpenCvSharp;

namespace CardScanner.Core.Vision;

/// <summary>
/// Foils from Urza's Legacy through Scourge (1999–2003) have a "shooting star" printed at the bottom-left of
/// the text box; non-foils never do. Template cut from a real foil Seedtime.
/// Measured: real foils 0.81–0.91 (raw, sleeved, and a 400 px eBay photo), everything else in 336 photos
/// ≤ 0.53 except one modern card at 0.77, which is why it's only used for 1999–2003 printings.
/// </summary>
public static class ShootingStar
{
    public const double FoilAt = 0.70, NonFoilBelow = 0.50;
    private static readonly PrintedMark Mark = new("shooting_star.png", new Rect2d(0, 0.80, 0.45, 0.17), 25, 0.85, 0.95, 1.05, 1.15);
    public static double Score(Mat card) => Mark.Score(card);
}
