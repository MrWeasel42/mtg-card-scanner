using Microsoft.ML.OnnxRuntime;
using Microsoft.ML.OnnxRuntime.Tensors;
using OpenCvSharp;

namespace CardScanner.Core.Ocr;

/// <summary>One line of text found in an image.</summary>
public sealed record TextLine(string Text, float Confidence, Point2f[] Box)
{
    public float Top => Box.Min(p => p.Y);
    public float Left => Box.Min(p => p.X);
}

/// <summary>
/// Reads printed text (card names, collector lines) with the PaddleOCR PP-OCRv3 models.
/// Step 1 finds text lines (a "DB" text detector), step 2 reads each line (a CTC recognizer).
/// Mirrors the reference Python implementation used to validate it on real card photos.
/// </summary>
public sealed class TextReader : IDisposable
{
    private static readonly float[] Mean = [0.485f, 0.456f, 0.406f];
    private static readonly float[] Std = [0.229f, 0.224f, 0.225f];

    private readonly InferenceSession _det;
    private readonly InferenceSession _rec;
    private readonly string _detInput, _recInput;
    private readonly string[] _chars;

    public TextReader(string modelDir)
    {
        var opts = new SessionOptions
        {
            GraphOptimizationLevel = GraphOptimizationLevel.ORT_ENABLE_ALL,
            IntraOpNumThreads = Math.Max(1, Environment.ProcessorCount / 2),
        };
        _det = new InferenceSession(Path.Combine(modelDir, "text_det.onnx"), opts);
        _rec = new InferenceSession(Path.Combine(modelDir, "text_rec.onnx"), opts);
        _detInput = _det.InputMetadata.Keys.First();
        _recInput = _rec.InputMetadata.Keys.First();
        var dict = _rec.ModelMetadata.CustomMetadataMap["character"];
        _chars = [.. dict.Split('\n').Select(c => c.TrimEnd('\r')), " "];
    }

    /// <summary>The folder next to the app that holds the OCR models.</summary>
    public static string DefaultModelDir => Path.Combine(AppContext.BaseDirectory, "OcrModels");

    /// <summary>Finds and reads every text line in a BGR image, top to bottom.</summary>
    public List<TextLine> Read(Mat bgr, float minConfidence = 0.5f)
    {
        var lines = new List<TextLine>();
        foreach (var box in Detect(bgr))
        {
            using var crop = Crop(bgr, box);
            var (text, conf) = Recognize(crop);
            if (text.Length > 0 && conf >= minConfidence) lines.Add(new TextLine(text, conf, box));
        }
        return lines;
    }

    // ---------------- Detection ----------------

    public List<Point2f[]> Detect(Mat bgr, int limit = 736, float thresh = 0.3f, float boxThresh = 0.5f, float unclip = 1.6f)
    {
        int h = bgr.Rows, w = bgr.Cols;
        double r = Math.Min(h, w) < limit ? (double)limit / Math.Min(h, w) : 1.0;
        int rh = Math.Max(32, (int)Math.Round(h * r / 32) * 32);
        int rw = Math.Max(32, (int)Math.Round(w * r / 32) * 32);

        using var resized = new Mat();
        Cv2.Resize(bgr, resized, new Size(rw, rh));
        var input = new DenseTensor<float>([1, 3, rh, rw]);
        resized.GetArray(out Vec3b[] px);
        for (int y = 0; y < rh; y++)
            for (int x = 0; x < rw; x++)
            {
                var p = px[y * rw + x];
                // Same channel order as the reference (image as loaded, i.e. B,G,R).
                input[0, 0, y, x] = (p.Item0 / 255f - Mean[0]) / Std[0];
                input[0, 1, y, x] = (p.Item1 / 255f - Mean[1]) / Std[1];
                input[0, 2, y, x] = (p.Item2 / 255f - Mean[2]) / Std[2];
            }

        using var results = _det.Run([NamedOnnxValue.CreateFromTensor(_detInput, input)]);
        var outT = results.First().AsTensor<float>();
        using var pred = new Mat(rh, rw, MatType.CV_32FC1);
        var buf = new float[rh * rw];
        int k = 0;
        for (int y = 0; y < rh; y++)
            for (int x = 0; x < rw; x++)
                buf[k++] = outT[0, 0, y, x];
        pred.SetArray(buf);

        using var bitmap = new Mat();
        Cv2.Threshold(pred, bitmap, thresh, 255, ThresholdTypes.Binary);
        bitmap.ConvertTo(bitmap, MatType.CV_8UC1);
        using (var kernel = Mat.Ones(2, 2, MatType.CV_8UC1).ToMat())
            Cv2.Dilate(bitmap, bitmap, kernel);
        Cv2.FindContours(bitmap, out Point[][] contours, out _, RetrievalModes.List, ContourApproximationModes.ApproxSimple);

        var boxes = new List<Point2f[]>();
        foreach (var c in contours.Take(1000))
        {
            var rect = Cv2.MinAreaRect(c);
            if (Math.Min(rect.Size.Width, rect.Size.Height) < 3) continue;
            if (BoxScore(pred, rect.Points(), rw, rh) < boxThresh) continue;

            float bw = rect.Size.Width, bh = rect.Size.Height;
            float d = bw * bh * unclip / (2 * (bw + bh));
            var big = new RotatedRect(rect.Center, new Size2f(bw + 2 * d, bh + 2 * d), rect.Angle);
            if (Math.Min(big.Size.Width, big.Size.Height) < 5) continue;

            var pts = big.Points().Select(p => new Point2f(
                (float)Math.Clamp(Math.Round(p.X / rw * w), 0, w - 1),
                (float)Math.Clamp(Math.Round(p.Y / rh * h), 0, h - 1))).ToArray();
            var o = Order(pts);
            if (Dist(o[0], o[1]) > 3 && Dist(o[0], o[3]) > 3) boxes.Add(o);
        }
        boxes.Sort((a, b) => a[0].Y != b[0].Y ? a[0].Y.CompareTo(b[0].Y) : a[0].X.CompareTo(b[0].X));
        return boxes;
    }

