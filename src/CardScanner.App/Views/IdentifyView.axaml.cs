using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Interactivity;
using Avalonia.Platform.Storage;
using CardScanner.App.ViewModels;

namespace CardScanner.App.Views;

public partial class IdentifyView : UserControl
{
    public IdentifyView()
    {
        InitializeComponent();
        AddHandler(DragDrop.DragOverEvent, OnDragOver);
        AddHandler(DragDrop.DragLeaveEvent, (_, _) => DropZone.Classes.Remove("hover"));
        AddHandler(DragDrop.DropEvent, OnDrop);
        AddButton.Click += OnAddClicked;
    }

    // Keyboard shortcuts in the compare view: Esc closes, arrows switch options, Enter picks.
    protected override void OnAttachedToVisualTree(Avalonia.VisualTreeAttachmentEventArgs e)
    {
        base.OnAttachedToVisualTree(e);
        TopLevel.GetTopLevel(this)?.AddHandler(KeyDownEvent, OnKeyDown, RoutingStrategies.Tunnel);
    }

    protected override void OnDetachedFromVisualTree(Avalonia.VisualTreeAttachmentEventArgs e)
    {
        TopLevel.GetTopLevel(this)?.RemoveHandler(KeyDownEvent, OnKeyDown);
        base.OnDetachedFromVisualTree(e);
    }

    private void OnKeyDown(object? sender, KeyEventArgs e)
    {
        if (Vm?.Compare is not { } c) return;
        switch (e.Key)
        {
            case Key.Escape: c.CloseCommand.Execute(null); e.Handled = true; break;
            case Key.Left: c.PreviousCommand.Execute(null); e.Handled = true; break;
            case Key.Right: c.NextCommand.Execute(null); e.Handled = true; break;
            case Key.Enter: c.PickThisCommand.Execute(null); e.Handled = true; break;
            case Key.Z: c.ToggleZoomCommand.Execute(null); e.Handled = true; break;
        }
    }

    private IdentifyViewModel? Vm => DataContext as IdentifyViewModel;

    private void OnDragOver(object? sender, DragEventArgs e)
    {
        e.DragEffects = e.Data.Contains(DataFormats.Files) ? DragDropEffects.Copy : DragDropEffects.None;
        if (!DropZone.Classes.Contains("hover")) DropZone.Classes.Add("hover");
    }

    private async void OnDrop(object? sender, DragEventArgs e)
    {
        DropZone.Classes.Remove("hover");
        var paths = e.Data.GetFiles()?.Select(f => f.TryGetLocalPath()).OfType<string>().ToList();
        if (paths is { Count: > 0 } && Vm is { } vm)
            await vm.AddFilesAsync(paths);
    }

    private async void OnAddClicked(object? sender, RoutedEventArgs e)
    {
        var top = TopLevel.GetTopLevel(this);
        if (top is null || Vm is not { } vm) return;
        var files = await top.StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
        {
            Title = "Choose card photos",
            AllowMultiple = true,
            FileTypeFilter =
            [
                new FilePickerFileType("Photos") { Patterns = IdentifyViewModel.ImageExtensions.Select(x => "*" + x).ToArray() },
            ],
        });
        var paths = files.Select(f => f.TryGetLocalPath()).OfType<string>().ToList();
        if (paths.Count > 0) await vm.AddFilesAsync(paths);
    }
}
