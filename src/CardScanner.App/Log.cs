using CardScanner.Core;

namespace CardScanner.App;

/// <summary>Tiny error log in the app's data folder, so problems can be diagnosed later.</summary>
internal static class Log
{
    private static readonly object Gate = new();
    public static readonly AppPaths Paths = new();

    public static void Error(string what, Exception? ex)
    {
        try
        {
            lock (Gate)
                File.AppendAllText(Path.Combine(Paths.LogsDir, "errors.log"),
                    $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] {what}: {ex}\n\n");
        }
        catch { /* never let logging crash the app */ }
    }
}
