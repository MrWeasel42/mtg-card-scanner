using System.Collections.ObjectModel;
using System.Globalization;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using Avalonia.Media.Imaging;
using Avalonia.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace CardScanner.App.ViewModels;

/// <summary>A bin on the machine page: its label, how many cards went in, how full it is.</summary>
public sealed record MachineBin(int Bin, string Label, int Count, double Level, bool IsEnd, bool IsHit)
{
    public string Title => IsEnd ? $"BIN {Bin} · END" : $"BIN {Bin}";
    public bool HasLevel => Level >= 0;
}

/// <summary>The bin the last card went to gets a teal edge.</summary>
public static class MachineBrushes
{
    public static readonly Avalonia.Data.Converters.FuncValueConverter<bool, Avalonia.Media.IBrush> Hit =
        new(hit => hit ? new Avalonia.Media.SolidColorBrush(Avalonia.Media.Color.Parse("#2DD4BF")) : Avalonia.Media.Brushes.Transparent);
}

/// <summary>A session kept on the machine.</summary>
public sealed record MachineSession(string Id, string Name, string Summary, string State, int ToReview)
{
    public string Tag => State == "finished" ? "finished" : State == "running" ? "running" : "not finished";
    public string ReviewText => ToReview > 0 ? $"⚑ {ToReview} to review" : "";
}