    private static double BoxScore(Mat pred, Point2f[] pts, int w, int h)
    {
        int x0 = Math.Clamp((int)Math.Floor(pts.Min(p => p.X)), 0, w - 1);
        int y0 = Math.Clamp((int)Math.Floor(pts.Min(p => p.Y)), 0, h - 1);
        int x1 = Math.Clamp((int)Math.Ceiling(pts.Max(p => p.X)), 0, w - 1);
        int y1 = Math.Clamp((int)Math.Ceiling(pts.Max(p => p.Y)), 0, h - 1);
        using var mask = new Mat(y1 - y0 + 1, x1 - x0 + 1, MatType.CV_8UC1, Scalar.All(0));
        var poly = pts.Select(p => new Point((int)(p.X - x0), (int)(p.Y - y0))).ToArray();
        Cv2.FillPoly(mask, [poly], Scalar.All(1));
        using var roi = new Mat(pred, new Rect(x0, y0, x1 - x0 + 1, y1 - y0 + 1));
        return Cv2.Mean(roi, mask).Val0;
    }

    private static Point2f[] Order(Point2f[] p)
    {
        var xs = p.OrderBy(q => q.X).ToArray();
        var left = xs.Take(2).OrderBy(q => q.Y).ToArray();
        var right = xs.Skip(2).OrderBy(q => q.Y).ToArray();
        return [left[0], right[0], right[1], left[1]];
    }

    private static double Dist(Point2f a, Point2f b) => Math.Sqrt((a.X - b.X) * (a.X - b.X) + (a.Y - b.Y) * (a.Y - b.Y));

    // ---------------- Recognition ----------------

    private static Mat Crop(Mat img, Point2f[] b)
    {
        int w = (int)Math.Max(Dist(b[0], b[1]), Dist(b[2], b[3]));
        int h = (int)Math.Max(Dist(b[0], b[3]), Dist(b[1], b[2]));
        w = Math.Max(w, 1); h = Math.Max(h, 1);
        var dst = new[] { new Point2f(0, 0), new Point2f(w, 0), new Point2f(w, h), new Point2f(0, h) };
        using var m = Cv2.GetPerspectiveTransform(b, dst);
        var outImg = new Mat();
        Cv2.WarpPerspective(img, outImg, m, new Size(w, h), InterpolationFlags.Cubic, BorderTypes.Replicate);
        if (h >= 1.5 * w) Cv2.Rotate(outImg, outImg, RotateFlags.Rotate90Counterclockwise);
        return outImg;
    }

    public (string Text, float Confidence) Recognize(Mat line)
    {
        int h = line.Rows, w = line.Cols;
        double ratio = (double)w / Math.Max(h, 1);
        int imgW = Math.Max(320, (int)Math.Ceiling(48 * ratio));
        int rw = Math.Min(imgW, (int)Math.Ceiling(48 * ratio));
        using var resized = new Mat();
        Cv2.Resize(line, resized, new Size(rw, 48));
        resized.GetArray(out Vec3b[] px);

        var input = new DenseTensor<float>([1, 3, 48, imgW]); // zero-padded on the right
        for (int y = 0; y < 48; y++)
            for (int x = 0; x < rw; x++)
            {
                var p = px[y * rw + x];
                input[0, 0, y, x] = (p.Item0 / 255f - 0.5f) / 0.5f;
                input[0, 1, y, x] = (p.Item1 / 255f - 0.5f) / 0.5f;
                input[0, 2, y, x] = (p.Item2 / 255f - 0.5f) / 0.5f;
            }

        using var results = _rec.Run([NamedOnnxValue.CreateFromTensor(_recInput, input)]);
        var probs = results.First().AsTensor<float>(); // [1, T, classes]
        int steps = probs.Dimensions[1], classes = probs.Dimensions[2];
        var sb = new System.Text.StringBuilder();
        float confSum = 0; int confN = 0, prev = -1;
        for (int t = 0; t < steps; t++)
        {
            int best = 0; float bestP = float.MinValue;
            for (int c = 0; c < classes; c++)
            {
                float v = probs[0, t, c];
                if (v > bestP) { bestP = v; best = c; }
            }
            if (best != 0 && best != prev && best - 1 < _chars.Length)
            {
                sb.Append(_chars[best - 1]);
                confSum += bestP; confN++;
            }
            prev = best;
        }
        return (sb.ToString(), confN > 0 ? confSum / confN : 0f);
    }

    public void Dispose()
    {
        _det.Dispose();
        _rec.Dispose();
    }
}
