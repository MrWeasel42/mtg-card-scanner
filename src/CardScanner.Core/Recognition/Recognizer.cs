using System.Diagnostics;
using CardScanner.Core.Catalog;
using CardScanner.Core.Ocr;
using CardScanner.Core.Vision;
using OpenCvSharp;

namespace CardScanner.Core.Recognition;

public sealed record Candidate(CardInfo Card, float Score, float ImageSimilarity, bool NameMatched, bool NumberMatched, bool SetMatched);

public sealed class RecognitionResult
{
    public required string Source { get; init; }
    /// <summary>Name of the folder the photo came from (e.g. "raw", "single sleeve"), if any.</summary>
    public string Folder { get; set; } = "";
    /// <summary>Full path of the photo file, when it came from a file.</summary>
    public string? FilePath { get; set; }
    /// <summary>True if the orientation was chosen by the user rather than automatically.</summary>
    public bool OrientationForced { get; init; }
    public required List<Candidate> Candidates { get; init; }
    /// <summary>The straightened card (high resolution) as JPEG bytes, for showing in the app.</summary>
    public required byte[] CardImageJpeg { get; init; }
    public required bool CardOutlineFound { get; init; }
    public required bool UpsideDown { get; init; }
    public required TimeSpan Elapsed { get; init; }

    /// <summary>The card name as read from the card (OCR), if it could be read.</summary>
    public string? NameRead { get; init; }
    /// <summary>Border colour measured on the photo ("white", "black"), or null if unclear.</summary>
    public string? BorderColor { get; init; }
    /// <summary>The collector line as read from the card, if any.</summary>
    public CollectorLine Collector { get; init; } = CollectorLine.Empty;
    /// <summary>Foil according to the ★/• in the collector line (null = couldn't tell).</summary>
    public bool? FoilFromCollector => Collector.Foil;
    /// <summary>Name, set and collector number all agree: about as sure as it gets.</summary>
    public bool Pinned { get; init; }
    /// <summary>What pinned it, in words (e.g. "name + set + number agree"), or null if not pinned.</summary>
    public string? PinReason { get; init; }
    /// <summary>Needs a human look, and why.</summary>
    public bool Flagged => FlagReason is not null;
    public string? FlagReason { get; init; }

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

/// <summary>
/// Photo in, ranked catalog printings out.
///
///   1. Find the card in the photo and straighten it.
///   2. Read the card's name (OCR). That decides which card it is.
///   3. Read the collector line (set code + number + ★/•). That pins down the printing.
///   4. Compare the picture against every printing of that card to break remaining ties.
///
/// If the name can't be read, it falls back to the collector line, then to the picture alone,
/// and flags the card for review.
/// </summary>
public sealed class Recognizer : IDisposable
{
    // Scoring weights, tuned on real phone photos (see docs/recognition.md).
    private const double ImageWeight = 2.0;
    private const double NumberBonus = 0.30;
    private const double SetBonus = 0.20;
    private const double BothBonus = 0.50; // set AND number both read: near-decisive
    private const double UnlikelyPenalty = 0.20;    // collector-only reprints, Summer Magic, 90s boxed reprints
    private const int PictureCandidates = 5;        // nearest pictures always considered
    private const double BorderPenalty = 0.40;      // clearly white border vs a black-bordered printing, or vice versa
    private const double YearBonus = 0.25;          // copyright year printed on the card = the printing's release year
    private const double MinNameScore = 0.85;
    private const double MinFallbackNameScore = 0.90;
    private const float MinImageSimilarity = 0.50f;

    private const int HiW = CardDetector.Width * 2, HiH = CardDetector.Height * 2;

    private readonly CardCatalog _catalog;
    private readonly FingerprintIndex _index;
    private readonly Fingerprinter _fingerprinter;
    private readonly CardIndex _cards;
    private readonly CardTextReader _ocr;
    private readonly CLAHE _clahe = Cv2.CreateCLAHE(2.5, new Size(8, 8));

    public CatalogManifest Manifest { get; }
    public CardCatalog Catalog => _catalog;

    private Recognizer(CatalogManifest manifest, CardCatalog catalog, FingerprintIndex index, Fingerprinter fp, CardIndex cards, CardTextReader ocr)
    {
        Manifest = manifest;
        _catalog = catalog;
        _index = index;
        _fingerprinter = fp;
        _cards = cards;
        _ocr = ocr;
    }

