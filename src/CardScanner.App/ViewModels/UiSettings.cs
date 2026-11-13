using System.Text.Json;
using System.Text.Json.Serialization;
using CardScanner.Core;

namespace CardScanner.App.ViewModels;

/// <summary>Where the compare view puts the tags, card info and buttons.</summary>
public enum CompareLayout { Left, Top, Right }

/// <summary>Small per-user preferences, saved as settings.json next to the logs.</summary>
public sealed class UiSettings
{
    [JsonConverter(typeof(JsonStringEnumConverter))]
    public CompareLayout Layout { get; set; } = CompareLayout.Left;

    /// <summary>When the photo can't show foil vs non-foil, call it non-foil instead of asking. Off by default:
    /// those cards go to "Check finish" until the machine's camera can see the foil sheen.</summary>
    public bool AssumeNonFoil { get; set; }

    /// <summary>Listen for the Android scanner app on the local network.</summary>
    public bool PhoneLink { get; set; }

    [JsonIgnore] private string _path = "";

    public static UiSettings Load(AppPaths paths)
    {
        var path = Path.Combine(paths.Root, "settings.json");
        UiSettings s;
        try { s = File.Exists(path) ? JsonSerializer.Deserialize<UiSettings>(File.ReadAllText(path)) ?? new() : new(); }
        catch (Exception ex) { Log.Error("Read settings", ex); s = new(); }
        s._path = path;
        return s;
    }

    public void Save()
    {
        try { File.WriteAllText(_path, JsonSerializer.Serialize(this, new JsonSerializerOptions { WriteIndented = true })); }
        catch (Exception ex) { Log.Error("Save settings", ex); }
    }
}
