using System.Numerics;
using System.Runtime.InteropServices;

namespace CardScanner.Core.Recognition;

/// <summary>
/// All catalog fingerprints in memory. Finding a card = finding the fingerprints most similar
/// to the scanned card's (fingerprints are unit length, so similarity is a dot product).
/// </summary>
public sealed class FingerprintIndex
{
    public int Dim { get; }
    public int Count => _ids.Length;
    private readonly string[] _ids;
    private readonly float[] _vectors; // Count x Dim, row-major
    private readonly Dictionary<string, int> _rowOf;

    public FingerprintIndex(string[] ids, float[] vectors, int dim)
    {
        if (vectors.Length != ids.Length * dim)
            throw new InvalidDataException($"Fingerprint file has {vectors.Length / Math.Max(dim, 1)} rows but {ids.Length} ids");
        _ids = ids;
        _vectors = vectors;
        Dim = dim;
        _rowOf = new Dictionary<string, int>(ids.Length);
        for (int i = 0; i < ids.Length; i++) _rowOf[ids[i]] = i;
    }

    /// <summary>Loads fingerprints.bin (float16, little-endian) and fingerprint_ids.txt.</summary>
    public static FingerprintIndex Load(string binPath, string idsPath, int dim)
    {
        var ids = File.ReadAllLines(idsPath).Where(l => l.Length > 0).ToArray();
        var bytes = File.ReadAllBytes(binPath);
        var halves = MemoryMarshal.Cast<byte, Half>(bytes);
        var floats = new float[halves.Length];
        for (int i = 0; i < halves.Length; i++) floats[i] = (float)halves[i];
        return new FingerprintIndex(ids, floats, dim);
    }

    public string IdAt(int row) => _ids[row];

    public bool Contains(string id) => _rowOf.ContainsKey(id);

    /// <summary>Similarity between a query fingerprint and one catalog printing (0 if unknown).</summary>
    public float Similarity(ReadOnlySpan<float> query, string id) =>
        _rowOf.TryGetValue(id, out var row) ? Dot(query, _vectors.AsSpan(row * Dim, Dim)) : 0f;

    /// <summary>Top-k most similar catalog cards, best first.</summary>
    public List<(string Id, float Score)> Search(ReadOnlySpan<float> query, int k = 5)
    {
        if (query.Length != Dim) throw new ArgumentException($"Query has {query.Length} values, expected {Dim}");
        var q = query.ToArray();
        int n = Count;
        var scores = new float[n];
        Parallel.For(0, n, new ParallelOptions { MaxDegreeOfParallelism = Environment.ProcessorCount }, row =>
        {
            scores[row] = Dot(q, _vectors.AsSpan(row * Dim, Dim));
        });

        // Keep the k best with a small min-heap.
        var heap = new PriorityQueue<int, float>();
        for (int i = 0; i < n; i++)
        {
            if (heap.Count < k) heap.Enqueue(i, scores[i]);
            else if (scores[i] > scores[heap.Peek()]) { heap.Dequeue(); heap.Enqueue(i, scores[i]); }
        }
        var best = new List<(string, float)>(heap.Count);
        while (heap.Count > 0) { var i = heap.Dequeue(); best.Add((_ids[i], scores[i])); }
        best.Reverse();
        return best;
    }

    private static float Dot(ReadOnlySpan<float> a, ReadOnlySpan<float> b)
    {
        float sum = 0;
        int i = 0;
        if (Vector.IsHardwareAccelerated && a.Length >= Vector<float>.Count)
        {
            var acc = Vector<float>.Zero;
            var va = MemoryMarshal.Cast<float, Vector<float>>(a);
            var vb = MemoryMarshal.Cast<float, Vector<float>>(b);
            for (int j = 0; j < va.Length; j++) acc += va[j] * vb[j];
            sum = Vector.Dot(acc, Vector<float>.One);
            i = va.Length * Vector<float>.Count;
        }
        for (; i < a.Length; i++) sum += a[i] * b[i];
        return sum;
    }
}
