using OpenCvSharp;

namespace CardScanner.Core.Vision;

/// <summary>
/// Reads the tiny ★ (foil) or • (non-foil) printed between the set code and the language on modern cards
/// ("LTR ★ EN"), when the text reader dropped it. On a straightened card the mark sits in the same small
/// spot every time, so star and dot shapes are only matched there.
///
/// Measured on the 0.2.9 test crops: 172 cards whose mark the text reader did get (68 ★, 104 •) all came
/// out right or unsure (one ★ unsure, none wrong), and 30 of the 50 "couldn't tell" cards were settled, all
/// correctly. The other 20 are older or Mystery Booster frames that don't print a mark at all.
/// </summary>
public static class StarMark
{
    public const double FoilAt = 0.88, FoilLead = 0.08, NonFoilAt = 0.86, NonFoilLead = 0.04;
    private const int W = 976, H = 1360;
    // Collector-line area, and inside it where the separator's centre lands.
    private static readonly Rect Area = new(20, 1250, 400, 110);
    private const int X0 = 80, X1 = 125, Y0 = 45, Y1 = 75;
    private static readonly Mat[] Stars = new[] { 11, 13, 15, 17, 19 }.Select(Star).ToArray();
    private static readonly Mat[] Dots = new[] { 5, 6, 7, 9 }.Select(Dot).ToArray();

    /// <summary>(star, dot) shape scores at the separator position of a straightened card.</summary>
    public static (double Star, double Dot) Score(byte[] cardJpeg)
    {
        using var img = Cv2.ImDecode(cardJpeg, ImreadModes.Grayscale);
        if (img.Empty()) return (0, 0);
        using var sized = new Mat();
        Cv2.Resize(img, sized, new Size(W, H), 0, 0, InterpolationFlags.Area);
        using var roi = new Mat(sized, Area);
        using var f = new Mat();
        roi.ConvertTo(f, MatType.CV_32F);
        using var k = Cv2.GetStructuringElement(MorphShapes.Ellipse, new Size(15, 15));
        using var e = new Mat();
        Cv2.MorphologyEx(f, e, MorphTypes.TopHat, k);   // light text on the dark collector line
        return (Stars.Max(t => Best(e, t)), Dots.Max(t => Best(e, t)));
    }

    /// <summary>true = ★ (foil), false = • (non-foil), null = can't tell.</summary>
    public static bool? Read((double Star, double Dot) s) =>
        s.Star >= FoilAt && s.Star - s.Dot >= FoilLead ? true
        : s.Dot >= NonFoilAt && s.Dot - s.Star >= NonFoilLead ? false
        : null;

    /// <summary>Best match whose centre falls in the separator window.</summary>
    private static double Best(Mat image, Mat template)
    {
        using var r = new Mat();
        Cv2.MatchTemplate(image, template, r, TemplateMatchModes.CCoeffNormed);
        int x0 = Math.Max(0, X0 - template.Cols / 2), y0 = Math.Max(0, Y0 - template.Rows / 2);
        int x1 = Math.Min(r.Cols - 1, X1 - template.Cols / 2), y1 = Math.Min(r.Rows - 1, Y1 - template.Rows / 2);
        if (x1 < x0 || y1 < y0) return 0;
        using var win = new Mat(r, new Rect(x0, y0, x1 - x0 + 1, y1 - y0 + 1));
        Cv2.MinMaxLoc(win, out _, out double max);
        return max;
    }

    private static Mat Star(int size)
    {
        int n = size + 6; double c = n / 2.0, R = size / 2.0, r = R * 0.42;
        var pts = Enumerable.Range(0, 10).Select(i =>
        {
            double rad = i % 2 == 0 ? R : r, a = i * Math.PI / 5;
            return new Point((int)Math.Round((c + rad * Math.Sin(a)) * 4), (int)Math.Round((c - rad * Math.Cos(a)) * 4));
        }).ToArray();
        var t = new Mat(n, n, MatType.CV_32F, Scalar.All(0));
        Cv2.FillPoly(t, [pts], Scalar.All(1), LineTypes.AntiAlias, 2);
        Cv2.GaussianBlur(t, t, new Size(3, 3), 0);
        return t;
    }

    private static Mat Dot(int size)
    {
        int n = size + 8;
        var t = new Mat(n, n, MatType.CV_32F, Scalar.All(0));
        Cv2.Circle(t, new Point(n / 2, n / 2), size / 2, Scalar.All(1), -1);
        Cv2.GaussianBlur(t, t, new Size(3, 3), 0);
        return t;
    }
}
