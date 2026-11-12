using OpenCvSharp;

namespace CardScanner.Core.Vision;

/// <summary>
/// Measures the colour of the card's outer border on a straightened card. Tells white-bordered
/// printings (Unlimited, Revised, 4th Edition...) from black-bordered ones (Alpha, Beta, most others),
/// which the picture fingerprint barely notices. Returns null when it isn't clear (borderless cards,
/// glare, or a crop that missed the border); those cards get no border rule at all.
///
/// Checked against 336 hand-graded phone photos (raw, single and double sleeved): 38 white and 200 black
/// borders recognised, one black border read as white, no white border read as black.
/// </summary>
public static class CardBorder
{
    public static string? Classify(Mat straightenedCard)
    {
        var (v, s, _) = Measure(straightenedCard);
        string? measured = v < 70 ? "black" : v > 150 && s < 60 ? "white" : null;
        if (measured == "white") return measured;
        // A card in a (double) sleeve is often cropped at the sleeve, whose edge looks dark. A white
        // border then shows up just inside it; a black border stays dark much further in.
        var (v1, s1, _) = Measure(straightenedCard, 0.025, 0.04);
        var (v2, s2, _) = Measure(straightenedCard, 0.04, 0.055);
        if (v1 > 140 && s1 < 60 && v2 > 150 && s2 < 60) return "white";
        return measured;
    }

    /// <summary>Median brightness, saturation and hue of a ring between two distances from the card
    /// edge (fractions of the card width). Default: a thin ring just inside the edge.</summary>
    public static (double V, double S, double H) Measure(Mat card, double from = 0.012, double to = 0.035)
    {
        int w = card.Cols, h = card.Rows;
        int o = (int)(from * w), i = (int)(to * w);
        using var mask = new Mat(h, w, MatType.CV_8UC1, Scalar.All(0));
        mask[new Rect(o, o, w - 2 * o, h - 2 * o)].SetTo(Scalar.All(255));
        mask[new Rect(i, i, w - 2 * i, h - 2 * i)].SetTo(Scalar.All(0));
        using var hsv = new Mat();
        Cv2.CvtColor(card, hsv, ColorConversionCodes.BGR2HSV);
        hsv.GetArray(out Vec3b[] px);
        mask.GetArray(out byte[] m);
        var hs = new List<byte>(); var ss = new List<byte>(); var vs = new List<byte>();
        for (int k = 0; k < m.Length; k++)
        {
            if (m[k] == 0) continue;
            hs.Add(px[k].Item0); ss.Add(px[k].Item1); vs.Add(px[k].Item2);
        }
        return (Median(vs), Median(ss), Median(hs));
    }

    private static double Median(List<byte> xs)
    {
        if (xs.Count == 0) return 0;
        xs.Sort();
        int n = xs.Count;
        return n % 2 == 1 ? xs[n / 2] : (xs[n / 2 - 1] + xs[n / 2]) / 2.0;
    }
}
