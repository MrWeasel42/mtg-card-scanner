using OpenCvSharp;

namespace CardScanner.Core.Vision;

/// <summary>
/// Looks for the tiny ★ (foil) printed between the set code and the language on modern cards ("LTR ★ EN"),
/// when the text reader dropped it. Matches drawn star and dot shapes against the bottom-left corner.
///
/// Only used to say "foil": on the 0.2.8 test crops a clear star (score ≥ 0.90, beating the dot shape by
/// 0.08) was never wrong, and it found 2 of the 3 foils the text reader missed. The dot shape is too easy to
/// match by accident (it scored high on 2 star cards), so a dot is not taken as proof of non-foil.
/// </summary>
public static class StarMark
{
    public const double FoilAt = 0.90, FoilLead = 0.08;
    private const int W = 976, H = 1360;
    private static readonly Mat[] Stars = new[] { 11, 13, 15, 17, 19 }.Select(Star).ToArray();
    private static readonly Mat[] Dots = new[] { 5, 6, 7, 9 }.Select(Dot).ToArray();

    /// <summary>(star, dot) shape scores in the collector-line area of a straightened card.</summary>
    public static (double Star, double Dot) Score(byte[] cardJpeg)
    {
        using var img = Cv2.ImDecode(cardJpeg, ImreadModes.Grayscale);
        if (img.Empty()) return (0, 0);
        using var sized = new Mat();
        Cv2.Resize(img, sized, new Size(W, H), 0, 0, InterpolationFlags.Area);
        using var roi = new Mat(sized, new Rect(20, 1250, 400, 110));
        using var f = new Mat();
        roi.ConvertTo(f, MatType.CV_32F);
        using var k = Cv2.GetStructuringElement(MorphShapes.Ellipse, new Size(15, 15));
        (double, double) best = (0, 0);
        foreach (var op in new[] { MorphTypes.TopHat, MorphTypes.BlackHat })   // light-on-dark and dark-on-light text
        {
            using var e = new Mat();
            Cv2.MorphologyEx(f, e, op, k);
            double s = Stars.Max(t => Best(e, t)), d = Dots.Max(t => Best(e, t));
            if (s > best.Item1) best = (s, d);
        }
        return best;
    }

    public static bool LooksFoil((double Star, double Dot) s) => s.Star >= FoilAt && s.Star - s.Dot >= FoilLead;

    private static double Best(Mat image, Mat template)
    {
        using var r = new Mat();
        Cv2.MatchTemplate(image, template, r, TemplateMatchModes.CCoeffNormed);
        Cv2.MinMaxLoc(r, out _, out double max);
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
