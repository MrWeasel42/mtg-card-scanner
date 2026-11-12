using CardScanner.Core;
using CardScanner.Core.Catalog;
using CardScanner.Core.Recognition;
using CardScanner.Core.Vision;
using OpenCvSharp;
using Xunit;

namespace CardScanner.Core.Tests;

public class FingerprintIndexTests
{
    [Fact]
    public void Finds_nearest_vector()
    {
        var rng = new Random(1);
        int n = 500, dim = 64;
        var ids = Enumerable.Range(0, n).Select(i => $"card{i}").ToArray();
        var vecs = new float[n * dim];
        for (int i = 0; i < n; i++) Normalize(vecs.AsSpan(i * dim, dim), rng);
        var index = new FingerprintIndex(ids, vecs, dim);

        var query = vecs.AsSpan(37 * dim, dim).ToArray();
        for (int d = 0; d < dim; d++) query[d] += (float)(rng.NextDouble() - 0.5) * 0.05f;

        var top = index.Search(query, 5);
        Assert.Equal("card37", top[0].Id);
        Assert.Equal(5, top.Count);
        Assert.True(top[0].Score >= top[1].Score && top[1].Score >= top[4].Score);
    }

    [Fact]
    public void Loads_float16_file()
    {
        var dir = Directory.CreateTempSubdirectory().FullName;
        var values = new Half[] { (Half)0.5f, (Half)(-0.25f), (Half)1f, (Half)0f };
        File.WriteAllBytes(Path.Combine(dir, "f.bin"), values.SelectMany(h => BitConverter.GetBytes(h)).ToArray());
        File.WriteAllLines(Path.Combine(dir, "ids.txt"), ["a", "b"]);
        var index = FingerprintIndex.Load(Path.Combine(dir, "f.bin"), Path.Combine(dir, "ids.txt"), 2);
        Assert.Equal(2, index.Count);
        Assert.Equal("b", index.Search([1f, 0f], 1)[0].Id);
    }

    private static void Normalize(Span<float> v, Random rng)
    {
        float s = 0;
        for (int i = 0; i < v.Length; i++) { v[i] = (float)(rng.NextDouble() * 2 - 1); s += v[i] * v[i]; }
        s = MathF.Sqrt(s);
        for (int i = 0; i < v.Length; i++) v[i] /= s;
    }
}

public class CardDetectorTests
{
    /// <summary>Pastes a card image into a "photo" at an angle, like a phone picture on a table.</summary>
    internal static Mat FakePhoto(Mat card, double angleDeg, int photoW = 1800, int photoH = 1400, bool sideways = false)
    {
        var photo = new Mat(photoH, photoW, MatType.CV_8UC3, new Scalar(120, 110, 100));
        using (var noise = new Mat(photoH, photoW, MatType.CV_8UC3))
        {
            Cv2.Randn(noise, new Scalar(0, 0, 0), new Scalar(8, 8, 8));
            Cv2.Add(photo, noise, photo);
        }
        float cw = 600, ch = cw * 88f / 63f;
        if (sideways) (cw, ch) = (ch, cw);
        var center = new Point2f(photoW / 2f, photoH / 2f);
        var rect = new RotatedRect(center, new Size2f(cw, ch), (float)angleDeg);
        var pts = CardDetector.OrderCorners(rect.Points());
        var src = new[] { new Point2f(0, 0), new Point2f(card.Width - 1, 0), new Point2f(card.Width - 1, card.Height - 1), new Point2f(0, card.Height - 1) };
        using var m = Cv2.GetPerspectiveTransform(src, pts);
        using var mask = new Mat(card.Size(), MatType.CV_8UC1, Scalar.All(255));
        using var warped = new Mat();
        using var warpedMask = new Mat();
        Cv2.WarpPerspective(card, warped, m, photo.Size(), InterpolationFlags.Cubic);
        Cv2.WarpPerspective(mask, warpedMask, m, photo.Size());
        warped.CopyTo(photo, warpedMask);
        return photo;
    }

    internal static Mat LoadFixtureCard(int i)
    {
        var path = Directory.GetFiles(Path.Combine(AppContext.BaseDirectory, "Fixtures", "cards"), "*.png").OrderBy(p => p).ElementAt(i);
        return Cv2.ImRead(path, ImreadModes.Color);
    }

