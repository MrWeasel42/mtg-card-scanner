using Avalonia.Media.Imaging;
using CardScanner.Core;
using CardScanner.Core.Catalog;

namespace CardScanner.App;

/// <summary>
/// Card pictures for the results list, fetched from Scryfall the first time and cached on disk.
/// If you're offline, results still work; you just won't see the pictures.
/// </summary>
public sealed class ThumbnailCache(AppPaths paths)
{
    private static readonly HttpClient Http = CatalogUpdater.CreateHttpClient();
    private static readonly SemaphoreSlim Limit = new(4);

    public async Task<Bitmap?> GetAsync(CardInfo card)
    {
        if (string.IsNullOrEmpty(card.ImageUrl) || !card.ImageUrl.StartsWith("https://")) return null;
        var file = Path.Combine(paths.ThumbnailDir, card.Id + ".jpg");
        try
        {
            if (!File.Exists(file))
            {
                await Limit.WaitAsync();
                try
                {
                    var bytes = await Http.GetByteArrayAsync(card.ImageUrl);
                    await File.WriteAllBytesAsync(file, bytes);
                }
                finally { Limit.Release(); }
            }
            return new Bitmap(file);
        }
        catch
        {
            return null;
        }
    }
}
