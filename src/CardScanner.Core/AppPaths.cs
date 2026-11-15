namespace CardScanner.Core;

/// <summary>
/// Where the app keeps its data: one folder per user (%LocalAppData%\MTGCardScanner, next to the installed app in
/// %LocalAppData%\Programs). Layout:
///   Sessions\&lt;date name&gt;\   session summary, CSVs and a Crops folder for each scan session
///   Exports\                     CSVs exported outside a session
///   Logs\                        results log, errors.log, Crops\ for scans outside a session
///   Phone photos\&lt;date&gt;\      photos the phone (or the machine) sent
///   catalog\, cache\, settings.json   the app's own files
/// </summary>
public sealed class AppPaths
{
    public string Root { get; }
    public string CatalogDir => Path.Combine(Root, "catalog");
    public string CacheDir => Path.Combine(Root, "cache");
    public string ThumbnailDir => Path.Combine(CacheDir, "thumbs");
    public string LogsDir => Path.Combine(Root, "Logs");
    public string SessionsDir => Path.Combine(Root, "Sessions");
    public string ExportsDir => Path.Combine(Root, "Exports");
    public string PhonePhotosDir => Path.Combine(Root, "Phone photos");
    /// <summary>Crops of cards scanned outside a session (a session keeps its own in its folder).</summary>
    public string LooseCropsDir => Path.Combine(LogsDir, "Crops");

    public string Manifest => Path.Combine(CatalogDir, "manifest.json");
    public string Database => Path.Combine(CatalogDir, "catalog.sqlite");
    public string Fingerprints => Path.Combine(CatalogDir, "fingerprints.bin");
    public string FingerprintIds => Path.Combine(CatalogDir, "fingerprint_ids.txt");
    public string Model => Path.Combine(CatalogDir, "model.onnx");

    public AppPaths(string? root = null)
    {
        Root = root ?? Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "MTGCardScanner");
        foreach (var d in new[] { Root, CatalogDir, CacheDir, ThumbnailDir, LogsDir, SessionsDir, ExportsDir, PhonePhotosDir })
            Directory.CreateDirectory(d);
    }

    public string CatalogFile(string name) => Path.Combine(CatalogDir, name);
}
