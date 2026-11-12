using OpenCvSharp;

namespace CardScanner.Core.Vision;

/// <summary>
/// White-bordered cards (Revised, 4th, Chronicles...) photographed on a light background: the outline
/// finder often locks onto the coloured frame inside the white border, because the border barely stands
/// out from the table. If the band just outside the outline looks like white card stock, walk outward on
/// every side until it stops looking like card (texture, brightness or tint changes) and move the
/// outline out to there. Only accepted when all four sides agree on a sensible border width.
/// On 336 real photos: 10 white-bordered cards fixed, no other outline changed.
/// </summary>
public static class WhiteBorder
{
    private const double MaxGrow = 1.16;   // look up to 16% beyond the outline
    private const int Scale = 600;         // the outline's width in the working image

    public static Point2f[]? Extend(Mat img, Point2f[] quad)
    {
        var o = CardDetector.OrderCorners(quad);
        double w = (Dist(o[0], o[1]) + Dist(o[3], o[2])) / 2, h = (Dist(o[0], o[3]) + Dist(o[1], o[2])) / 2;
        if (w < 20 || h < 20) return null;
        double s = Scale / w;
        int W = (int)(w * s * MaxGrow), H = (int)(h * s * MaxGrow);

        var c = new Point2f(o.Average(p => p.X), o.Average(p => p.Y));
        var big = o.Select(p => new Point2f((float)(c.X + (p.X - c.X) * MaxGrow), (float)(c.Y + (p.Y - c.Y) * MaxGrow))).ToArray();
        using var m = Cv2.GetPerspectiveTransform(big, [new(0, 0), new(W - 1, 0), new(W - 1, H - 1), new(0, H - 1)]);
        using var warp = new Mat();
        Cv2.WarpPerspective(img, warp, m, new Size(W, H), InterpolationFlags.Area, BorderTypes.Replicate);

        using var gray8 = new Mat();
        Cv2.CvtColor(warp, gray8, ColorConversionCodes.BGR2GRAY);
        using var g = new Mat();
        gray8.ConvertTo(g, MatType.CV_32F);
        using var mu = new Mat();
        Cv2.Blur(g, mu, new Size(5, 5));
        using var g2 = new Mat();
        Cv2.Multiply(g, g, g2);
        using var mu2 = new Mat();
        Cv2.Blur(g2, mu2, new Size(5, 5));
        using var hsv = new Mat();
        Cv2.CvtColor(warp, hsv, ColorConversionCodes.BGR2HSV);
        Cv2.Split(hsv, out var hsvCh);

        g.GetArray(out float[] gv);
        mu.GetArray(out float[] muv);
        mu2.GetArray(out float[] mu2v);
        hsvCh[1].GetArray(out byte[] sat);
        foreach (var ch in hsvCh) ch.Dispose();

        double ix0 = (W - w * s) / 2, iy0 = (H - h * s) / 2, ix1 = W - ix0, iy1 = H - iy0;
        var offs = new Dictionary<string, double>();
        foreach (var side in new[] { "top", "bottom", "left", "right" })
        {
            var p = Profile(side);
            int a = 4, b = Math.Max(8, (int)(0.02 * Scale));
            if (p.Count <= b) return null;
            var ring = p.GetRange(a, b - a);
            var bV = Median(ring.Select(r => r.V)); var bT = Median(ring.Select(r => r.T)); var bS = Median(ring.Select(r => r.S));
            if (bV < 150 || bS > 60 || bT > 8) return null; // not white card stock outside the outline
            int? edge = null;
            for (int d = b; d < p.Count - 3; d++)
            {
                double nV = (p[d].V + p[d + 1].V + p[d + 2].V + p[d + 3].V) / 4;
                double nT = (p[d].T + p[d + 1].T + p[d + 2].T + p[d + 3].T) / 4;
                double nS = (p[d].S + p[d + 1].S + p[d + 2].S + p[d + 3].S) / 4;
                if (Math.Abs(nV - bV) > 18 || nT > Math.Max(2.2 * bT, bT + 4) || Math.Abs(nS - bS) > 18) { edge = d; break; }
            }
            if (edge is null) return null;
            offs[side] = edge.Value / s;
        }

        var rel = offs.ToDictionary(kv => kv.Key, kv => kv.Value / w);
        double med = Median(rel.Values);
        var odd = rel.Where(kv => kv.Value < 0.65 * med || kv.Value > 1.5 * med).Select(kv => kv.Key).ToList();
        if (odd.Count == 1) { rel[odd[0]] = med; offs[odd[0]] = med * w; }
        double lo = rel.Values.Min(), hi = rel.Values.Max();
        if (lo < 0.025 || hi > 0.09 || hi / lo >= 1.8) return null;

        // Move each side outward along the card's own axes.
        var ux = Unit(new Point2f((o[1].X - o[0].X + o[2].X - o[3].X) / 2, (o[1].Y - o[0].Y + o[2].Y - o[3].Y) / 2));
        var uy = Unit(new Point2f((o[3].X - o[0].X + o[2].X - o[1].X) / 2, (o[3].Y - o[0].Y + o[2].Y - o[1].Y) / 2));
        float t = (float)offs["top"], bt = (float)offs["bottom"], l = (float)offs["left"], r = (float)offs["right"];
        Point2f[] nq =
        [
            new(o[0].X - ux.X * l - uy.X * t, o[0].Y - ux.Y * l - uy.Y * t),
            new(o[1].X + ux.X * r - uy.X * t, o[1].Y + ux.Y * r - uy.Y * t),
            new(o[2].X + ux.X * r + uy.X * bt, o[2].Y + ux.Y * r + uy.Y * bt),
            new(o[3].X - ux.X * l + uy.X * bt, o[3].Y - ux.Y * l + uy.Y * bt),
        ];
        return CardDetector.LooksLikeCardPublic(nq) ? nq : null;

        List<(double V, double T, double S)> Profile(string side)
        {
            var res = new List<(double, double, double)>();
            bool horizontal = side is "top" or "bottom";
            int from = horizontal ? (side == "top" ? (int)iy0 - 1 : (int)iy1) : (side == "left" ? (int)ix0 - 1 : (int)ix1);
            int step = side is "top" or "left" ? -1 : 1;
            int limit = horizontal ? H : W;
            int lo2 = (int)((horizontal ? W : H) * 0.2), hi2 = (int)((horizontal ? W : H) * 0.8);
            var vs = new double[hi2 - lo2]; var ts = new double[hi2 - lo2]; var ss = new double[hi2 - lo2];
            for (int k = from; k >= 0 && k < limit; k += step)
            {
                for (int j = lo2; j < hi2; j++)
                {
                    int idx = horizontal ? k * W + j : j * W + k;
                    vs[j - lo2] = gv[idx];
                    ts[j - lo2] = Math.Sqrt(Math.Max(mu2v[idx] - muv[idx] * muv[idx], 0));
                    ss[j - lo2] = sat[idx];
                }
                res.Add((Median(vs), Median(ts), Median(ss)));
            }
            return res;
        }
    }

    private static double Median(IEnumerable<double> xs)
    {
        var a = xs.ToArray(); if (a.Length == 0) return 0;
        Array.Sort(a); int n = a.Length;
        return n % 2 == 1 ? a[n / 2] : (a[n / 2 - 1] + a[n / 2]) / 2;
    }

    private static Point2f Unit(Point2f v) { var n = (float)Math.Sqrt(v.X * v.X + v.Y * v.Y); return new(v.X / n, v.Y / n); }
    private static double Dist(Point2f a, Point2f b) => Math.Sqrt((a.X - b.X) * (a.X - b.X) + (a.Y - b.Y) * (a.Y - b.Y));
}
