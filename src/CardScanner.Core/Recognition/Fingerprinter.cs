using CardScanner.Core.Catalog;
using Microsoft.ML.OnnxRuntime;
using Microsoft.ML.OnnxRuntime.Tensors;
using OpenCvSharp;

namespace CardScanner.Core.Recognition;

/// <summary>
/// Runs the AI model on a straightened card image and returns its fingerprint.
/// Preprocessing must match catalog-builder/builder/fingerprints.py exactly:
/// RGB, bicubic resize to Width x Height, /255, (x - mean) / std, CHW.
/// </summary>
public sealed class Fingerprinter : IDisposable
{
    private readonly InferenceSession _session;
    private readonly ModelInfo _info;

    public int Dim => _info.Dim;

    public Fingerprinter(string modelPath, ModelInfo info)
    {
        _info = info;
        var opts = new SessionOptions
        {
            GraphOptimizationLevel = GraphOptimizationLevel.ORT_ENABLE_ALL,
            IntraOpNumThreads = Math.Max(1, Environment.ProcessorCount / 2),
        };
        _session = new InferenceSession(modelPath, opts);
    }

    public float[] Embed(Mat card) => EmbedBatch([card])[0];

    public float[][] EmbedBatch(IReadOnlyList<Mat> cards)
    {
        int w = _info.Width, h = _info.Height;
        var tensor = new DenseTensor<float>([cards.Count, 3, h, w]);
        for (int n = 0; n < cards.Count; n++)
            Fill(tensor, n, cards[n], w, h);

        using var results = _session.Run([NamedOnnxValue.CreateFromTensor(_info.InputName, tensor)]);
        var output = results.First().AsTensor<float>();
        var vecs = new float[cards.Count][];
        for (int n = 0; n < cards.Count; n++)
        {
            var v = new float[Dim];
            for (int d = 0; d < Dim; d++) v[d] = output[n, d];
            vecs[n] = v;
        }
        return vecs;
    }

    private void Fill(DenseTensor<float> tensor, int n, Mat card, int w, int h)
    {
        using var resized = new Mat();
        Cv2.Resize(card, resized, new Size(w, h), 0, 0, InterpolationFlags.Cubic);
        resized.GetArray(out Vec3b[] px); // OpenCV pixels are B, G, R
        var mean = _info.Mean;
        var std = _info.Std;
        for (int y = 0; y < h; y++)
        {
            for (int x = 0; x < w; x++)
            {
                var p = px[y * w + x];
                tensor[n, 0, y, x] = (p.Item2 / 255f - mean[0]) / std[0]; // R
                tensor[n, 1, y, x] = (p.Item1 / 255f - mean[1]) / std[1]; // G
                tensor[n, 2, y, x] = (p.Item0 / 255f - mean[2]) / std[2]; // B
            }
        }
    }

    public void Dispose() => _session.Dispose();
}
