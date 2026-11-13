using OpenCvSharp;

namespace CardScanner.Core.Vision;

/// <summary>
/// Finds a small printed graphic (the foil shooting star, the List symbol...) in one area of a straightened
/// 976x1360 card. Matching is done on the card's bright thin structure (a top-hat filter), so the colour
/// of the frame underneath doesn't matter. Templates were cut from real photos.
/// </summary>
public sealed class PrintedMark
{
    private readonly Mat _template;
    private readonly Rect2d _area;      // fractions of the card
    private readonly int _kernel;
    private readonly double[] _scales;

    public PrintedMark(string resource, Rect2d area, int kernel, params double[] scales)
    {
        _area = area; _kernel = kernel; _scales = scales;
        using var s = typeof(PrintedMark).Assembly.GetManifestResourceStream(resource)
            ?? throw new InvalidOperationException($"{resource} resource missing");
        using var ms = new MemoryStream();
        s.CopyTo(ms);
        using var t = Cv2.ImDecode(ms.ToArray(), ImreadModes.Grayscale);
        _template = new Mat();
        t.ConvertTo(_template, MatType.CV_32F);
    }

    /// <summary>Best match, 0..1.</summary>
    public double Score(Mat card)
    {
        int h = card.Rows, w = card.Cols;
        var r = new Rect((int)(w * _area.X), (int)(h * _area.Y), (int)(w * _area.Width), (int)(h * _area.Height));
        r = r.Intersect(new Rect(0, 0, w, h));
        using var region = new Mat(card, r);
        using var gray = new Mat();
        Cv2.CvtColor(region, gray, ColorConversionCodes.BGR2GRAY);
        using var k = Cv2.GetStructuringElement(MorphShapes.Ellipse, new Size(_kernel, _kernel));
        using var top = new Mat();
        Cv2.MorphologyEx(gray, top, MorphTypes.TopHat, k);
        using var topF = new Mat();
        top.ConvertTo(topF, MatType.CV_32F);
        double best = -1;
        foreach (var scale in _scales)
        {
            using var t = new Mat();
            Cv2.Resize(_template, t, new Size(0, 0), scale, scale);
            if (t.Rows >= topF.Rows || t.Cols >= topF.Cols) continue;
            using var res = new Mat();
            Cv2.MatchTemplate(topF, t, res, TemplateMatchModes.CCoeffNormed);
            Cv2.MinMaxLoc(res, out _, out double max);
            if (!double.IsNaN(max)) best = Math.Max(best, max);
        }
        return best;
    }
}

/// <summary>
/// The List symbol (a small planeswalker mark) printed bottom-left on The List reprints, next to the
/// collector line (modern frames) or in the black border (old frames). Measured on 336 photos: the 4 List
/// cards scored 0.77–1.0, every other card 0.65 or less.
/// </summary>
public static class ListSymbol
{
    public const double SeenAt = 0.72, AbsentBelow = 0.60;
    private static readonly PrintedMark Mark = new("list_symbol.png", new Rect2d(0, 0.88, 0.14, 0.12), 31, 0.8, 0.9, 1.0, 1.1, 1.25);
    public static double Score(Mat card) => Mark.Score(card);
}
