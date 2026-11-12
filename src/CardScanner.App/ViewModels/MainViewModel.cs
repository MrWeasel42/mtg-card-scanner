using Avalonia.Threading;
using CardScanner.Core;
using CardScanner.Core.Catalog;
using CardScanner.Core.Recognition;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace CardScanner.App.ViewModels;

/// <summary>Top level: shows the setup/download page until the catalog is ready, then the main page.</summary>
public partial class MainViewModel : ObservableObject, IDisposable
{
    public static string AppVersion =>
        typeof(MainViewModel).Assembly.GetName().Version is { } v ? $"{v.Major}.{v.Minor}.{v.Build}" : "dev";

    public AppPaths Paths { get; } = Log.Paths;
    private readonly CatalogUpdater _updater;
    private Recognizer? _recognizer;

    [ObservableProperty] private object? _currentPage;
    [ObservableProperty] private string _catalogText = "";
    [ObservableProperty] private bool _updateAvailable;
    [ObservableProperty] private string? _appUpdateText;
    private AppUpdater.Update? _appUpdate;

    public SetupViewModel Setup { get; }

    public MainViewModel()
    {
        _updater = new CatalogUpdater(Paths);
        Setup = new SetupViewModel(this);
        CurrentPage = Setup;
    }

    public async Task StartAsync()
    {
        _ = CheckForAppUpdateAsync();
        if (_updater.HasCatalog)
        {
            await LoadAndShowMainAsync();
            _ = CheckForCatalogUpdateAsync();
        }
        else
        {
            await DownloadCatalogAsync();
        }
    }

    public async Task DownloadCatalogAsync()
    {
        CurrentPage = Setup;
        Setup.Begin("Downloading the card catalog (about 210 MB, one time only)...");
        try
        {
            var progress = new Progress<DownloadProgress>(p => Setup.Report(p));
            await Task.Run(() => _updater.UpdateAsync(progress, beforeSwap: ReleaseCatalogAsync));
            UpdateAvailable = false;
            await LoadAndShowMainAsync();
        }
        catch (Exception ex)
        {
            Log.Error("Catalog download", ex);
            Setup.Fail("Couldn't download the card catalog. Check your internet connection and try again.\n\n" + ex.Message);
        }
    }

    /// <summary>Close the catalog files so the updater can replace them (the main page is reloaded afterwards).</summary>
    private Task ReleaseCatalogAsync()
    {
        var old = _recognizer;
        _recognizer = null;
        old?.Dispose();
        return Task.CompletedTask;
    }

    private async Task LoadAndShowMainAsync()
    {
        Setup.Begin("Loading the card catalog...");
        Setup.Indeterminate = true;
        try
        {
            var old = _recognizer;
            _recognizer = await Task.Run(() => Recognizer.Load(Paths));
            old?.Dispose();
            CatalogText = $"Catalog {_recognizer.Manifest.CatalogVersion} · {_recognizer.Manifest.Cards:N0} printings";
            CurrentPage = new IdentifyViewModel(_recognizer, Paths);
        }
        catch (Exception ex)
        {
            Log.Error("Catalog load", ex);
            Setup.Fail("The card catalog on this computer looks damaged. Click Retry to download it again.\n\n" + ex.Message);
        }
    }

    private async Task CheckForCatalogUpdateAsync()
    {
        try
        {
            bool available = await _updater.IsUpdateAvailableAsync();
            Dispatcher.UIThread.Post(() => UpdateAvailable = available);
        }
        catch { /* offline is fine */ }
    }

    [RelayCommand]
    private Task UpdateCatalog() => DownloadCatalogAsync();

    private async Task CheckForAppUpdateAsync()
    {
        try
        {
            var update = await AppUpdater.CheckAsync(AppVersion);
            if (update is null) return;
            Dispatcher.UIThread.Post(() =>
            {
                _appUpdate = update;
                AppUpdateText = $"App update v{update.Version} available — install";
            });
        }
        catch { /* offline is fine */ }
    }

    [RelayCommand]
    private async Task InstallAppUpdate()
    {
        if (_appUpdate is null) return;
        try
        {
            AppUpdateText = "Downloading update...";
            await AppUpdater.DownloadAndRunAsync(_appUpdate,
                new Progress<double>(p => AppUpdateText = $"Downloading update... {p * 100:0}%"));
            if (Avalonia.Application.Current?.ApplicationLifetime is Avalonia.Controls.ApplicationLifetimes.IClassicDesktopStyleApplicationLifetime d)
                d.Shutdown();
        }
        catch (Exception ex)
        {
            Log.Error("App update", ex);
            AppUpdateText = "Update failed — try again";
        }
    }

    public void Dispose() => _recognizer?.Dispose();
}
