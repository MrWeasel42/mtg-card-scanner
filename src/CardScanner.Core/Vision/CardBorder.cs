using OpenCvSharp;

namespace CardScanner.Core.Vision;

/// <summary>
/// Measures the colour of the card's outer border on a straightened card. Tells white-bordered
/// printings (Unlimited, Revised, 4th Edition...) from black-bordered ones (Alpha, Beta, most others),
/// which the picture fingerprint barely notices. Returns null when it isn't clear (borderless cards,
/// glare, or a crop that missed the border); those cards get no border rule at all.
///
/// Calibrated on real phone photos: of 164 cards with a known black border and 8 with a known white
/// border, none were classified as the other colour.
/// </summary>
public static class CardBorder
{
    public static string? Classify(Mat straightenedCard)
    {
        var (v, s, h) = Measure(straightenedCard);
        if (v < 70) return "black";
        if (v > 150 && s < 60) return "white";
        return null;
    }

    /// <summary>Median brightness, saturation and hue of a thin ring just inside the card edge.</summary>
    public static (double V, double S, double H) Measure(Mat card)
    {
        int w = card.Cols, h = card.Rows;
        int o = (int)(0.012 * w), i = (int)(0.035 * w);
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
