using CardScanner.Core.Catalog;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace CardScanner.App.ViewModels;

/// <summary>The "getting ready" page: catalog download progress, or an error with a Retry button.</summary>
public partial class SetupViewModel(MainViewModel main) : ObservableObject
{
    [ObservableProperty] private string _message = "Getting ready...";
    [ObservableProperty] private string _detail = "";
    [ObservableProperty] private double _percent;
    [ObservableProperty] private bool _indeterminate = true;
    [ObservableProperty] private bool _failed;

    public void Begin(string message)
    {
        Message = message;
        Detail = "";
        Percent = 0;
        Indeterminate = true;
        Failed = false;
    }

    public void Report(DownloadProgress p)
    {
        Indeterminate = p.BytesTotal == 0;
        Percent = p.Fraction * 100;
        Detail = p.BytesTotal > 0
            ? $"{p.Step} · {p.BytesDone / 1e6:0} of {p.BytesTotal / 1e6:0} MB"
            : p.Step;
    }

    public void Fail(string message)
    {
        Message = message;
        Detail = "";
        Indeterminate = false;
        Failed = true;
    }

    [RelayCommand]
    private Task Retry() => main.DownloadCatalogAsync();
}
