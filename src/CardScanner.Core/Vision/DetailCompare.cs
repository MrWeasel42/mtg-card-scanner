using OpenCvSharp;

namespace CardScanner.Core.Vision;

/// <summary>
/// Close-up comparison of the photo against each candidate printing's catalog image, for printings that
/// look alike: the set symbol at the end of the type line, the bottom strip (where the "Illus." line sits,
/// "Illus." vs "Illus. ©", the © line) and the top of the text box (first words: "Counts as both…" vs
/// "{T}: Add…"). Each area is compared by its edges, and allowed to shift a little to absorb crop error.
///
/// On 57 hand-graded photos of cards with several printings it put the true printing first 55 times
/// (picture matching alone: 44), including every Revised vs Unlimited vs 4th Edition case and Shivan
/// Dragon 10E vs M10. The two misses were List reprints, which the List-symbol check handles.
/// A lead of 0.03 or more never picked the wrong printing; 0.08 or more is used to pin.
/// </summary>
public static class DetailCompare
{
    public const double ReorderMargin = 0.03, PinMargin = 0.08;
    private const int W = 976, H = 1360;

    private static readonly (string Name, Rect2d Patch, double Margin)[] Regions =
    [
        ("set symbol", new Rect2d(0.78, 0.53, 0.17, 0.09), 0.04),
        ("bottom", new Rect2d(0.04, 0.86, 0.76, 0.125), 0.035),
        ("text top", new Rect2d(0.06, 0.62, 0.88, 0.12), 0.035),
    ];

    /// <summary>Score (0..1, higher = closer) of the photo against each candidate image file.</summary>
    public static List<(string Id, double Score)> Score(byte[] photoJpeg, IEnumerable<(string Id, string ImagePath)> candidates)
    {
        var result = new List<(string, double)>();
        using var photoImg = Cv2.ImDecode(photoJpeg, ImreadModes.Color);
        if (photoImg.Empty()) return result;
        using var photo = Prep(photoImg);
        foreach (var (id, path) in candidates)
        {
            using var img = Cv2.ImRead(path, ImreadModes.Color);
            if (img.Empty()) continue;
            using var cand = Prep(img);
            result.Add((id, Regions.Average(r => RegionScore(photo, cand, r.Patch, r.Margin))));
        }
        return result;
    }

    /// <summary>Edge strength of the card at the standard size, softened so small offsets still line up.</summary>
    private static Mat Prep(Mat bgr)
    {
        using var sized = new Mat();
        Cv2.Resize(bgr, sized, new Size(W, H), 0, 0, InterpolationFlags.Area);
        using var gray8 = new Mat();
        Cv2.CvtColor(sized, gray8, ColorConversionCodes.BGR2GRAY);
        using var g = new Mat();
        gray8.ConvertTo(g, MatType.CV_32F);
        Cv2.GaussianBlur(g, g, new Size(5, 5), 0);
        using var gx = new Mat(); using var gy = new Mat();
        Cv2.Sobel(g, gx, MatType.CV_32F, 1, 0, 3);
        Cv2.Sobel(g, gy, MatType.CV_32F, 0, 1, 3);
        var mag = new Mat();
        Cv2.Magnitude(gx, gy, mag);
        Cv2.GaussianBlur(mag, mag, new Size(5, 5), 0);
        return mag;
    }

    private static double RegionScore(Mat photo, Mat cand, Rect2d p, double margin)
    {
        var patchRect = new Rect((int)(p.X * W), (int)(p.Y * H), (int)(p.Width * W), (int)(p.Height * H));
        int sx0 = Math.Max(0, (int)((p.X - margin) * W)), sy0 = Math.Max(0, (int)((p.Y - margin) * H));
        int sx1 = Math.Min(W, (int)((p.X + p.Width + margin) * W)), sy1 = Math.Min(H, (int)((p.Y + p.Height + margin) * H));
        using var patch = new Mat(cand, patchRect);
        using var area = new Mat(photo, new Rect(sx0, sy0, sx1 - sx0, sy1 - sy0));
        using var r = new Mat();
        Cv2.MatchTemplate(area, patch, r, TemplateMatchModes.CCoeffNormed);
        Cv2.MinMaxLoc(r, out _, out double max);
        return double.IsNaN(max) ? 0 : max;
    }
}
