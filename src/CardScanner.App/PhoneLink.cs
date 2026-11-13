using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;

namespace CardScanner.App;

/// <summary>
/// Lets the Android scanner app send photos to this PC over Wi-Fi.
///   - UDP 8771: the phone broadcasts "MTGSCAN?" and gets back "MTGSCAN 8770 &lt;PC name&gt;", so nothing has to be typed.
///   - TCP 8770: a tiny HTTP server. GET /api/hello, POST /api/scan (body = one JPEG) → JSON result.
/// Off by default (Settings → Phone link). Windows asks once whether to allow it through the firewall:
/// tick "Private networks".
/// The machine's Pi camera can later use the same POST /api/scan.
/// </summary>
public sealed class PhoneLink
{
    public const int HttpPort = 8770, DiscoveryPort = 8771;
    public static PhoneLink Instance { get; } = new();

    /// <summary>One request from the phone (or the machine's Pi).</summary>
    public sealed record Request(string Method, string Path, IReadOnlyDictionary<string, string> Headers, byte[] Body, string Peer);

    /// <summary>Set by the identify page: answers /api/scan, /api/session/*, /api/undo and /api/status.
    /// Returns the HTTP status and a reply object (serialized to JSON).</summary>
    public Func<Request, Task<(int Code, object Body)>>? Handler { get; set; }

    public event Action<string>? StatusChanged;
    public string Status { get; private set; } = "Phone link is off.";

    private CancellationTokenSource? _cts;
    private TcpListener? _tcp;
    private UdpClient? _udp;
    private int _scans;

    private void SetStatus(string s) { Status = s; StatusChanged?.Invoke(s); }

    public void Start()
    {
        if (_cts is not null) return;
        _cts = new CancellationTokenSource();
        try
        {
            _tcp = new TcpListener(IPAddress.Any, HttpPort);
            _tcp.Start();
            _udp = new UdpClient(new IPEndPoint(IPAddress.Any, DiscoveryPort)) { EnableBroadcast = true };
        }
        catch (Exception ex)
        {
            Log.Error("Phone link start", ex);
            Stop();
            SetStatus($"Phone link couldn't start: {ex.Message}");
            return;
        }
        var ct = _cts.Token;
        _ = Task.Run(() => AcceptLoop(ct));
        _ = Task.Run(() => DiscoveryLoop(ct));
        SetStatus($"Phone link on · {Addresses()} · waiting for the phone");
    }

    public void Stop()
    {
        _cts?.Cancel();
        try { _tcp?.Stop(); } catch { }
        try { _udp?.Dispose(); } catch { }
        _cts = null; _tcp = null; _udp = null;
        SetStatus("Phone link is off.");
    }

    public const string FirewallRule = "MTG Card Scanner phone link";

    /// <summary>
    /// Opens the phone link's two ports to the local network only (remoteip=localsubnet), on every network type,
    /// after removing any rule for this app that Windows made when its "allow" prompt was dismissed (a block
    /// rule beats an allow rule). Shows the Windows admin prompt; returns false if that was declined.
    /// </summary>
    public static async Task<bool> AllowThroughFirewallAsync()
    {
        var exe = Environment.ProcessPath ?? "";
        var cmd = string.Join(" & ",
            $"netsh advfirewall firewall delete rule name=all program=\"{exe}\"",
            $"netsh advfirewall firewall delete rule name=\"{FirewallRule}\"",
            $"netsh advfirewall firewall add rule name=\"{FirewallRule}\" dir=in action=allow protocol=TCP localport={HttpPort} remoteip=localsubnet profile=any",
            $"netsh advfirewall firewall add rule name=\"{FirewallRule}\" dir=in action=allow protocol=UDP localport={DiscoveryPort} remoteip=localsubnet profile=any");
        var psi = new System.Diagnostics.ProcessStartInfo("cmd.exe", "/c " + cmd)
        {
            UseShellExecute = true, Verb = "runas", WindowStyle = System.Diagnostics.ProcessWindowStyle.Hidden,
        };
        try
        {
            using var p = System.Diagnostics.Process.Start(psi);
            if (p is null) return false;
            await p.WaitForExitAsync();
            return p.ExitCode == 0;
        }
        catch (System.ComponentModel.Win32Exception) { return false; }   // admin prompt declined
    }

    /// <summary>This PC's Wi-Fi / Ethernet addresses, for typing into the phone if discovery is blocked.</summary>
    public static string Addresses()
    {
        try
        {
            var ips = System.Net.NetworkInformation.NetworkInterface.GetAllNetworkInterfaces()
                .Where(n => n.OperationalStatus == System.Net.NetworkInformation.OperationalStatus.Up
                            && n.NetworkInterfaceType != System.Net.NetworkInformation.NetworkInterfaceType.Loopback)
                .SelectMany(n => n.GetIPProperties().UnicastAddresses)
                .Where(a => a.Address.AddressFamily == AddressFamily.InterNetwork)
                .Select(a => a.Address.ToString())
                .Where(a => !a.StartsWith("169.254."))
                .Distinct().ToList();
            return ips.Count == 0 ? "no network" : string.Join(", ", ips);
        }
        catch { return "?"; }
    }

