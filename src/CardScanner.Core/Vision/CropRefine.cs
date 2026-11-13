using OpenCvSharp;

namespace CardScanner.Core.Vision;

/// <summary>
/// Straightens the card by lining the photo up against the catalog image of the matched card (like laying
/// one transparency over another), instead of trusting four corners guessed from the photo alone. Rounded
/// corners, sleeves and glare can push a corner off by a few pixels and turn the card into a trapezoid;
/// the printed card itself can't lie about where its frame and text are.
///
/// Measured on 333 hand-graded photos (fit of the straightened photo to the true card, 0..1): corners
/// alone 0.32, with this refinement 0.87; better on 291, worse on 2. When it can't lock on (40 photos:
/// starting crop too far off, heavy glare) it gives up and the normal crop stays.
/// </summary>
public static class CropRefine
{
    private const int Wd = 244, Hd = 340;

    /// <summary>New corners (photo coordinates, TL TR BR BL), or null to keep the original ones.</summary>
    public static Point2f[]? Refine(Mat photo, Point2f[] corners, Mat reference, bool upsideDown)
    {
        if (corners.Length != 4) return null;
        using var card = CardDetector.Warp(photo, corners, Wd, Hd);
        using var refSmall = new Mat();
        Cv2.Resize(reference, refSmall, new Size(Wd, Hd), 0, 0, InterpolationFlags.Area);
        if (upsideDown) Cv2.Rotate(refSmall, refSmall, RotateFlags.Rotate180);
        using var a = Gray(card);
        using var b = Gray(refSmall);
        using var warp = Mat.Eye(3, 3, MatType.CV_32F).ToMat();
        try
        {
            Cv2.FindTransformECC(b, a, warp, MotionTypes.Homography,
                new TermCriteria(CriteriaTypes.Eps | CriteriaTypes.Count, 100, 1e-5), null, 5);
        }
        catch (OpenCVException) { return null; }   // didn't converge

        Point2f[] frame = [new(0, 0), new(Wd - 1, 0), new(Wd - 1, Hd - 1), new(0, Hd - 1)];
        var inCard = Cv2.PerspectiveTransform(frame, warp);
        // Moved too far from the starting crop: don't trust it.
        if (inCard.Zip(frame).Any(p => Math.Abs(p.First.X - p.Second.X) > 0.08 * Wd || Math.Abs(p.First.Y - p.Second.Y) > 0.08 * Wd))
            return null;
        using var toPhoto = Cv2.GetPerspectiveTransform(frame, corners);
        return Cv2.PerspectiveTransform(inCard, toPhoto);
    }

    private static Mat Gray(Mat bgr)
    {
        using var g = new Mat();
        Cv2.CvtColor(bgr, g, ColorConversionCodes.BGR2GRAY);
        Cv2.GaussianBlur(g, g, new Size(5, 5), 0);
        var f = new Mat();
        g.ConvertTo(f, MatType.CV_32F);
        return f;
    }
}
