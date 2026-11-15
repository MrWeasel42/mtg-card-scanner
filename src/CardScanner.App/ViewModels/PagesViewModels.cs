using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Text.Json;
using CardScanner.Core;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace CardScanner.App.ViewModels;

/// <summary>A past session on the Home page.</summary>
public sealed record RecentSession(string Name, string When, string Summary, string Folder, bool Finished)
{
    public string StateText => Finished ? "" : "not finished";
}

/// <summary>
/// The page the app opens on (and the logo in the top left goes back to): start or continue a session, the scan
/// page, settings, and the folders where the CSVs, logs and crops are kept.
/// </summary>
public partial class HomeViewModel : ObservableObject
{
    private readonly MainViewModel _main;
    public IdentifyViewModel Scan { get; }
    public ObservableCollection<RecentSession> Recent { get; } = [];

    [ObservableProperty] private string _continueText = "";
    [ObservableProperty] private bool _hasRecent;

    public HomeViewModel(MainViewModel main, IdentifyViewModel scan)
    {
        _main = main;
        Scan = scan;
        Scan.PropertyChanged += OnScanChanged;
        UpdateContinue();
    }

    private void OnScanChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName is nameof(IdentifyViewModel.SessionActive) or nameof(IdentifyViewModel.SessionReviewing)
            or nameof(IdentifyViewModel.SessionTitle) or nameof(IdentifyViewModel.SessionStats))
            UpdateContinue();
    }

    public bool SessionRunning => Scan.SessionActive;

    private void UpdateContinue()
    {
        OnPropertyChanged(nameof(SessionRunning));
        ContinueText = !Scan.SessionActive ? "No session running. Start one, or the phone / machine starts one with the default setup."
                     : Scan.SessionReviewing ? $"{Scan.SessionTitle} · stopped, waiting for review and Finish"
                     : $"{Scan.SessionTitle} · {Scan.SessionStats}";
    }

    /// <summary>Called each time the page is shown.</summary>
    public void Refresh()
    {
        UpdateContinue();
        Recent.Clear();
        try
        {
            var root = IdentifyViewModel.ExportFolder;
            if (Directory.Exists(root))
                foreach (var dir in Directory.GetDirectories(root).OrderByDescending(d => d).Take(30))
                {
                    var json = Path.Combine(dir, "session.json");
                    if (!File.Exists(json)) continue;
                    using var doc = JsonDocument.Parse(File.ReadAllText(json));
                    var r = doc.RootElement;
                    string name = r.TryGetProperty("Name", out var n) ? n.GetString() ?? "" : Path.GetFileName(dir);
                    bool finished = r.TryGetProperty("Ended", out var en) && en.ValueKind == JsonValueKind.String;
                    int cards = r.TryGetProperty("Cards", out var c) ? c.GetInt32() : 0;
                    int flagged = r.TryGetProperty("Flagged", out var f) ? f.GetInt32() : 0;
                    bool catalog = !r.TryGetProperty("Catalog", out var cat) || cat.GetBoolean();
                    string when = r.TryGetProperty("Started", out var st) && st.TryGetDateTime(out var t) ? t.ToString("ddd MMM d, h:mm tt") : "";
                    Recent.Add(new RecentSession(name, when, $"{cards} cards · {flagged} flagged · {(catalog ? "Catalog" : "Sort")}", dir, finished));
                    if (Recent.Count == 6) break;
                }
        }
        catch (Exception ex) { Log.Error("Recent sessions", ex); }
        HasRecent = Recent.Count > 0;
    }

    [RelayCommand]
    private void StartSession()
    {
        _main.ShowScan();
        if (!Scan.SessionActive) Scan.OpenSessionSetupCommand.Execute(null);
    }

    [RelayCommand] private void ContinueSession() => _main.ShowScan();
    [RelayCommand] private void OpenScanPage() => _main.ShowScan();
    [RelayCommand] private void OpenSettings() => _main.ShowSettings();

    [RelayCommand] private void OpenSessionsFolder() => OpenFolder(IdentifyViewModel.ExportFolder);
    [RelayCommand] private void OpenLogsFolder() => OpenFolder(Scan.AppPaths.LogsDir);
    [RelayCommand] private void OpenCropsFolder() => OpenFolder(Path.Combine(Scan.AppPaths.LogsDir, "crops"));
    [RelayCommand] private void OpenPhonePhotosFolder() => OpenFolder(Path.Combine(Scan.AppPaths.Root, "phone_scans"));
    [RelayCommand] private void OpenRecent(RecentSession? s) { if (s is not null) OpenFolder(s.Folder); }

    internal static void OpenFolder(string dir)
    {
        try
        {
            Directory.CreateDirectory(dir);
            System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo("explorer.exe", $"\"{dir}\"") { UseShellExecute = true });
        }
        catch (Exception ex) { Log.Error("Open folder", ex); }
    }
}

/// <summary>Every setting in one place: look, the compare view, finish, phone link, and the default bin setup.</summary>
public partial class SettingsViewModel : ObservableObject
{
    private readonly MainViewModel _main;
    public IdentifyViewModel Scan { get; }

    public static readonly string[] ThemeList = ["Dark", "Light", "System"];
    public static readonly string[] LayoutList = ["Panel on the left", "Panel on the right", "Tags on top"];

    [ObservableProperty] private string _binsSavedText = "";

    public SettingsViewModel(MainViewModel main, IdentifyViewModel scan)
    {
        _main = main;
        Scan = scan;
        Scan.BinEditor.Changed += () => { if (_shown) BinsSavedText = "Not saved yet: press Save as default."; };
    }
    private bool _shown;

    public void Refresh()
    {
        _shown = false;
        Scan.LoadSetupDefaults();
        BinsSavedText = "";
        _shown = true;
        OnPropertyChanged(nameof(Theme));
        OnPropertyChanged(nameof(LayoutChoice));
    }

    public string Theme
    {
        get => Scan.Settings.Theme;
        set
        {
            if (value is null || value == Scan.Settings.Theme) return;
            Scan.Settings.Theme = value;
            Scan.Settings.Save();
            UiSettings.ApplyTheme(value);
            OnPropertyChanged();
        }
    }

    public string LayoutChoice
    {
        get => LayoutList[Scan.Layout switch { CompareLayout.Right => 1, CompareLayout.Top => 2, _ => 0 }];
        set
        {
            if (value is null) return;
            Scan.Layout = Array.IndexOf(LayoutList, value) switch { 1 => CompareLayout.Right, 2 => CompareLayout.Top, _ => CompareLayout.Left };
            OnPropertyChanged();
        }
    }

    [RelayCommand]
    private void SaveBins()
    {
        Scan.SaveSetupDefaults();
        BinsSavedText = $"✓ Saved {DateTime.Now:h:mm tt}. New sessions (and the phone / machine) use this setup.";
    }

    [RelayCommand] private void Back() { _shown = false; _main.GoBack(); }
}