    public static Recognizer Load(AppPaths paths, string? ocrModelDir = null)
    {
        var manifest = CatalogManifest.TryLoad(paths.Manifest)
            ?? throw new FileNotFoundException("The card catalog hasn't been downloaded yet.");
        var index = FingerprintIndex.Load(paths.Fingerprints, paths.FingerprintIds, manifest.Model.Dim);
        var catalog = new CardCatalog(paths.Database);
        var fp = new Fingerprinter(paths.Model, manifest.Model);
        var cards = new CardIndex(paths.Database);
        var ocr = new CardTextReader(ocrModelDir ?? CardTextReader.DefaultModelDir);
        return new Recognizer(manifest, catalog, index, fp, cards, ocr);
    }

    /// <param name="forceUpsideDown">null = decide automatically; true/false = the user says which way up it is.</param>
    public RecognitionResult IdentifyFile(string path, int topK = 8, bool? forceUpsideDown = null)
    {
        using var photo = Cv2.ImRead(path, ImreadModes.Color); // applies phone rotation (EXIF)
        if (photo.Empty())
            throw new InvalidDataException($"Couldn't open {Path.GetFileName(path)}. If it's an iPhone HEIC photo, save it as JPG.");
        var result = Identify(photo, Path.GetFileName(path), topK, forceUpsideDown);
        result.Folder = Path.GetFileName(Path.GetDirectoryName(Path.GetFullPath(path))) ?? "";
        result.FilePath = Path.GetFullPath(path);
        return result;
    }

    private sealed record NameHit(string Key, double Score, string Raw, int View);

