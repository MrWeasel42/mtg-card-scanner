using System.Diagnostics;
using CardScanner.Core.Catalog;
using CardScanner.Core.Vision;
using OpenCvSharp;

namespace CardScanner.Core.Recognition;

public sealed record Candidate(CardInfo Card, float Score);

public sealed class RecognitionResult
{
    public required string Source { get; init; }
    /// <summary>Name of the folder the photo came from (e.g. "raw", "single sleeve"), if any.</summary>
    public string Folder { get; set; } = "";
    public required List<Candidate> Candidates { get; init; }
    /// <summary>The straightened card as PNG bytes (for showing in the app).</summary>
    public required byte[] CardImagePng { get; init; }
    public required bool CardOutlineFound { get; init; }
    public required bool UpsideDown { get; init; }
    /// <summary>True if the best match came from a rectangle inside the outline (e.g. the card inside a sleeve).</summary>
    public bool UsedInnerOutline { get; init; }
    public required TimeSpan Elapsed { get; init; }

    public Candidate? Best => Candidates.FirstOrDefault();

    /// <summary>How far ahead the best match is of the best match with a *different* name.</summary>
    public float NameMargin
    {
        get
        {
            if (Best is null) return 0;
            var other = Candidates.FirstOrDefault(c => c.Card.Name != Best.Card.Name);
            return other is null ? 1f : Best.Score - other.Score;
        }
    }
}

/// <summary>Photo in, ranked catalog printings out.</summary>
public sealed class Recognizer : IDisposable
{
    private readonly CardCatalog _catalog;
    private readonly FingerprintIndex _index;
    private readonly Fingerprinter _fingerprinter;

    public CatalogManifest Manifest { get; }
    public CardCatalog Catalog => _catalog;

    private Recognizer(CatalogManifest manifest, CardCatalog catalog, FingerprintIndex index, Fingerprinter fp)
    {
        Manifest = manifest;
        _catalog = catalog;
        _index = index;
        _fingerprinter = fp;
    }

    public static Recognizer Load(AppPaths paths)
    {
        var manifest = CatalogManifest.TryLoad(paths.Manifest)
            ?? throw new FileNotFoundException("The card catalog hasn't been downloaded yet.");
        var index = FingerprintIndex.Load(paths.Fingerprints, paths.FingerprintIds, manifest.Model.Dim);
        var catalog = new CardCatalog(paths.Database);
        var fp = new Fingerprinter(paths.Model, manifest.Model);
        return new Recognizer(manifest, catalog, index, fp);
    }

    public RecognitionResult IdentifyFile(string path, int topK = 5)
    {
        using var photo = Cv2.ImRead(path, ImreadModes.Color); // applies phone rotation (EXIF)
        if (photo.Empty())
            throw new InvalidDataException($"Couldn't open {Path.GetFileName(path)}. If it's an iPhone HEIC photo, save it as JPG.");
        var result = Identify(photo, Path.GetFileName(path), topK);
        result.Folder = Path.GetFileName(Path.GetDirectoryName(Path.GetFullPath(path))) ?? "";
        return result;
    }

    public RecognitionResult Identify(Mat photo, string source, int topK = 5)
    {
        var sw = Stopwatch.StartNew();
        using var detected = CardDetector.Detect(photo);

        // Crops to try: the outline we found, plus any card-shaped rectangle inside it
        // (the real card, if the outline was a sleeve). Each is tried upright and upside down.
        var crops = new List<Mat> { detected.Card };
        foreach (var inner in CardDetector.InnerCardQuads(detected.Card))
            crops.Add(CardDetector.Warp(detected.Card, inner));
        var views = new List<Mat>();
        foreach (var crop in crops)
        {
            views.Add(crop);
            var flipped = new Mat();
            Cv2.Rotate(crop, flipped, RotateFlags.Rotate180);
            views.Add(flipped);
        }

        try
        {
            var vecs = _fingerprinter.EmbedBatch(views);
            var searches = vecs.Select(v => _index.Search(v, topK)).ToList();

            // Prefer the outer crop unless an inner one is clearly better (a raw card's own
            // printed frame can look like an inner rectangle; it should not win by a hair).
            int best = 0;
            for (int i = 1; i < searches.Count; i++)
            {
                float margin = i >= 2 ? 0.01f : 0f;
                if (searches[i][0].Score > searches[best][0].Score + margin) best = i;
            }
            var hits = searches[best];

            var cards = _catalog.GetMany(hits.Select(h => h.Id).ToList());
            var candidates = hits.Where(h => cards.ContainsKey(h.Id))
                                 .Select(h => new Candidate(cards[h.Id], h.Score)).ToList();

            Cv2.ImEncode(".png", views[best], out var png);
            return new RecognitionResult
            {
                Source = source,
                Candidates = candidates,
                CardImagePng = png,
                CardOutlineFound = detected.Found,
                UpsideDown = best % 2 == 1,
                UsedInnerOutline = best >= 2,
                Elapsed = sw.Elapsed,
            };
        }
        finally
        {
            // views[0] is detected.Card, disposed by its own using.
            foreach (var v in views.Skip(1)) v.Dispose();
        }
    }

    public void Dispose()
    {
        _fingerprinter.Dispose();
        _catalog.Dispose();
    }
}
