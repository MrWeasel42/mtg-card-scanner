using System.Text.Json;
using System.Text.Json.Serialization;

namespace CardScanner.Core.Catalog;

/// <summary>Describes a published catalog pack (written by catalog-builder/build.py).</summary>
public sealed class CatalogManifest
{
    [JsonPropertyName("format")] public int Format { get; set; }
    [JsonPropertyName("catalog_version")] public string CatalogVersion { get; set; } = "";
    [JsonPropertyName("built_at")] public string BuiltAt { get; set; } = "";
    [JsonPropertyName("cards")] public int Cards { get; set; }
    [JsonPropertyName("fingerprints")] public int FingerprintCount { get; set; }
    [JsonPropertyName("model")] public ModelInfo Model { get; set; } = new();
    [JsonPropertyName("files")] public Dictionary<string, FileInfoEntry> Files { get; set; } = new();

    public static CatalogManifest Parse(string json) =>
        JsonSerializer.Deserialize<CatalogManifest>(json)
        ?? throw new InvalidDataException("Empty catalog manifest");

    public static CatalogManifest? TryLoad(string path)
    {
        try { return File.Exists(path) ? Parse(File.ReadAllText(path)) : null; }
        catch { return null; }
    }
}

public sealed class ModelInfo
{
    [JsonPropertyName("version")] public string Version { get; set; } = "";
    [JsonPropertyName("file")] public string File { get; set; } = "model.onnx";
    [JsonPropertyName("sha256")] public string Sha256 { get; set; } = "";
    [JsonPropertyName("size")] public long Size { get; set; }
    [JsonPropertyName("input_name")] public string InputName { get; set; } = "image";
    [JsonPropertyName("output_name")] public string OutputName { get; set; } = "fingerprint";
    [JsonPropertyName("width")] public int Width { get; set; } = 224;
    [JsonPropertyName("height")] public int Height { get; set; } = 308;
    [JsonPropertyName("mean")] public float[] Mean { get; set; } = [0.485f, 0.456f, 0.406f];
    [JsonPropertyName("std")] public float[] Std { get; set; } = [0.229f, 0.224f, 0.225f];
    [JsonPropertyName("dim")] public int Dim { get; set; } = 384;
}

public sealed class FileInfoEntry
{
    [JsonPropertyName("size")] public long Size { get; set; }
    [JsonPropertyName("sha256")] public string Sha256 { get; set; } = "";
}