    public RecognitionResult Identify(Mat photo, string source, int topK = 8, bool? forceUpsideDown = null)
    {
        var sw = Stopwatch.StartNew();
        using var detected = CardDetector.Detect(photo);

        // High-resolution straightened card for reading text; normal size for the picture match.
        using var hiUp = detected.Found
            ? CardDetector.Warp(photo, detected.Corners, HiW, HiH)
            : Resize(photo, HiW, HiH);
        using var hiDown = new Mat();
        Cv2.Rotate(hiUp, hiDown, RotateFlags.Rotate180);
        var hi = new[] { hiUp, hiDown };
        using var smallUp = Resize(hiUp, CardDetector.Width, CardDetector.Height);
        using var smallDown = Resize(hiDown, CardDetector.Width, CardDetector.Height);
        var vecs = _fingerprinter.EmbedBatch([smallUp, smallDown]);

        int[] views = forceUpsideDown switch { true => [1], false => [0], null => [0, 1] };

        // 1. Read the name from the top of the card, both ways up.
        var hits = new List<NameHit>();
        foreach (var v in views) hits.AddRange(ReadNames(hi[v], v, topOnly: true, minScore: MinNameScore));
        if (!hits.Any(h => h.Score >= 0.9))
            foreach (var v in views) hits.AddRange(ReadNames(Enhance(hi[v]), v, topOnly: true, minScore: MinNameScore));
        // Borderless / showcase cards can have the name somewhere else: read the whole card.
        if (hits.Count == 0)
            foreach (var v in views)
            {
                using var whole = Resize(hi[v], 732, 1020);
                hits.AddRange(ReadNames(whole, v, topOnly: false, minScore: MinFallbackNameScore)
                    .Where(h => h.Key.Length >= 5));
            }

        // 2. Which way up? Whichever view has the name reading the picture agrees with best.
        int view = views[0];
        if (views.Length == 2)
        {
            double Best(int v) => hits.Where(h => h.View == v)
                .Select(h => h.Score + ImageWeight * BestSimilarity(h.Key, vecs[v]))
                .DefaultIfEmpty(ImageWeight * _index.Search(vecs[v], 1)[0].Score)
                .Max();
            view = Best(1) > Best(0) ? 1 : 0;
        }
        var vec = vecs[view];
        var viewHits = hits.Where(h => h.View == view).ToList();
        // "Dead" is a card name too (Dead // Gone), but if "Kjeldoran Dead" was read, it's part of that.
        viewHits = viewHits.Where(h => !viewHits.Any(o => o.Key != h.Key && o.Score >= 0.9
            && (" " + o.Key + " ").Contains(" " + h.Key + " "))).ToList();

        // 3. Collector line (bottom-left small print) and border colour.
        var collector = ReadCollector(hi[view]);
        // Older frames (1997, 2003-2014) and retro reprints have no set code: their number follows the
        // copyright line, further right. Read that from a sharper, 2x-resolution straightening of the photo.
        if (detected.Found && collector.SetCodes.Count == 0)
        {
            using var sharp = CardDetector.Warp(photo, detected.Corners, HiW * 2, HiH * 2);
            using var turned = new Mat();
            if (view == 1) Cv2.Rotate(sharp, turned, RotateFlags.Rotate180);
            collector = collector.WithCopyrightNumbers(ReadCopyrightLine(view == 1 ? turned : sharp));
        }
        var border = detected.Found ? CardBorder.Classify(hi[view]) : null;

        // 4. Score every printing that the name or the collector line points at.
        var nameScore = new Dictionary<string, double>();
        foreach (var h in viewHits)
            nameScore[h.Key] = Math.Max(nameScore.GetValueOrDefault(h.Key), h.Score);
        var pool = new Dictionary<string, PrintingKey>();
        foreach (var key in nameScore.Keys)
            foreach (var p in _cards.PrintingsOfName(key)) pool[p.Id] = p;
        foreach (var set in collector.SetCodes)
            foreach (var num in collector.Numbers)
                foreach (var p in _cards.PrintingsAt(set, num)) pool[p.Id] = p;
        // The closest pictures always get a say, so a misread name ("Flying" → Fling) can't shut out
        // the card the photo obviously shows (a Secret Lair token whose set code didn't read).
        var pictureIds = new HashSet<string>();
        foreach (var (id, _) in _index.Search(vec, PictureCandidates))
            if (_cards.ById(id) is { } p && !pool.ContainsKey(id)) { pool[id] = p; pictureIds.Add(id); }

        var scored = new List<(PrintingKey P, double Score, float Sim, bool Name, bool Num, bool Set, bool BorderMismatch, bool Year)>();
        foreach (var p in pool.Values)
        {
            if (!_index.Contains(p.Id)) continue;
            float sim = _index.Similarity(vec, p.Id);
            double ns = p.Name.Split(" // ").Append(p.Name).Select(CardIndex.Normalize)
                .Select(k => nameScore.GetValueOrDefault(k)).Max();
            bool num = collector.Numbers.Contains(p.Number.ToLowerInvariant().TrimStart('0'));
            bool set = collector.SetCodes.Contains(p.SetCode.ToLowerInvariant());
            bool pinnedByCollector = num && set;
            bool borderMismatch = border switch
            {
                "white" => p.BorderColor is "black" or "gold",
                "black" => p.BorderColor == "white",
                _ => false,
            };
            bool yearMatch = collector.CopyrightYear is { } cy && p.ReleaseYear == cy;
            double score = ImageWeight * sim + ns + (num ? NumberBonus : 0) + (set ? SetBonus : 0) + (pinnedByCollector ? BothBonus : 0)
                + (yearMatch && !pinnedByCollector ? YearBonus : 0)
                - (p.IsUnlikely && !pinnedByCollector ? UnlikelyPenalty : 0)
                - (borderMismatch && !pinnedByCollector ? BorderPenalty : 0);
            scored.Add((p, score, sim, ns > 0, num, set, borderMismatch && !pinnedByCollector, yearMatch));
        }

        string? flag = null;
        if (scored.Count == 0)
        {
            // Nothing readable: picture only.
            foreach (var (id, s) in _index.Search(vec, topK))
                scored.Add((new PrintingKey(id, "", "", "", ""), ImageWeight * s, s, false, false, false, false, false));
            flag = "Couldn't read the card's name or collector number — matched by picture only.";
        }
        scored.Sort((a, b) => b.Score.CompareTo(a.Score));
        // Don't offer printings whose border colour contradicts the card (a black-bordered Alpha card when
        // the photo clearly shows a white border), unless that's all there is.
        // Picture-only extras are only shown when they're the best guess or the photo really looks like
        // them, so a Kjeldoran Dead doesn't come with random red cards attached.
        var top = scored.Where((t, i) => i == 0 || !t.BorderMismatch)
            .Where((t, i) => i == 0 || !pictureIds.Contains(t.P.Id) || t.Num || t.Sim >= 0.85f)
            .Take(topK).ToList();

        var cards = _catalog.GetMany(top.Select(t => t.P.Id).ToList());
        var candidates = top.Where(t => cards.ContainsKey(t.P.Id))
            .Select(t => new Candidate(cards[t.P.Id], (float)t.Score, t.Sim, t.Name, t.Num, t.Set)).ToList();

        var best = candidates.FirstOrDefault();
        if (flag is null && best is not null)
        {
            if (!best.NameMatched && !(best.NumberMatched && best.SetMatched))
                flag = "Couldn't read the card's name — matched by collector line and picture.";
            else if (best.ImageSimilarity < MinImageSimilarity && !(best.NameMatched && best.NumberMatched && best.SetMatched))
                flag = "The picture doesn't look much like the catalog image.";
        }
        bool pinned = best is { NameMatched: true, NumberMatched: true, SetMatched: true };
        string? pinReason = pinned ? "name + set + number agree" : null;
        // Retro-frame cards print a number but no set code. If the name and number together point at
        // exactly one printing, that's as good as a set + number match.
        // When the number alone fits two printings (8th and 9th Edition Scathe Zombies are both #160),
        // the printed copyright year (1993-2005) can settle it.
        if (!pinned && best is { NameMatched: true, NumberMatched: true } && collector.SetCodes.Count == 0)
        {
            var same = scored.Where(t => t.Name && t.Num && t.P.Name == best.Card.Name).ToList();
            if (same.Count == 1) { pinned = true; pinReason = "name + number (no set code printed)"; }
            else if (same.Count(t => t.Year) == 1 && same.First(t => t.P.Id == best.Card.Id).Year)
            { pinned = true; pinReason = "name + number + copyright year"; }
        }
        // Japanese printings: the name can't be read, but set code + number + the JP marker pin it down.
        if (!pinned && best is { NumberMatched: true, SetMatched: true }
            && scored.FirstOrDefault(t => t.P.Id == best.Card.Id).P?.Lang == "ja")
        {
            pinned = true;
            pinReason = "set + number + JP marker (Japanese printing)";
            if (flag?.StartsWith("Couldn't read the card's name") == true) flag = null;
        }

        // Look-alike printings with very different prices (e.g. Alpha/Beta/Unlimited/Revised duals,
        // which have no collector line): the picture alone shouldn't decide. Ask a human.
        if (flag is null && best is not null && !pinned)
        {
            var rival = candidates.Skip(1).FirstOrDefault(c => c.Card.Name == best.Card.Name);
            decimal p1 = Price(best.Card), p2 = rival is null ? 0 : Price(rival.Card);
            decimal hiP = Math.Max(p1, p2), loP = Math.Max(Math.Min(p1, p2), 0.01m);
            if (rival is not null && hiP >= 20 && hiP / loP >= 2 && best.Score - rival.Score < 0.15f)
                flag = $"Look-alike printings with very different prices ({best.Card.SetCode.ToUpperInvariant()} ${p1:0.##} vs {rival.Card.SetCode.ToUpperInvariant()} ${p2:0.##}) — double-check the edition.";
        }

        Cv2.ImEncode(".jpg", hi[view], out var jpeg, new ImageEncodingParam(ImwriteFlags.JpegQuality, 92));
        return new RecognitionResult
        {
            Source = source,
            Candidates = candidates,
            CardImageJpeg = jpeg,
            CardOutlineFound = detected.Found,
            UpsideDown = view == 1,
            OrientationForced = forceUpsideDown is not null,
            NameRead = viewHits.OrderByDescending(h => h.Score).FirstOrDefault()?.Raw,
            Collector = collector,
            BorderColor = border,
            Pinned = pinned,
            PinReason = pinReason,
            FlagReason = flag,
            Elapsed = sw.Elapsed,
        };
    }