    internal static double Similarity(Mat a, Mat b)
    {
        using var r = new Mat();
        Cv2.MatchTemplate(a, b, r, TemplateMatchModes.CCoeffNormed);
        return r.Get<float>(0, 0);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(12)]
    [InlineData(-25)]
    public void Finds_and_straightens_a_tilted_card(double angle)
    {
        using var card = LoadFixtureCard(0);
        using var photo = FakePhoto(card, angle);
        using var found = CardDetector.Detect(photo);
        Assert.True(found.Found, "card outline not found");
        Assert.Equal(CardDetector.Width, found.Card.Width);
        Assert.Equal(CardDetector.Height, found.Card.Height);
        Assert.True(Similarity(found.Card, card) > 0.8, $"straightened card doesn't match ({Similarity(found.Card, card):0.00})");
    }

    [Fact]
    public void Sideways_card_comes_out_portrait()
    {
        using var card = LoadFixtureCard(1);
        using var photo = FakePhoto(card, 0, sideways: true);
        using var found = CardDetector.Detect(photo);
        Assert.True(found.Found);
        Assert.Equal(CardDetector.Height, found.Card.Height);
    }

    [Fact]
    public void Already_cropped_photo_is_used_as_is()
    {
        using var card = LoadFixtureCard(2);
        using var found = CardDetector.Detect(card);
        Assert.Equal(CardDetector.Width, found.Card.Width);
        Assert.True(Similarity(found.Card, card) > 0.9);
    }
}

public class RecognizerTests
{
    private static AppPaths FixturePaths()
    {
        // Copy the fixture pack into a temp app folder laid out like the real one.
        var root = Directory.CreateTempSubdirectory().FullName;
        var paths = new AppPaths(root);
        foreach (var f in new[] { "manifest.json", "catalog.sqlite", "fingerprints.bin", "fingerprint_ids.txt", "model.onnx" })
            File.Copy(Path.Combine(AppContext.BaseDirectory, "Fixtures", f), paths.CatalogFile(f));
        return paths;
    }

    [Fact]
    public void Identifies_every_fixture_card_from_a_tilted_photo()
    {
        var paths = FixturePaths();
        using var rec = Recognizer.Load(paths);
        for (int i = 0; i < 8; i++)
        {
            using var card = CardDetectorTests.LoadFixtureCard(i);
            using var photo = CardDetectorTests.FakePhoto(card, 8 * (i % 3) - 8);
            var result = rec.Identify(photo, $"photo{i}");
            Assert.NotNull(result.Best);
            using var detected = CardDetector.Detect(photo);
            var why = $"card {i}: outline={result.CardOutlineFound} upsideDown={result.UpsideDown} " +
                      $"corners=[{string.Join(" ", detected.Corners.Select(c => $"({c.X:0},{c.Y:0})"))}] " +
                      $"sim={CardDetectorTests.Similarity(detected.Card, card):0.00} " +
                      string.Join(", ", result.Candidates.Select(c => $"{c.Card.Name}={c.Score:0.000}"));
            Assert.True($"Test Card {i}" == result.Best!.Card.Name && !result.UpsideDown, why);
        }
    }

    /// <summary>A card inside a clear sleeve: a slightly bigger, see-through rectangle with a visible edge.</summary>
    private static Mat Sleeve(Mat card, double grow)
    {
        int w = (int)(card.Width * grow), h = (int)(card.Height * (1 + (grow - 1) * 0.7));
        var sleeve = new Mat(h, w, MatType.CV_8UC3, new Scalar(150, 142, 135)); // table seen through clear plastic
        Cv2.Rectangle(sleeve, new Rect(0, 0, w, h), new Scalar(225, 225, 225), 3); // sleeve edge catching light
        card.CopyTo(sleeve[new Rect((w - card.Width) / 2, (h - card.Height) / 2, card.Width, card.Height)]);
        return sleeve;
    }

    [Theory]
    [InlineData(1.04)] // perfect fit / standard sleeve
    [InlineData(1.10)] // double sleeved
    public void Identifies_sleeved_cards(double grow)
    {
        var paths = FixturePaths();
        using var rec = Recognizer.Load(paths);
        int right = 0;
        for (int i = 0; i < 8; i++)
        {
            using var card = CardDetectorTests.LoadFixtureCard(i);
            using var sleeved = Sleeve(card, grow);
            using var photo = CardDetectorTests.FakePhoto(sleeved, 6);
            var result = rec.Identify(photo, $"sleeved{i}");
            if (result.Best?.Card.Name == $"Test Card {i}") right++;
        }
        Assert.True(right >= 6, $"only {right}/8 sleeved cards identified");
    }

    [Fact]
    public void Identifies_an_upside_down_card()
    {
        var paths = FixturePaths();
        using var rec = Recognizer.Load(paths);
        using var card = CardDetectorTests.LoadFixtureCard(3);
        using var flipped = new Mat();
        Cv2.Rotate(card, flipped, RotateFlags.Rotate180);
        using var photo = CardDetectorTests.FakePhoto(flipped, 5);
        var result = rec.Identify(photo, "flipped");
        Assert.Equal("Test Card 3", result.Best!.Card.Name);
        Assert.True(result.UpsideDown);
    }

