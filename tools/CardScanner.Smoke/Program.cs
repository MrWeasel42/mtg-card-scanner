// End-to-end smoke test: downloads the published catalog with the app's own updater, takes
// random real card images from Scryfall, pastes each into a fake tilted "photo", and checks the
// recognizer names the card. Exits non-zero if accuracy is too low.
using CardScanner.Core;
using CardScanner.Core.Catalog;
using CardScanner.Core.Recognition;
using Microsoft.Data.Sqlite;
using OpenCvSharp;

int count = args.Length > 0 ? int.Parse(args[0]) : 40;
var paths = new AppPaths(Path.Combine(Path.GetTempPath(), "mtgscan-smoke"));
var updater = new CatalogUpdater(paths);
Console.WriteLine("Downloading catalog with the app's updater...");
var manifest = await updater.UpdateAsync(new Progress<DownloadProgress>(_ => { }));
Console.WriteLine($"Catalog {manifest.CatalogVersion}: {manifest.Cards:N0} cards");

using var rec = Recognizer.Load(paths);
var picks = new List<(string Id, string Name, string Url)>();
using (var con = new SqliteConnection($"Data Source={paths.Database};Mode=ReadOnly"))
{
    con.Open();
    using var cmd = con.CreateCommand();
    cmd.CommandText = "SELECT id, name, image_url FROM cards WHERE layout NOT IN ('token','emblem','art_series') ORDER BY random() LIMIT $n";
    cmd.Parameters.AddWithValue("$n", count);
    using var r = cmd.ExecuteReader();
    while (r.Read()) picks.Add((r.GetString(0), r.GetString(1), r.GetString(2)));
}

using var http = CatalogUpdater.CreateHttpClient();
var rng = new Random(7);
int exact = 0, name = 0, n = 0;
long ms = 0;
foreach (var (id, cardName, url) in picks)
{
    byte[] bytes;
    try { bytes = await http.GetByteArrayAsync(url); } catch { continue; }
    using var card = Cv2.ImDecode(bytes, ImreadModes.Color);
    using var photo = FakePhoto(card, rng.Next(-15, 16), rng.Next(2) == 0);
    var res = rec.Identify(photo, id);
    n++;
    ms += (long)res.Elapsed.TotalMilliseconds;
    if (res.Best?.Card.Id == id) exact++;
    if (res.Best?.Card.Name == cardName) name++;
    else Console.WriteLine($"  MISS: {cardName} -> {res.Best?.Card.Name} ({res.Best?.Card.SetLabel}) outline={res.CardOutlineFound}");
}
Console.WriteLine($"Right card: {name}/{n}  Exact printing: {exact}/{n}  Avg {ms / Math.Max(n, 1)} ms per photo");
var summary = Environment.GetEnvironmentVariable("GITHUB_STEP_SUMMARY");
if (summary is not null)
    File.AppendAllText(summary, $"### App end-to-end check\n- Right card: **{name}/{n}**\n- Exact printing: {exact}/{n}\n- Average {ms / Math.Max(n, 1)} ms per photo\n");
return n > 0 && name >= n * 0.85 ? 0 : 1;

static Mat FakePhoto(Mat card, double angle, bool lightTable)
{
    var bg = lightTable ? new Scalar(215, 210, 205) : new Scalar(45, 40, 38);
    var photo = new Mat(1500, 2000, MatType.CV_8UC3, bg);
    float cw = 700, ch = cw * 88f / 63f;
    var rect = new RotatedRect(new Point2f(1000, 750), new Size2f(cw, ch), (float)angle);
    var pts = CardScanner.Core.Vision.CardDetector.OrderCorners(rect.Points());
    var src = new[] { new Point2f(0, 0), new Point2f(card.Width - 1, 0), new Point2f(card.Width - 1, card.Height - 1), new Point2f(0, card.Height - 1) };
    using var m = Cv2.GetPerspectiveTransform(src, pts);
    using var mask = new Mat(card.Size(), MatType.CV_8UC1, Scalar.All(255));
    using var warped = new Mat();
    using var warpedMask = new Mat();
    Cv2.WarpPerspective(card, warped, m, photo.Size(), InterpolationFlags.Cubic);
    Cv2.WarpPerspective(mask, warpedMask, m, photo.Size());
    warped.CopyTo(photo, warpedMask);
    Cv2.GaussianBlur(photo, photo, new Size(3, 3), 0);
    return photo;
}