    private static decimal Price(CardInfo c) => c.PriceUsd ?? c.PriceUsdFoil ?? c.PriceUsdEtched ?? 0m;

    private double BestSimilarity(string nameKey, float[] vec)
    {
        float best = 0;
        foreach (var p in _cards.PrintingsOfName(nameKey))
            best = Math.Max(best, _index.Similarity(vec, p.Id));
        return best;
    }

    /// <summary>Keywords printed in rules text that sit one letter away from a real card name
    /// ("Flying" → Fling). Only a fuzzy match is ignored; a card actually named this still matches.</summary>
    private static readonly HashSet<string> RulesWords =
    [
        "flying", "trample", "haste", "vigilance", "reach", "deathtouch", "lifelink", "first strike",
        "double strike", "flash", "defender", "menace", "hexproof", "indestructible", "ward", "prowess",
        "flanking", "banding", "shroud", "fear", "intimidate", "regenerate", "enchant creature", "equip",
    ];

    private IEnumerable<NameHit> ReadNames(Mat card, int view, bool topOnly, double minScore)
    {
        Mat region = topOnly
            ? new Mat(card, new Rect(0, 0, (int)(card.Cols * 0.85), (int)(card.Rows * 0.20)))
            : card;
        try
        {
            var found = new List<NameHit>();
            foreach (var text in LineTexts(_ocr.Read(region)))
                if (_cards.MatchName(text, minScore) is { } m && !(m.Score < 1 && RulesWords.Contains(CardIndex.Normalize(text))))
                    found.Add(new NameHit(m.Name, m.Score, text, view));
            return found;
        }
        finally
        {
            if (topOnly) region.Dispose();
        }
    }

