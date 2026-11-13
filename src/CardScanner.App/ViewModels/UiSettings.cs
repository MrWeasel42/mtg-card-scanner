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
