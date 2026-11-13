using OpenCvSharp;

namespace CardScanner.Core.Vision;

/// <summary>
/// Straightens the card by lining the photo up against the catalog image of the matched card (like laying
/// one transparency over another), instead of trusting four corners guessed from the photo alone. Rounded
/// corners, sleeves and glare can push a corner off by a few pixels and turn the card into a trapezoid;
/// the printed card itself can't lie about where its frame and text are.
///
/// Measured on 332 photos from the v0.2.8 test (how far the final crop's corners are from the true card
/// edges): one pass limited to 8% left 47 crops more than 2% off, mostly double-sleeved cards it refused
/// to move; two passes allowing 15% leave 9. When it can't lock on it gives up and the normal crop stays.
/// </summary>
public static class CropRefine
{
    private const int Wd = 244, Hd = 340;

    /// <summary>First pass may move a corner up to this far (fraction of card width): double sleeves
    /// often put the first outline on the outer sleeve, 8-11% off.</summary>
    private const double MaxMove = 0.15, PolishMove = 0.05;
    /// <summary>Moves over 8% must also line up well (ECC correlation), so a bad lock can't distort the card.</summary>
    private const double BigMove = 0.08, BigMoveMinFit = 0.5;

    /// <summary>New corners (photo coordinates, TL TR BR BL), or null to keep the original ones.
    /// Two passes: a coarse lock that may move far, then a polish from the new crop.</summary>
    public static Point2f[]? Refine(Mat photo, Point2f[] corners, Mat reference, bool upsideDown)
    {
        if (corners.Length != 4) return null;
        using var refSmall = new Mat();
        Cv2.Resize(reference, refSmall, new Size(Wd, Hd), 0, 0, InterpolationFlags.Area);
        if (upsideDown) Cv2.Rotate(refSmall, refSmall, RotateFlags.Rotate180);
        using var b = Gray(refSmall);
        var first = Pass(photo, corners, b, MaxMove);
        if (first is null) return null;
        return Pass(photo, first, b, PolishMove) ?? first;
    }

    private static Point2f[]? Pass(Mat photo, Point2f[] corners, Mat refGray, double maxMove)
    {
        using var card = CardDetector.Warp(photo, corners, Wd, Hd);
        using var a = Gray(card);
        using var warp = Mat.Eye(3, 3, MatType.CV_32F).ToMat();
        double fit;
        try
        {
            fit = Cv2.FindTransformECC(refGray, a, warp, MotionTypes.Homography,
                new TermCriteria(CriteriaTypes.Eps | CriteriaTypes.Count, 200, 1e-5), null, 5);
        }
        catch (OpenCVException) { return null; }   // didn't converge

        Point2f[] frame = [new(0, 0), new(Wd - 1, 0), new(Wd - 1, Hd - 1), new(0, Hd - 1)];
        var inCard = Cv2.PerspectiveTransform(frame, warp);
        double move = inCard.Zip(frame).Max(p => Math.Max(Math.Abs(p.First.X - p.Second.X), Math.Abs(p.First.Y - p.Second.Y))) / Wd;
        // Moved too far from the starting crop, or a big move that doesn't line up well: don't trust it.
        if (move > maxMove || move > BigMove && fit < BigMoveMinFit) return null;
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