    /// <summary>Each OCR line on its own, plus words that sit on the same row joined together
    /// (the reader sometimes splits "Lightning Bolt" into "Lightning" and "Bolt").</summary>
    private static IEnumerable<string> LineTexts(List<TextLine> lines)
    {
        foreach (var l in lines) yield return l.Text;
        var rows = new List<List<TextLine>>();
        foreach (var l in lines.OrderBy(l => l.Top))
        {
            float h = l.Box.Max(p => p.Y) - l.Top;
            var row = rows.FirstOrDefault(r => Math.Abs(r[0].Top - l.Top) < h * 0.5);
            if (row is null) rows.Add([l]); else row.Add(l);
        }
        foreach (var row in rows.Where(r => r.Count > 1))
            yield return string.Join(" ", row.OrderBy(l => l.Left).Select(l => l.Text));
    }

    /// <summary>Modern collector line, bottom-left: "R 0381 DSK • EN", "147/269 R / ELD • EN".</summary>
    private CollectorLine ReadCollector(Mat card)
    {
        int y0 = (int)(card.Rows * 0.88);
        using var bottom = new Mat(card, new Rect(0, y0, (int)(card.Cols * 0.62), card.Rows - y0));
        using var big = new Mat();
        Cv2.Resize(bottom, big, new Size(0, 0), 2, 2, InterpolationFlags.Cubic);
        var lines = _ocr.Read(big).OrderBy(l => l.Top).Select(l => l.Text);
        return CollectorLine.Parse(string.Join(" ", lines));
    }

    /// <summary>
    /// The copyright line of older/retro frames, e.g. "©1993-1998 Wizards of the Coast, Inc. 128/350" or
    /// "TM & © 2024 Wizards of the Coast 14". Where the number sits (measured on ~290 Scryfall images,
    /// tools/collector_survey): x ~ 0.43-0.75 of the card width, up to ~0.90 on Time Spiral timeshifted and
    /// Future Sight. Reads 95% of the width but keeps only lines that start in the left 70%: the copyright
    /// line always does, the power/toughness box never does.
    /// </summary>
    private string ReadCopyrightLine(Mat card)
    {
        int y0 = (int)(card.Rows * 0.88);
        using var bottom = new Mat(card, new Rect(0, y0, (int)(card.Cols * 0.95), card.Rows - y0));
        float maxLeft = card.Cols * 0.70f;
        return string.Join(" ", _ocr.Read(bottom).Where(l => l.Box.Min(pt => pt.X) < maxLeft).OrderBy(l => l.Top).Select(l => l.Text));
    }

    private Mat Enhance(Mat bgr)
    {
        using var gray = new Mat();
        Cv2.CvtColor(bgr, gray, ColorConversionCodes.BGR2GRAY);
        using var eq = new Mat();
        _clahe.Apply(gray, eq);
        var outBgr = new Mat();
        Cv2.CvtColor(eq, outBgr, ColorConversionCodes.GRAY2BGR);
        return outBgr;
    }

    private static Mat Resize(Mat src, int w, int h)
    {
        var dst = new Mat();
        Cv2.Resize(src, dst, new Size(w, h), 0, 0, src.Width > w ? InterpolationFlags.Area : InterpolationFlags.Cubic);
        return dst;
    }

    public void Dispose()
    {
        _fingerprinter.Dispose();
        _catalog.Dispose();
        _ocr.Dispose();
        _clahe.Dispose();
    }
}
