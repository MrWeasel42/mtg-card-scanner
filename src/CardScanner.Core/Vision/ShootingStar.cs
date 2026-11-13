using OpenCvSharp;

namespace CardScanner.Core.Vision;

/// <summary>
/// Foils from Urza's Legacy through Scourge (1999–2003) have a "shooting star" printed at the bottom-left of
/// the text box; non-foils never do. Looks for that exact graphic (a template cut from a real foil Seedtime)
/// on the card's structure (bright thin shapes), so the frame colour doesn't matter.
/// Measured: real foils 0.81–0.91 (including a 400 px eBay photo), everything else in 336 photos ≤ 0.53
/// except one modern card at 0.77, which is why this is only used for 1999–2003 printings.
/// </summary>
public static class ShootingStar
{
    public const double FoilAt = 0.70, NonFoilBelow = 0.50;
    private static readonly Mat Template = LoadTemplate();

    private static Mat LoadTemplate()
    {
        using var s = typeof(ShootingStar).Assembly.GetManifestResourceStream("shooting_star.png")
            ?? throw new InvalidOperationException("shooting_star.png resource missing");
        using var ms = new MemoryStream();
        s.CopyTo(ms);
        var t = Cv2.ImDecode(ms.ToArray(), ImreadModes.Grayscale);
        var f = new Mat();
        t.ConvertTo(f, MatType.CV_32F);
        t.Dispose();
        return f;
    }

    /// <summary>Best match (0..1) for the star in the bottom-left of a straightened 976x1360 card.</summary>
    public static double Score(Mat card)
    {
        int h = card.Rows, w = card.Cols;
        using var region = new Mat(card, new Rect(0, (int)(h * 0.80), (int)(w * 0.45), (int)(h * 0.97) - (int)(h * 0.80)));
        using var gray = new Mat();
        Cv2.CvtColor(region, gray, ColorConversionCodes.BGR2GRAY);
        using var k = Cv2.GetStructuringElement(MorphShapes.Ellipse, new Size(25, 25));
        using var top = new Mat();
        Cv2.MorphologyEx(gray, top, MorphTypes.TopHat, k);
        using var topF = new Mat();
        top.ConvertTo(topF, MatType.CV_32F);
        double best = -1;
        foreach (var scale in new[] { 0.85, 0.95, 1.05, 1.15 })
        {
            using var t = new Mat();
            Cv2.Resize(Template, t, new Size(0, 0), scale, scale);
            if (t.Rows >= topF.Rows || t.Cols >= topF.Cols) continue;
            using var r = new Mat();
            Cv2.MatchTemplate(topF, t, r, TemplateMatchModes.CCoeffNormed);
            Cv2.MinMaxLoc(r, out _, out double max);
            best = Math.Max(best, max);
        }
        return best;
    }
}
