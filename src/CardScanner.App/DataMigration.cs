using CardScanner.Core;

namespace CardScanner.App;

/// <summary>
/// One-time move to the single data folder (0.6.1): sessions and exports used to go to Documents\MTG Card Scanner,
/// phone photos to phone_scans and crops to logs\crops. Sessions are copied (the Documents originals are left
/// alone, since that folder may be synced by OneDrive); everything inside the data folder is moved.
/// </summary>
public static class DataMigration
{
    public static void Run(AppPaths paths)
    {
        var marker = Path.Combine(paths.Root, ".layout-v2");
        if (File.Exists(marker)) return;
        try
        {
            // phone_scans\<date> -> Phone photos\<date>
            var oldPhotos = Path.Combine(paths.Root, "phone_scans");
            if (Directory.Exists(oldPhotos))
            {
                foreach (var d in Directory.GetDirectories(oldPhotos))
                {
                    var to = Path.Combine(paths.PhonePhotosDir, Path.GetFileName(d));
                    if (!Directory.Exists(to)) Directory.Move(d, to);
                }
                if (!Directory.EnumerateFileSystemEntries(oldPhotos).Any()) Directory.Delete(oldPhotos);
            }

            // Documents\MTG Card Scanner\<session> -> Sessions\<session>, "<date> export" -> Exports
            var docs = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "MTG Card Scanner");
            if (Directory.Exists(docs))
                foreach (var d in Directory.GetDirectories(docs))
                {
                    var name = Path.GetFileName(d);
                    string? to = File.Exists(Path.Combine(d, "session.json")) ? Path.Combine(paths.SessionsDir, name)
                               : name.EndsWith(" export", StringComparison.OrdinalIgnoreCase) ? Path.Combine(paths.ExportsDir, name)
                               : null;
                    if (to is not null && !Directory.Exists(to)) CopyDir(d, to);
                }

            // Logs\crops\<session folder> -> Sessions\<session folder>\Crops; other crop folders stay in Logs\Crops
            if (Directory.Exists(paths.LooseCropsDir))
                foreach (var d in Directory.GetDirectories(paths.LooseCropsDir))
                {
                    var session = Path.Combine(paths.SessionsDir, Path.GetFileName(d));
                    var to = Path.Combine(session, "Crops");
                    if (Directory.Exists(session) && !Directory.Exists(to)) Directory.Move(d, to);
                }

            File.WriteAllText(Path.Combine(paths.Root, "README.txt"),
                "MTG Card Scanner data folder\r\n\r\n" +
                "Sessions\\       one folder per scan session: session.json, the CSVs, and Crops\\ (what the scanner saw)\r\n" +
                "Exports\\        CSVs exported outside a session\r\n" +
                "Logs\\           identify_results (every card, how it was read, its bin), errors.log, Crops\\ from outside sessions\r\n" +
                "Phone photos\\   photos the phone or the machine sent, one folder per day\r\n" +
                "catalog\\, cache\\, settings.json   the app's own files (card database, card pictures, your settings)\r\n");
            File.WriteAllText(marker, DateTime.Now.ToString("s"));
        }
        catch (Exception ex) { Log.Error("Move to the data folder", ex); }
    }

    private static void CopyDir(string from, string to)
    {
        Directory.CreateDirectory(to);
        foreach (var f in Directory.GetFiles(from)) File.Copy(f, Path.Combine(to, Path.GetFileName(f)), overwrite: false);
        foreach (var d in Directory.GetDirectories(from)) CopyDir(d, Path.Combine(to, Path.GetFileName(d)));
    }
}
