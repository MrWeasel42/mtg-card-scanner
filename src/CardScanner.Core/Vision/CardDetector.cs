using OpenCvSharp;

namespace CardScanner.Core.Vision;

/// <summary>Result of looking for a card in a photo.</summary>
public sealed class DetectedCard : IDisposable
{
    /// <summary>The card, straightened and cropped to <see cref="CardDetector.Width"/> x <see cref="CardDetector.Height"/>.</summary>
    public required Mat Card { get; init; }
    /// <summary>Corners of the card in the original photo (TL, TR, BR, BL). Empty if no card outline was found.</summary>
    public required Point2f[] Corners { get; init; }
    public bool Found => Corners.Length == 4;
    public void Dispose() => Card.Dispose();
}

/// <summary>
/// Finds a Magic card in a photo and straightens it, so the rest of the pipeline always sees
/// a flat, upright, standard-sized card no matter how the photo was taken.
/// </summary>
public static class CardDetector
{
    // Same size as Scryfall's "normal" images, which the catalog fingerprints came from.
    public const int Width = 488;
    public const int Height = 680;
    private const double CardAspect = 63.0 / 88.0; // width / height of a real card

    public static DetectedCard Detect(Mat photo)
    {
        // Work on a smaller copy for speed; map the corners back afterwards.
        double scale = Math.Min(1.0, 1400.0 / Math.Max(photo.Width, photo.Height));
        using var small = new Mat();
        Cv2.Resize(photo, small, new Size(0, 0), scale, scale, InterpolationFlags.Area);

        var quad = FindCardQuad(small);
        if (quad is null)
        {
            // No outline found: assume the photo is already cropped to the card.
            var whole = new Mat();
            Cv2.Resize(photo, whole, new Size(Width, Height), 0, 0, InterpolationFlags.Cubic);
            return new DetectedCard { Card = whole, Corners = [] };
        }

        var corners = quad.Select(p => new Point2f((float)(p.X / scale), (float)(p.Y / scale))).ToArray();
        return new DetectedCard { Card = Warp(photo, corners), Corners = corners };
    }

    /// <summary>
    /// Card-shaped rectangles *inside* an already-straightened image, largest first. For a sleeved card
    /// the first straightening finds the sleeve's edge; the real card is one of these. A raw card's own
    /// printed frame can show up here too, so callers should try each crop and keep the best match
    /// rather than trusting these blindly.
    /// </summary>
    public static List<Point2f[]> InnerCardQuads(Mat straightened, int max = 2)
    {
        double full = straightened.Width * straightened.Height;
        var found = new List<(Point2f[] Quad, double Area)>();
        using var blurred = new Mat();
        Cv2.GaussianBlur(straightened, blurred, new Size(5, 5), 0);
        using var gray = new Mat();
        Cv2.CvtColor(blurred, gray, ColorConversionCodes.BGR2GRAY);
        var masks = EdgeMasks(blurred, gray);
        try
        {
            foreach (var mask in masks)
            {
                Cv2.FindContours(mask, out Point[][] contours, out _, RetrievalModes.List, ContourApproximationModes.ApproxSimple);
                foreach (var c in contours)
                {
                    double area = Cv2.ContourArea(c);
                    // Card inside a perfect fit is ~97% of the sleeve; inside two sleeves ~85%.
                    if (area < full * 0.78 || area > full * 0.985) continue;
                    var quad = QuadFromContour(c, area);
                    if (quad is null || TouchesEdge(quad, straightened.Width, straightened.Height) || !LooksLikeCard(quad)) continue;
                    var o = OrderCorners(quad);
                    float cx = o.Average(p => p.X), cy = o.Average(p => p.Y);
                    if (Math.Abs(cx - straightened.Width / 2f) > straightened.Width * 0.05 ||
                        Math.Abs(cy - straightened.Height / 2f) > straightened.Height * 0.05) continue;
                    // Skip near-duplicates of a rectangle we already have.
                    if (found.Any(f => Math.Abs(f.Area - area) < full * 0.01)) continue;
                    found.Add((o, area));
                }
            }
        }
        finally
        {
            foreach (var m in masks) m.Dispose();
        }
        return found.OrderByDescending(f => f.Area).Take(max).Select(f => f.Quad).ToList();
    }

    /// <summary>Straightens the area inside the four corners (TL, TR, BR, BL) into a flat card image.</summary>
    public static Mat Warp(Mat photo, Point2f[] corners)
    {
        var dst = new[] { new Point2f(0, 0), new Point2f(Width - 1, 0), new Point2f(Width - 1, Height - 1), new Point2f(0, Height - 1) };
        using var m = Cv2.GetPerspectiveTransform(corners, dst);
        var card = new Mat();
        Cv2.WarpPerspective(photo, card, m, new Size(Width, Height), InterpolationFlags.Cubic, BorderTypes.Replicate);
        return card;
    }

