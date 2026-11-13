using Avalonia;
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
        LeftPane.PointerMoved += OnComparePointerMoved;
        RightPane.PointerMoved += OnComparePointerMoved;
        LeftPane.PointerExited += (_, _) => HideLenses();
        RightPane.PointerExited += (_, _) => HideLenses();
        AddButton.Click += OnAddClicked;
        CardsHost.SizeChanged += (_, _) => Resize();
        LeftImg.PropertyChanged += (_, e) => { if (e.Property == Image.SourceProperty) Resize(); };
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
            case Key.M: _magnifier = !_magnifier; if (!_magnifier) HideLenses(); e.Handled = true; break;
            case Key.S: c.SkipCommand.Execute(null); e.Handled = true; break;
            case Key.F: c.FlipCommand.Execute(null); e.Handled = true; break;
            case Key.Back when e.Source is not TextBox: c.LastCardCommand.Execute(null); e.Handled = true; break;
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

    // ---- Card sizing: both pictures the same size, as big as the space allows, captions right underneath ----

    /// <summary>Room kept under the pictures for the captions (name, set, price, rarity / finish).</summary>
    private const double CaptionRoom = 175, LabelRoom = 26, Gap = 120;

    private void Resize()
    {
        var host = CardsHost.Bounds;
        if (host.Width <= 0 || host.Height <= 0) return;
        double aspect = LeftImg.Source is { Size: { Width: > 0, Height: > 0 } sz } ? sz.Width / sz.Height : 63.0 / 88.0;
        double h = Math.Min(host.Height - LabelRoom - CaptionRoom, (host.Width - Gap) / 2 / aspect);
        h = Math.Max(h, 80);
        double w = h * aspect;
        foreach (var img in new[] { LeftImg, RightImg }) { img.Width = w; img.Height = h; }
        foreach (var cap in new[] { LeftCaption, RightCaption }) cap.Width = Math.Max(w, 240);
        HideLenses();
    }

    // ---- Magnifier: a lens that follows the mouse over either card, showing the same spot on both ----

    private const double LensZoom = 2.5, LensSize = 360;
    private bool _magnifier = true;

    private void OnComparePointerMoved(object? sender, PointerEventArgs e)
    {
        if (!_magnifier) return;
        var img = ReferenceEquals(sender, LeftPane) ? LeftImg : RightImg;
        if (!Rendered(img, out var r)) { HideLenses(); return; }
        var p = e.GetPosition(img);
        double u = (p.X - r.X) / r.Width, v = (p.Y - r.Y) / r.Height;
        if (u < 0 || u > 1 || v < 0 || v > 1) { HideLenses(); return; }
        ShowLens(LeftImg, LeftLens, LeftLensImg, u, v);
        ShowLens(RightImg, RightLens, RightLensImg, u, v);
    }

    /// <summary>Where the picture actually sits inside the Image control (Stretch=Uniform letterboxes it).</summary>
    private static bool Rendered(Image img, out Rect r)
    {
        r = default;
        if (img.Source is not { } src || src.Size.Width <= 0 || img.Bounds.Width <= 0) return false;
        var b = img.Bounds.Size;
        double scale = Math.Min(b.Width / src.Size.Width, b.Height / src.Size.Height);
        double w = src.Size.Width * scale, h = src.Size.Height * scale;
        r = new Rect((b.Width - w) / 2, (b.Height - h) / 2, w, h);
        return true;
    }

    private static void ShowLens(Image img, Border lens, Image lensImg, double u, double v)
    {
        if (!Rendered(img, out var r)) { lens.IsVisible = false; return; }
        // The lens lives in a canvas covering the whole pane; the image may sit to one side of it.
        var offset = lens.Parent is Visual canvas ? img.TranslatePoint(default, canvas) ?? default : default;
        r = r.Translate(new Vector(offset.X, offset.Y));
        lensImg.Width = r.Width * LensZoom;
        lensImg.Height = r.Height * LensZoom;
        // The lens stays over the card (slides back near an edge); the magnified spot stays under the pointer.
        double px = r.X + u * r.Width, py = r.Y + v * r.Height;
        double left = Math.Clamp(px - LensSize / 2, r.X, Math.Max(r.X, r.Right - LensSize));
        double top = Math.Clamp(py - LensSize / 2, r.Y, Math.Max(r.Y, r.Bottom - LensSize));
        Canvas.SetLeft(lensImg, (px - left) - u * lensImg.Width);
        Canvas.SetTop(lensImg, (py - top) - v * lensImg.Height);
        Canvas.SetLeft(lens, left);
        Canvas.SetTop(lens, top);
        lens.IsVisible = true;
    }

    private void HideLenses()
    {
        LeftLens.IsVisible = false;
        RightLens.IsVisible = false;
    }
}