    private async Task DiscoveryLoop(CancellationToken ct)
    {
        var udp = _udp!;
        var reply = Encoding.UTF8.GetBytes($"MTGSCAN {HttpPort} {Environment.MachineName}");
        while (!ct.IsCancellationRequested)
        {
            try
            {
                var r = await udp.ReceiveAsync(ct);
                if (Encoding.UTF8.GetString(r.Buffer).StartsWith("MTGSCAN?"))
                    await udp.SendAsync(reply, reply.Length, r.RemoteEndPoint);
            }
            catch (OperationCanceledException) { break; }
            catch (ObjectDisposedException) { break; }
            catch (Exception ex) { Log.Error("Phone link discovery", ex); await Task.Delay(500, ct).ContinueWith(_ => { }); }
        }
    }

    private async Task AcceptLoop(CancellationToken ct)
    {
        var tcp = _tcp!;
        while (!ct.IsCancellationRequested)
        {
            TcpClient client;
            try { client = await tcp.AcceptTcpClientAsync(ct); }
            catch { break; }
            _ = Task.Run(() => Serve(client, ct));
        }
    }

    private async Task Serve(TcpClient client, CancellationToken ct)
    {
        using var _ = client;
        client.ReceiveTimeout = 30000; client.SendTimeout = 30000;
        var stream = client.GetStream();
        try
        {
            var (method, path, headers, body) = await ReadRequest(stream, ct);
            string peer = (client.Client.RemoteEndPoint as IPEndPoint)?.Address.ToString() ?? "phone";
            if (method == "GET" && path == "/api/hello")
            {
                SetStatus($"Phone link on · {Addresses()} · phone connected ({peer})");
                await Reply(stream, 200, new { app = "MTG Card Scanner", pc = Environment.MachineName, version = ViewModels.MainViewModel.AppVersion });
            }
            else if (path.StartsWith("/api/"))
            {
                if (Handler is null) { await Reply(stream, 503, new { ok = false, error = "The PC app is still loading the card database." }); return; }
                if (path == "/api/scan" && body.Length < 1000) { await Reply(stream, 400, new { ok = false, error = "No photo in the request." }); return; }
                var (code, result) = await Handler(new Request(method, path, headers, body, peer));
                if (path == "/api/scan")
                {
                    _scans++;
                    SetStatus($"Phone link on · {Addresses()} · {_scans} scan{(_scans == 1 ? "" : "s")} from {peer}");
                }
                await Reply(stream, code, result);
            }
            else await Reply(stream, 404, new { ok = false, error = "Unknown request." });
        }
        catch (Exception ex)
        {
            Log.Error("Phone link request", ex);
            try { await Reply(stream, 500, new { ok = false, error = ex.Message }); } catch { }
        }
    }

    private const int MaxBody = 40 * 1024 * 1024;

    private static async Task<(string Method, string Path, Dictionary<string, string> Headers, byte[] Body)> ReadRequest(
        NetworkStream s, CancellationToken ct)
    {
        // headers: read until CRLFCRLF
        var head = new List<byte>(1024);
        var one = new byte[1];
        while (true)
        {
            int n = await s.ReadAsync(one, ct);
            if (n == 0) throw new IOException("Connection closed");
            head.Add(one[0]);
            int c = head.Count;
            if (c >= 4 && head[c - 4] == '\r' && head[c - 3] == '\n' && head[c - 2] == '\r' && head[c - 1] == '\n') break;
            if (c > 16384) throw new IOException("Header too large");
        }
        var lines = Encoding.ASCII.GetString(head.ToArray()).Split("\r\n", StringSplitOptions.RemoveEmptyEntries);
        var first = lines[0].Split(' ');
        var headers = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (var l in lines.Skip(1))
        {
            int i = l.IndexOf(':');
            if (i > 0) headers[l[..i].Trim()] = l[(i + 1)..].Trim();
        }
        int len = headers.TryGetValue("Content-Length", out var cl) && int.TryParse(cl, out var v) ? v : 0;
        if (len < 0 || len > MaxBody) throw new IOException("Body too large");
        var body = new byte[len];
        int read = 0;
        while (read < len)
        {
            int n = await s.ReadAsync(body.AsMemory(read, len - read), ct);
            if (n == 0) throw new IOException("Connection closed early");
            read += n;
        }
        return (first[0].ToUpperInvariant(), first.Length > 1 ? first[1].Split('?')[0] : "/", headers, body);
    }

    private static async Task Reply(NetworkStream s, int code, object payload)
    {
        var json = JsonSerializer.SerializeToUtf8Bytes(payload, new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase });
        var text = code switch { 200 => "OK", 400 => "Bad Request", 404 => "Not Found", 409 => "Conflict", 503 => "Service Unavailable", _ => "Error" };
        var hdr = Encoding.ASCII.GetBytes(
            $"HTTP/1.1 {code} {text}\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: {json.Length}\r\nConnection: close\r\n\r\n");
        await s.WriteAsync(hdr);
        await s.WriteAsync(json);
        await s.FlushAsync();
    }
}