/// <summary>
/// The card sorter, from the PC: the same controls as its touchscreen (status, the run, pause / stop / emergency
/// stop, the setup tools, identify-on, updates) through the machine's own API (machine/sorter/app.py). Reviewing a
/// machine session opens the machine's page in the browser (the same review screen as on the touchscreen); finished
/// sessions are also copied to this PC automatically.
/// </summary>
public partial class MachineViewModel : ObservableObject
{
    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(8) };
    private readonly MainViewModel _main;
    private readonly DispatcherTimer _timer;
    private bool _polling;
    private int _lastPhotoN = -1;
    private string _lastPhotoSession = "";
    private string? _armed;                    // a button that needs a second click to confirm
    private DateTime _armedAt;

    public IdentifyViewModel Scan { get; }
    public ObservableCollection<MachineBin> Bins { get; } = [];
    public ObservableCollection<MachineSession> Sessions { get; } = [];

    public static readonly string[] IdentifyOnList = ["PC, else the machine", "PC only", "Machine only"];
    private static readonly string[] IdentifyOnKeys = ["auto", "pc", "machine"];
    public static readonly string[] PriceShowList = ["Last card", "Highest so far", "Both"];
    private static readonly string[] PriceShowKeys = ["last", "top", "both"];

    [ObservableProperty] private string _host = "sorter.local";
    [ObservableProperty] private bool _online;
    [ObservableProperty] private string _statusText = "Looking for the machine…";
    [ObservableProperty] private string _chipsText = "";
    [ObservableProperty] private string _state = "";
    [ObservableProperty] private bool _hasSession;
    [ObservableProperty] private string _sessionName = "";
    [ObservableProperty] private string _sessionLine = "";
    [ObservableProperty] private string _statsText = "";
    [ObservableProperty] private string _lastCardName = "";
    [ObservableProperty] private string _lastCardLine = "";
    [ObservableProperty] private Bitmap? _lastPhoto;
    [ObservableProperty] private string _alertText = "";
    [ObservableProperty] private string _alertKind = "";
    [ObservableProperty] private bool _isRunning;
    [ObservableProperty] private bool _isPaused;
    [ObservableProperty] private bool _isStopped;
    [ObservableProperty] private int _toReview;
    [ObservableProperty] private string _toolOutput = "Pick a tool. Tools only work while nothing is sorting.";
    [ObservableProperty] private string _confirmText = "";
    [ObservableProperty] private string _versionText = "";
    [ObservableProperty] private string _updateText = "";
    [ObservableProperty] private bool _updateAvailable;
    [ObservableProperty] private string _machineIdText = "";
    private string _identifyOnKey = "auto";
    private string _priceShowKey = "both";
    private bool _lightsOn;
    private string _sessionId = "";

    public bool HasAlert => AlertText.Length > 0;
    public bool IsJam => AlertKind == "jam";
    public bool IsEStop => AlertKind == "estop";
    public bool CanStart => Online && !IsRunning && !IsStopped;
    public string WebAddress => $"http://{Host}:8080";
    partial void OnAlertTextChanged(string value) => OnPropertyChanged(nameof(HasAlert));
    partial void OnAlertKindChanged(string value) { OnPropertyChanged(nameof(IsJam)); OnPropertyChanged(nameof(IsEStop)); }
    partial void OnOnlineChanged(bool value) => OnPropertyChanged(nameof(CanStart));
    partial void OnIsRunningChanged(bool value) => OnPropertyChanged(nameof(CanStart));
    partial void OnIsStoppedChanged(bool value) => OnPropertyChanged(nameof(CanStart));
    partial void OnHostChanged(string value) => OnPropertyChanged(nameof(WebAddress));

    public MachineViewModel(MainViewModel main, IdentifyViewModel scan)
    {
        _main = main;
        Scan = scan;
        _timer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1.5) };
        _timer.Tick += async (_, _) => await PollAsync();
    }

    public string IdentifyOn
    {
        get => IdentifyOnList[Math.Max(0, Array.IndexOf(IdentifyOnKeys, _identifyOnKey))];
        set
        {
            int i = Array.IndexOf(IdentifyOnList, value);
            if (i < 0 || IdentifyOnKeys[i] == _identifyOnKey) return;
            _identifyOnKey = IdentifyOnKeys[i];
            _ = PostAsync("settings", new Dictionary<string, object> { ["identifyOn"] = _identifyOnKey });
            OnPropertyChanged();
        }
    }

    public string PriceShow
    {
        get => PriceShowList[Math.Max(0, Array.IndexOf(PriceShowKeys, _priceShowKey))];
        set
        {
            int i = Array.IndexOf(PriceShowList, value);
            if (i < 0 || PriceShowKeys[i] == _priceShowKey) return;
            _priceShowKey = PriceShowKeys[i];
            _ = PostAsync("settings", new Dictionary<string, object> { ["priceShow"] = _priceShowKey });
            OnPropertyChanged();
        }
    }

    /// <summary>Called when the page is shown / left.</summary>
    public void Show()
    {
        Host = Scan.MachineHost;
        _timer.Start();
        _ = PollAsync();
        _ = LoadSessionsAsync();
    }

    public void Hide() => _timer.Stop();

    private string Url(string path) => $"http://{Host}:8080/api/{path}";

    private async Task<JsonElement?> GetAsync(string path)
    {
        try
        {
            using var doc = JsonDocument.Parse(await Http.GetStringAsync(Url(path)));
            return doc.RootElement.Clone();
        }
        catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException or JsonException) { return null; }
    }

    private async Task<JsonElement?> PostAsync(string path, object? body = null)
    {
        try
        {
            using var r = await Http.PostAsJsonAsync(Url(path), body ?? new { });
            using var doc = JsonDocument.Parse(await r.Content.ReadAsStringAsync());
            var e = doc.RootElement.Clone();
            if (e.TryGetProperty("ok", out var ok) && ok.ValueKind == JsonValueKind.False && e.TryGetProperty("error", out var err))
                ToolOutput = "⚠ " + err.GetString();
            _ = PollAsync();
            return e;
        }
        catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException or JsonException)
        {
            ToolOutput = $"⚠ The machine didn't answer ({ex.Message}).";
            return null;
        }
    }

    private static string S(JsonElement e, string name) =>
        e.ValueKind == JsonValueKind.Object && e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() ?? "" : "";
    private static int I(JsonElement e, string name) =>
        e.ValueKind == JsonValueKind.Object && e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.Number ? v.GetInt32() : 0;
    private static double? D(JsonElement e, string name) =>
        e.ValueKind == JsonValueKind.Object && e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.Number ? v.GetDouble() : null;
    private static bool B(JsonElement e, string name) =>
        e.ValueKind == JsonValueKind.Object && e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.True;
    private static JsonElement O(JsonElement e, string name) =>
        e.ValueKind == JsonValueKind.Object && e.TryGetProperty(name, out var v) ? v : default;
    private static string Money(double? v) => v is null ? "—" : "$" + v.Value.ToString("0.00", CultureInfo.InvariantCulture);

    private async Task PollAsync()
    {
        if (_polling) return;
        _polling = true;
        try
        {
            var st = await GetAsync("state");
            if (st is not { } s)
            {
                Online = false;
                StatusText = $"Can't reach the machine at {Host}. Is it on, and on the same network as this PC?";
                ChipsText = "";
                return;
            }
            Online = true;
            State = S(s, "state");
            IsPaused = B(s, "paused");
            IsRunning = State is "starting" or "running" or "stopping";
            var pc = O(s, "pc");
            var hw = O(s, "hw");
            string tower = S(hw, "tower") switch { "raw" => "Tower: raw", "single" => "Tower: 1 sleeve", "double" => "Tower: 2 sleeves", _ => "" };
            ChipsText = string.Join("  ·  ", new[]
            {
                B(pc, "online") ? "PC: " + S(pc, "name") : "No PC", "Motors: " + S(hw, "motors"), "Identify: " + S(s, "identifier"), tower,
                B(s, "sim") ? "SIMULATION" : "",
            }.Where(x => x.Length > 0));
            StatusText = State switch
            {
                "running" => IsPaused ? "Paused" : "Sorting",
                "starting" => "Starting…",
                "stopping" => "Clearing the track…",
                "stopped" => "Session stopped: review the flagged cards, then Finish",
                "estop" => "EMERGENCY STOP",
                "error" => "Stopped by a problem",
                _ => "Ready",
            };
            var alert = O(s, "alert");
            AlertKind = S(alert, "kind");
            AlertText = S(alert, "text");
            var settings = O(s, "settings");
            var idk = S(settings, "identifyOn");
            if (idk.Length > 0 && idk != _identifyOnKey) { _identifyOnKey = idk; OnPropertyChanged(nameof(IdentifyOn)); }
            var psk = S(settings, "priceShow");
            if (psk.Length > 0 && psk != _priceShowKey) { _priceShowKey = psk; OnPropertyChanged(nameof(PriceShow)); }
            var mid = O(s, "machineId");
            var avg = D(mid, "avgMs");
            MachineIdText = (S(mid, "detail") is { Length: > 0 } d ? d : S(mid, "state"))
                          + (avg is { } a ? $" · about {a / 1000:0.0} s per card" : "");
            VersionText = S(s, "version");
            var u = O(s, "update");
            UpdateAvailable = B(u, "available");
            UpdateText = UpdateAvailable ? "Update available: " + S(u, "latest") : S(u, "error") is { Length: > 0 } ue ? ue : "Up to date (it checks every 30 min).";

            var ss = O(s, "session");
            HasSession = ss.ValueKind == JsonValueKind.Object;
            IsStopped = State == "stopped" && HasSession;
            if (!HasSession)
            {
                SessionName = ""; SessionLine = ""; StatsText = ""; LastCardName = ""; LastCardLine = ""; LastPhoto = null;
                Bins.Clear();
                _lastPhotoN = -1;
                return;
            }
            _sessionId = S(ss, "id");
            SessionName = S(ss, "name");
            ToReview = I(ss, "toReview");
            int cards = I(ss, "cards");
            SessionLine = $"{S(ss, "mode")} · {StatusText.ToLowerInvariant()} · identifying on {S(s, "identifier")}";
            var top = O(ss, "top");
            StatsText = $"{cards} cards  ·  {D(s, "rate") ?? 0:0.0} per min  ·  {I(ss, "flagged")} flagged  ·  total {Money(D(ss, "total"))}"
                      + (top.ValueKind == JsonValueKind.Object ? $"  ·  highest {S(top, "name")} {Money(D(top, "price"))}" : "");
            var lc = O(s, "lastCard");
            int hitBin = I(lc, "bin");
            if (lc.ValueKind == JsonValueKind.Object)
            {
                LastCardName = S(lc, "name");
                LastCardLine = $"{S(lc, "set")} {S(lc, "setCode")} #{S(lc, "number")} · → bin {hitBin} · "
                             + (B(lc, "flagged") ? "Flagged: " + S(lc, "flagReason") : S(lc, "binLabel")) + " · " + Money(D(lc, "price"));
                int n = I(lc, "n");
                if (n != _lastPhotoN || _sessionId != _lastPhotoSession) await LoadPhotoAsync(_sessionId, n);
            }
            else { LastCardName = S(s, "phase") == "homing" ? "Homing the belt…" : "Waiting for the first card…"; LastCardLine = ""; }

            var labels = O(ss, "binLabels");
            var counts = O(ss, "binCounts");
            var levels = O(s, "levels");
            int inUse = I(ss, "binsInUse");
            var list = new List<MachineBin>();
            if (labels.ValueKind == JsonValueKind.Array)
            {
                int i = 0;
                foreach (var l in labels.EnumerateArray())
                {
                    i++;
                    int count = counts.ValueKind == JsonValueKind.Object && counts.TryGetProperty(i.ToString(CultureInfo.InvariantCulture), out var c) && c.ValueKind == JsonValueKind.Number ? c.GetInt32() : 0;
                    double level = levels.ValueKind == JsonValueKind.Array && levels.GetArrayLength() >= i && levels[i - 1].ValueKind == JsonValueKind.Number ? levels[i - 1].GetDouble() : -1;
                    list.Add(new MachineBin(i, l.GetString() ?? "", count, level, i == inUse, i == hitBin));
                }
            }
            if (!list.SequenceEqual(Bins)) { Bins.Clear(); foreach (var b in list) Bins.Add(b); }
        }
        catch (Exception ex) { Log.Error("Machine page", ex); }
        finally { _polling = false; }
    }

    private async Task LoadPhotoAsync(string sid, int n)
    {
        try
        {
            var bytes = await Http.GetByteArrayAsync(Url($"sessions/{sid}/photo/{n}"));
            using var ms = new MemoryStream(bytes);
            LastPhoto = Bitmap.DecodeToWidth(ms, 480);
            _lastPhotoN = n;
            _lastPhotoSession = sid;
        }
        catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException or ArgumentException or InvalidOperationException) { }
    }

    private async Task LoadSessionsAsync()
    {
        var r = await GetAsync("sessions");
        Sessions.Clear();
        if (r is not { } e || !e.TryGetProperty("sessions", out var arr)) return;
        foreach (var s in arr.EnumerateArray().Take(12))
        {
            string when = DateTime.TryParse(S(s, "started"), CultureInfo.InvariantCulture, DateTimeStyles.None, out var t) ? t.ToString("ddd MMM d, h:mm tt") : "";
            Sessions.Add(new MachineSession(S(s, "id"), S(s, "name"),
                $"{when} · {S(s, "mode")} · {I(s, "cards")} cards · {Money(D(s, "total"))}", S(s, "state"), I(s, "toReview")));
        }
    }

    /// <summary>Dangerous buttons take a second click within 4 seconds.</summary>
    private bool Confirmed(string key, string ask)
    {
        if (_armed == key && DateTime.Now - _armedAt < TimeSpan.FromSeconds(4)) { _armed = null; ConfirmText = ""; return true; }
        _armed = key;
        _armedAt = DateTime.Now;
        ConfirmText = ask;
        return false;
    }

    [RelayCommand] private Task Pause() => PostAsync("session/pause");
    [RelayCommand] private Task Resume() => PostAsync("session/resume");
    [RelayCommand] private async Task Stop() { if (Confirmed("stop", "Click ■ Stop again to stop feeding (cards on the track still go to their bins).")) await PostAsync("session/stop"); }
    [RelayCommand] private Task EStop() => PostAsync("estop");
    [RelayCommand] private Task CarryOn() => PostAsync("session/continue");
    [RelayCommand] private Task ResetMotors() => PostAsync("reset");
    [RelayCommand] private async Task EndSession() { if (Confirmed("end", "Click End again: take any cards off the track first.")) await PostAsync("session/stop"); }

    [RelayCommand]
    private async Task Finish()
    {
        var r = await PostAsync("session/finish");
        if (r is { } e && B(e, "ok")) { ToolOutput = "Session finished and saved. It's copied to this PC within a minute."; await LoadSessionsAsync(); }
    }

    /// <summary>Starts a session on the machine with this PC's default setup (Settings → Default session setup).</summary>
    [RelayCommand]
    private async Task StartWithMySetup()
    {
        var r = await PostAsync("session/start", new { name = "", mode = Scan.Settings.CatalogMode ? "Catalog" : "Sort", setup = Scan.Settings.Bins });
        if (r is { } e && B(e, "ok")) ToolOutput = "Started with this PC's default bins.";
    }

    [RelayCommand]
    private async Task Tool(string? name)
    {
        if (string.IsNullOrEmpty(name)) return;
        ToolOutput = "Working…";
        var r = await PostAsync("tools/" + name);
        if (r is { } e && B(e, "ok")) ToolOutput = S(e, "text") is { Length: > 0 } t ? t : "Done.";
    }

    [RelayCommand]
    private async Task Lights()
    {
        _lightsOn = !_lightsOn;
        await PostAsync("lights", new { on = _lightsOn });
        ToolOutput = "Lights " + (_lightsOn ? "on" : "off");
    }

    [RelayCommand] private Task CheckUpdate() => PostAsync("update/check");

    [RelayCommand]
    private async Task InstallUpdate()
    {
        if (!Confirmed("update", "Click Update again: the machine restarts its software (about 30 seconds).")) return;
        await PostAsync("update/install");
        ToolOutput = "Updating… the machine comes back by itself.";
    }

    [RelayCommand]
    private async Task Shutdown()
    {
        if (!Confirmed("shutdown", "Click Shut down again. Wait 20 seconds after its screen goes dark before unplugging.")) return;
        await PostAsync("shutdown");
    }

    [RelayCommand] private Task RefreshSessions() => LoadSessionsAsync();

    /// <summary>The machine's own page (review, downloads), in the browser.</summary>
    [RelayCommand] private void OpenWeb() => OpenUrl(WebAddress);
    [RelayCommand] private void OpenBackups() => HomeViewModel.OpenFolder(Path.Combine(IdentifyViewModel.ExportFolder, "Machine"));

    private static void OpenUrl(string url)
    {
        try { System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(url) { UseShellExecute = true }); }
        catch (Exception ex) { Log.Error("Open machine page", ex); }
    }

    [RelayCommand] private void Back() { Hide(); _main.GoBack(); }
}