    [Fact]
    public void Catalog_lookup_returns_card_details()
    {
        var paths = FixturePaths();
        using var catalog = new CardCatalog(paths.Database);
        var ids = File.ReadAllLines(paths.FingerprintIds);
        var card = catalog.Get(ids[0]);
        Assert.NotNull(card);
        Assert.Equal("tst", card!.SetCode);
        Assert.Equal(0.10m, card.PriceUsd);
    }
}

public class ManifestTests
{
    [Fact]
    public void Parses_published_manifest()
    {
        var m = CatalogManifest.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "manifest.json")));
        Assert.Equal(1, m.Format);
        Assert.Equal(8, m.FingerprintCount);
        Assert.Equal(192, m.Model.Dim);
        Assert.Equal(224, m.Model.Width);
        Assert.Contains("catalog.sqlite", m.Files.Keys);
        Assert.Equal("model-v1", CatalogUpdater.ModelTag("dinov2s-224x308-v1"));
    }
}

public class CollectorLineTests
{
    // Real collector lines read off test photos.
    [Theory]
    [InlineData("R0381 VALERA LUTFULLINA DSK·EN", "381", "dsk", false)]
    [InlineData("M0357 LTC ★EN ANASTASIA BALAKCHINA TM", "357", "ltc", true)]
    [InlineData("Not many do. RO325 DSC·EN PIOTR DURA", "325", "dsc", false)]
    [InlineData("mountainsroots. 147/269R ELDEN GRZEGORZ", "147", "eld", null)]
    [InlineData("015 TM OLENA RICHARDS SLDEN", "15", "sld", null)]
    [InlineData("U0334 CM LTREN NINO IS TM", "334", "ltr", null)]
    [InlineData("R0149 ANNA PAYLEEYA TDM★EN", "149", "tdm", true)]
    public void Parses_number_set_and_foil(string raw, string number, string set, bool? foil)
    {
        var c = CollectorLine.Parse(raw);
        Assert.Contains(number, c.Numbers);
        Assert.Contains(set, c.SetCodes);
        Assert.Equal(foil, c.Foil);
    }

    [Fact]
    public void Old_cards_have_no_collector_line()
    {
        var c = CollectorLine.Parse("Illus. Christopher Rush");
        Assert.Empty(c.SetCodes);
        Assert.False(c.HasAny && c.SetCodes.Count > 0);
    }
}

public class CardIndexTests
{
    [Theory]
    [InlineData("Æther Flash", "aether flash")]
    [InlineData("Nazgûl", "nazgul")]
    [InlineData("Niv-Mizzet, Visionary", "nivmizzet visionary")]
    [InlineData("Witch's  Clinic", "witchs clinic")]
    public void Normalizes_names(string input, string expected) => Assert.Equal(expected, CardIndex.Normalize(input));

    [Fact]
    public void Similarity_matches_rapidfuzz_ratio()
    {
        Assert.Equal(1.0, CardIndex.Similarity("abc", "abc"));
        // rapidfuzz: fuzz.ratio("theorists ssanctum", "theorists sanctum") = 97.14
        Assert.Equal(0.9714, CardIndex.Similarity("theorists ssanctum", "theorists sanctum"), 3);
    }

    [Fact]
    public void Matches_names_despite_ocr_typos()
    {
        var db = Path.Combine(AppContext.BaseDirectory, "Fixtures", "catalog.sqlite");
        var index = new CardIndex(db);
        Assert.Equal("test card 3", index.MatchName("Tesl Card 3")!.Value.Name);
        Assert.Null(index.MatchName("completely different words"));
        Assert.NotEmpty(index.PrintingsAt("tst", "0004"));
    }
}

public class TextReaderTests
{
    [Theory]
    [InlineData("Lightning Bolt")]
    [InlineData("Orcish Bowmasters")]
    public void Reads_printed_text(string text)
    {
        using var img = new Mat(160, 1100, MatType.CV_8UC3, new Scalar(225, 235, 240));
        Cv2.PutText(img, text, new Point(30, 105), HersheyFonts.HersheyTriplex, 2.4, new Scalar(20, 20, 20), 4, LineTypes.AntiAlias);
        using var reader = new CardScanner.Core.Ocr.CardTextReader(CardScanner.Core.Ocr.CardTextReader.DefaultModelDir);
        var lines = reader.Read(img);
        var all = string.Join(" ", lines.Select(l => l.Text));
        Assert.True(CardIndex.Similarity(CardIndex.Normalize(all), CardIndex.Normalize(text)) >= 0.85, $"read '{all}'");
    }
}
