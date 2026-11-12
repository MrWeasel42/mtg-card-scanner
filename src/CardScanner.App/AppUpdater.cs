using System.Diagnostics;
using System.Text.Json;
using CardScanner.Core.Catalog;

namespace CardScanner.App;

/// <summary>
/// Checks GitHub for a newer version of the app. If there is one, the app shows an
/// "Update available" button; clicking it downloads the new installer and runs it.
/// </summary>
public static class AppUpdater
{
    private const string LatestReleaseApi = "https://api.github.com/repos/MrWeasel42/mtg-card-scanner/releases/latest";
    private static readonly HttpClient Http = CatalogUpdater.CreateHttpClient();

    public sealed record Update(string Version, string InstallerUrl);

    public static async Task<Update?> CheckAsync(string currentVersion)
    {
        using var req = new HttpRequestMessage(HttpMethod.Get, LatestReleaseApi);
        req.Headers.Accept.ParseAdd("application/vnd.github+json");
        using var resp = await Http.SendAsync(req);
        if (!resp.IsSuccessStatusCode) return null;
        using var doc = JsonDocument.Parse(await resp.Content.ReadAsStringAsync());
        var tag = doc.RootElement.GetProperty("tag_name").GetString() ?? "";
        var latest = tag.TrimStart('v');
        if (!IsNewer(latest, currentVersion)) return null;
        foreach (var asset in doc.RootElement.GetProperty("assets").EnumerateArray())
        {
            var name = asset.GetProperty("name").GetString() ?? "";
            if (name.StartsWith("MTGCardScanner_Setup", StringComparison.OrdinalIgnoreCase) && name.EndsWith(".exe"))
                return new Update(latest, asset.GetProperty("browser_download_url").GetString()!);
        }
        return null;
    }

    public static bool IsNewer(string candidate, string current) =>
        Version.TryParse(candidate.Split('-')[0], out var a) &&
        Version.TryParse(current.Split('-')[0], out var b) && a > b;

    /// <summary>Downloads the installer and starts it. The caller should then close the app.</summary>
    public static async Task DownloadAndRunAsync(Update update, IProgress<double>? progress = null)
    {
        var file = Path.Combine(Path.GetTempPath(), $"MTGCardScanner_Setup_{update.Version}.exe");
        using (var resp = await Http.GetAsync(update.InstallerUrl, HttpCompletionOption.ResponseHeadersRead))
        {
            resp.EnsureSuccessStatusCode();
            long total = resp.Content.Headers.ContentLength ?? 0, done = 0;
            await using var src = await resp.Content.ReadAsStreamAsync();
            await using var dst = File.Create(file);
            var buf = new byte[1 << 20];
            int n;
            while ((n = await src.ReadAsync(buf)) > 0)
            {
                await dst.WriteAsync(buf.AsMemory(0, n));
                done += n;
                if (total > 0) progress?.Report((double)done / total);
            }
        }
        // /SILENT shows just a progress bar; the installer restarts the app when done.
        Process.Start(new ProcessStartInfo(file, "/SILENT") { UseShellExecute = true });
    }
}