    private static Point2f[]? FindCardQuad(Mat img)
    {
        using var blurred = new Mat();
        Cv2.GaussianBlur(img, blurred, new Size(5, 5), 0);
        using var gray = new Mat();
        Cv2.CvtColor(blurred, gray, ColorConversionCodes.BGR2GRAY);
        double minArea = img.Width * img.Height * 0.08;

        // Try a few ways of finding edges: Canny edges, then a brightness threshold (both polarities).
        var masks = EdgeMasks(blurred, gray);
        try
        {
            foreach (var mask in masks)
            {
                Cv2.FindContours(mask, out Point[][] contours, out _, RetrievalModes.External, ContourApproximationModes.ApproxSimple);
                foreach (var c in contours.OrderByDescending(c => Cv2.ContourArea(c)))
                {
                    double area = Cv2.ContourArea(c);
                    if (area < minArea) break;
                    // The photo's own frame is roughly card-shaped too; never mistake it for the card.
                    if (area > img.Width * img.Height * 0.9) continue;
                    var quad = QuadFromContour(c, area);
                    if (quad is null || TouchesEdge(quad, img.Width, img.Height)) continue;
                    if (LooksLikeCard(quad)) return OrderCorners(quad);
                }
            }
            return null;
        }
        finally
        {
            foreach (var m in masks) m.Dispose();
        }
    }

    private static List<Mat> EdgeMasks(Mat color, Mat gray)
    {
        // Edges from each colour channel separately, so a border that differs from the
        // table only in colour (not brightness) still shows up.
        var edges = new Mat(gray.Size(), MatType.CV_8UC1, Scalar.All(0));
        Cv2.Split(color, out Mat[] channels);
        foreach (var ch in channels)
        {
            using (ch)
            using (var e = new Mat())
            {
                Cv2.Canny(ch, e, 30, 90);
                Cv2.BitwiseOr(edges, e, edges);
            }
        }
        using (var k = Cv2.GetStructuringElement(MorphShapes.Rect, new Size(5, 5)))
            Cv2.MorphologyEx(edges, edges, MorphTypes.Close, k, iterations: 2);

        var bin = new Mat();
        Cv2.Threshold(gray, bin, 0, 255, ThresholdTypes.Binary | ThresholdTypes.Otsu);

        var inv = new Mat();
        Cv2.BitwiseNot(bin, inv);
        return [edges, bin, inv];
    }

    private static Point2f[]? QuadFromContour(Point[] contour, double area)
    {
        double peri = Cv2.ArcLength(contour, true);
        foreach (var eps in new[] { 0.02, 0.03, 0.05 })
        {
            var approx = Cv2.ApproxPolyDP(contour, eps * peri, true);
            if (approx.Length == 4 && Cv2.IsContourConvex(approx))
                return approx.Select(p => new Point2f(p.X, p.Y)).ToArray();
        }
        // Rounded corners or a slightly ragged outline: fall back to the tightest rotated rectangle.
        var rect = Cv2.MinAreaRect(contour);
        if (area / Math.Max(rect.Size.Width * rect.Size.Height, 1) > 0.85)
            return rect.Points();
        return null;
    }

    private static bool TouchesEdge(Point2f[] quad, int w, int h)
    {
        const float m = 3;
        return quad.Count(p => p.X <= m || p.Y <= m || p.X >= w - 1 - m || p.Y >= h - 1 - m) >= 2;
    }

    private static bool LooksLikeCard(Point2f[] quad)
    {
        var o = OrderCorners(quad);
        double w = (Dist(o[0], o[1]) + Dist(o[3], o[2])) / 2;
        double h = (Dist(o[0], o[3]) + Dist(o[1], o[2])) / 2;
        if (w < 1 || h < 1) return false;
        double aspect = Math.Min(w, h) / Math.Max(w, h);
        return Math.Abs(aspect - CardAspect) < 0.12;
    }

    /// <summary>Orders corners TL, TR, BR, BL with the card upright (portrait).</summary>
    public static Point2f[] OrderCorners(Point2f[] pts)
    {
        var tl = pts.OrderBy(p => p.X + p.Y).First();
        var br = pts.OrderByDescending(p => p.X + p.Y).First();
        var tr = pts.OrderBy(p => p.Y - p.X).First();
        var bl = pts.OrderByDescending(p => p.Y - p.X).First();
        var o = new[] { tl, tr, br, bl };

        // If the card is lying sideways, rotate the order so the long side is vertical.
        double w = Dist(o[0], o[1]), h = Dist(o[0], o[3]);
        if (w > h) o = [o[3], o[0], o[1], o[2]];
        return o;
    }

    private static double Dist(Point2f a, Point2f b) => Math.Sqrt((a.X - b.X) * (a.X - b.X) + (a.Y - b.Y) * (a.Y - b.Y));
}
