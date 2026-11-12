using CardScanner.Core;
using CardScanner.Core.Catalog;

namespace CardScanner.App;

/// <summary>
/// Card pictures fetched from Scryfall the first time and cached on disk. Uses Scryfall's
/// "large" images so the compare view stays sharp. If you're offline, results still work;
/// you just won't see the pictures.
/// </summary>
public sealed class ThumbnailCache(AppPaths paths)
{
    private static readonly HttpClient Http = CatalogUpdater.CreateHttpClient();
    private static readonly SemaphoreSlim Limit = new(4);

    /// <summary>Local path of the card's large image, downloading it if needed; null if unavailable.</summary>
    public async Task<string?> GetPathAsync(CardInfo card)
    {
        if (string.IsNullOrEmpty(card.ImageUrl) || !card.ImageUrl.StartsWith("https://")) return null;
        var file = Path.Combine(paths.ThumbnailDir, card.Id + "_large.jpg");
        if (File.Exists(file)) return file;
        await Limit.WaitAsync();
        try
        {
            if (File.Exists(file)) return file;
            var url = card.ImageUrl.Replace("/normal/", "/large/");
            byte[] bytes;
            try { bytes = await Http.GetByteArrayAsync(url); }
            catch { bytes = await Http.GetByteArrayAsync(card.ImageUrl); } // fall back to the normal size
            var tmp = file + ".tmp";
            await File.WriteAllBytesAsync(tmp, bytes);
            File.Move(tmp, file, overwrite: true);
            return file;
        }
        catch
        {
            return null;
        }
        finally
        {
            Limit.Release();
        }
    }
}
