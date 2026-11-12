using System.Security.Cryptography;

namespace CardScanner.Core.Catalog;

public sealed record DownloadProgress(string Step, long BytesDone, long BytesTotal)
{
    public double Fraction => BytesTotal > 0 ? Math.Clamp((double)BytesDone / BytesTotal, 0, 1) : 0;
}

/// <summary>
/// Downloads the card catalog and AI model from the project's GitHub releases.
/// Only files that changed are downloaded, every file is checked against its SHA-256,
/// and nothing replaces the working catalog until it has been fully verified.
/// </summary>
public sealed class CatalogUpdater
{
    public const string ReleaseBase = "https://github.com/MrWeasel42/mtg-card-scanner/releases/download";
    public static string CatalogUrl(string file) => $"{ReleaseBase}/catalog-latest/{file}";
    public static string ModelUrl(string modelVersionTag, string file) => $"{ReleaseBase}/{modelVersionTag}/{file}";

    /// <summary>Release tag that holds each model version.</summary>
    public static string ModelTag(string modelVersion) => modelVersion switch
    {
        "dinov2s-224x308-v1" => "model-v1",
        _ => throw new NotSupportedException($"This app version doesn't know model '{modelVersion}'. Please update the app."),
    };

    private readonly AppPaths _paths;
    private readonly HttpClient _http;

    public CatalogUpdater(AppPaths paths, HttpClient? http = null)
    {
        _paths = paths;
        _http = http ?? CreateHttpClient();
    }

    public static HttpClient CreateHttpClient()
    {
        var http = new HttpClient { Timeout = TimeSpan.FromMinutes(30) };
        http.DefaultRequestHeaders.UserAgent.ParseAdd("MTGCardScanner/0.1 (+https://github.com/MrWeasel42/mtg-card-scanner)");
        return http;
    }

    public bool HasCatalog => CatalogManifest.TryLoad(_paths.Manifest) is { } m
        && File.Exists(_paths.Model) && m.Files.Keys.All(f => File.Exists(_paths.CatalogFile(f)));

    public CatalogManifest? LocalManifest => CatalogManifest.TryLoad(_paths.Manifest);

    public async Task<CatalogManifest> FetchRemoteManifestAsync(CancellationToken ct = default)
    {
        var json = await _http.GetStringAsync(CatalogUrl("manifest.json"), ct);
        return CatalogManifest.Parse(json);
    }

    /// <summary>True if the published catalog is newer than the one on disk.</summary>
    public async Task<bool> IsUpdateAvailableAsync(CancellationToken ct = default)
    {
        var remote = await FetchRemoteManifestAsync(ct);
        return LocalManifest?.CatalogVersion != remote.CatalogVersion || !HasCatalog;
    }

    /// <summary>Downloads whatever is missing or out of date. Safe to call anytime.</summary>
    public async Task<CatalogManifest> UpdateAsync(IProgress<DownloadProgress>? progress = null, CancellationToken ct = default)
    {
        var remote = await FetchRemoteManifestAsync(ct);
        var staging = Path.Combine(_paths.CatalogDir, "staging");
        Directory.CreateDirectory(staging);

        // Work out what needs downloading.
        var jobs = new List<(string Name, string Url, string Sha, long Size)>();
        if (!await HashMatchesAsync(_paths.Model, remote.Model.Sha256, ct))
            jobs.Add((remote.Model.File, ModelUrl(ModelTag(remote.Model.Version), remote.Model.File), remote.Model.Sha256, remote.Model.Size));
        foreach (var (name, info) in remote.Files)
            if (!await HashMatchesAsync(_paths.CatalogFile(name), info.Sha256, ct))
                jobs.Add((name, CatalogUrl(name), info.Sha256, info.Size));

        long total = jobs.Sum(j => j.Size), done = 0;
        foreach (var job in jobs)
        {
            var tmp = Path.Combine(staging, job.Name);
            var before = done;
            await DownloadAsync(job.Url, tmp, new Progress<long>(b =>
                progress?.Report(new DownloadProgress($"Downloading {Friendly(job.Name)}", before + b, total))), ct);
            if (!string.Equals(await Sha256Async(tmp, ct), job.Sha, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException($"{job.Name} was corrupted during download. Please try again.");
            done += job.Size;
        }

        // Everything verified: swap the new files in.
        foreach (var job in jobs)
            File.Move(Path.Combine(staging, job.Name), _paths.CatalogFile(job.Name), overwrite: true);
        await File.WriteAllTextAsync(_paths.Manifest, System.Text.Json.JsonSerializer.Serialize(remote), ct);
        progress?.Report(new DownloadProgress("Catalog ready", total, total));
        return remote;
    }

    private static string Friendly(string file) => file switch
    {
        "model.onnx" => "AI model",
        "catalog.sqlite" => "card database",
        "fingerprints.bin" or "fingerprint_ids.txt" => "card fingerprints",
        _ => file,
    };

    private async Task DownloadAsync(string url, string dest, IProgress<long> progress, CancellationToken ct)
    {
        for (int attempt = 1; ; attempt++)
        {
            try
            {
                using var resp = await _http.GetAsync(url, HttpCompletionOption.ResponseHeadersRead, ct);
                resp.EnsureSuccessStatusCode();
                await using var src = await resp.Content.ReadAsStreamAsync(ct);
                await using var dst = File.Create(dest);
                var buffer = new byte[1 << 20];
                long got = 0;
                int n;
                while ((n = await src.ReadAsync(buffer, ct)) > 0)
                {
                    await dst.WriteAsync(buffer.AsMemory(0, n), ct);
                    got += n;
                    progress.Report(got);
                }
                return;
            }
            catch (HttpRequestException) when (attempt < 3)
            {
                await Task.Delay(TimeSpan.FromSeconds(3 * attempt), ct);
            }
        }
    }

    private static async Task<bool> HashMatchesAsync(string path, string sha, CancellationToken ct) =>
        File.Exists(path) && string.Equals(await Sha256Async(path, ct), sha, StringComparison.OrdinalIgnoreCase);

    public static async Task<string> Sha256Async(string path, CancellationToken ct = default)
    {
        await using var fs = File.OpenRead(path);
        var hash = await SHA256.HashDataAsync(fs, ct);
        return Convert.ToHexStringLower(hash);
    }
}
