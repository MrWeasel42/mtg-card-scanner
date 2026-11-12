namespace CardScanner.Core;

/// <summary>Where the app keeps its data. Everything lives under one folder per user.</summary>
public sealed class AppPaths
{
    public string Root { get; }
    public string CatalogDir => Path.Combine(Root, "catalog");
    public string CacheDir => Path.Combine(Root, "cache");
    public string ThumbnailDir => Path.Combine(CacheDir, "thumbs");
    public string LogsDir => Path.Combine(Root, "logs");

    public string Manifest => Path.Combine(CatalogDir, "manifest.json");
    public string Database => Path.Combine(CatalogDir, "catalog.sqlite");
    public string Fingerprints => Path.Combine(CatalogDir, "fingerprints.bin");
    public string FingerprintIds => Path.Combine(CatalogDir, "fingerprint_ids.txt");
    public string Model => Path.Combine(CatalogDir, "model.onnx");

    public AppPaths(string? root = null)
    {
        Root = root ?? Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "MTGCardScanner");
        foreach (var d in new[] { Root, CatalogDir, CacheDir, ThumbnailDir, LogsDir })
            Directory.CreateDirectory(d);
    }

    public string CatalogFile(string name) => Path.Combine(CatalogDir, name);
}
