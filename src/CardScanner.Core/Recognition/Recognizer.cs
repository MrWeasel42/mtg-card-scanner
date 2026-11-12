using System.Diagnostics;
using CardScanner.Core.Catalog;
using CardScanner.Core.Vision;
using OpenCvSharp;

namespace CardScanner.Core.Recognition;

public sealed record Candidate(CardInfo Card, float Score);

public sealed class RecognitionResult
{
    public required string Source { get; init; }
    public required List<Candidate> Candidates { get; init; }
    /// <summary>The straightened card as PNG bytes (for showing in the app).</summary>
    public required byte[] CardImagePng { get; init; }
    public required bool CardOutlineFound { get; init; }
    public required bool UpsideDown { get; init; }
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
        return Identify(photo, Path.GetFileName(path), topK);
    }

    public RecognitionResult Identify(Mat photo, string source, int topK = 5)
    {
        var sw = Stopwatch.StartNew();
        using var detected = CardDetector.Detect(photo);

        // The card might be upside down: try both ways and keep whichever matches better.
        using var flipped = new Mat();
        Cv2.Rotate(detected.Card, flipped, RotateFlags.Rotate180);
        var vecs = _fingerprinter.EmbedBatch([detected.Card, flipped]);
        var upright = _index.Search(vecs[0], topK);
        var rotated = _index.Search(vecs[1], topK);
        bool upsideDown = rotated[0].Score > upright[0].Score;
        var hits = upsideDown ? rotated : upright;

        var cards = _catalog.GetMany(hits.Select(h => h.Id).ToList());
        var candidates = hits.Where(h => cards.ContainsKey(h.Id))
                             .Select(h => new Candidate(cards[h.Id], h.Score)).ToList();

        Cv2.ImEncode(".png", upsideDown ? flipped : detected.Card, out var png);
        return new RecognitionResult
        {
            Source = source,
            Candidates = candidates,
            CardImagePng = png,
            CardOutlineFound = detected.Found,
            UpsideDown = upsideDown,
            Elapsed = sw.Elapsed,
        };
    }

    public void Dispose()
    {
        _fingerprinter.Dispose();
        _catalog.Dispose();
    }
}
