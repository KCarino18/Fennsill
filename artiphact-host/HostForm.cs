using System.Diagnostics;

namespace ArtiphactHost;

public sealed class HostForm : Form
{
    const int McpPort = 8766;

    readonly string _root;
    readonly string _python;
    readonly string _localMcpUrl = $"http://127.0.0.1:{McpPort}/mcp";
    readonly string _publicUrlFile;

    Process? _server;
    Process? _tunnel;
    System.Windows.Forms.Timer? _poll;

    readonly Label _status = new();
    readonly TextBox _localBox = new();
    readonly TextBox _publicBox = new();
    readonly Label _error = new();
    readonly Button _btnStart = new();
    readonly Button _btnStop = new();
    readonly Button _btnTunnel = new();
    readonly Button _btnCopyUrl = new();
    readonly Button _btnCopySetup = new();
    readonly Button _btnCopyPush = new();

    public HostForm()
    {
        _root = FindProjectRoot();
        _python = FindPython();
        _publicUrlFile = Path.Combine(_root, "connector", "host_public_url.txt");

        Text = "Artiphact Host";
        Width = 680;
        Height = 460;
        MinimumSize = new Size(560, 380);
        StartPosition = FormStartPosition.CenterScreen;
        Font = new Font("Segoe UI", 10f);

        var tip = new Label
        {
            AutoSize = false,
            Dock = DockStyle.Top,
            Height = 52,
            Padding = new Padding(14, 12, 14, 4),
            Text = "Starts the hosted MCP for Claude / ChatGPT. Keep this window open while they use the connector.",
        };

        var bar = new FlowLayoutPanel
        {
            Dock = DockStyle.Top,
            Height = 44,
            Padding = new Padding(12, 4, 12, 4),
            WrapContents = false,
        };
        _btnStart.Text = "Start server";
        _btnStart.AutoSize = true;
        _btnStart.Click += (_, _) => StartServer();
        _btnStop.Text = "Stop server";
        _btnStop.AutoSize = true;
        _btnStop.Enabled = false;
        _btnStop.Click += (_, _) => StopAll();
        _btnTunnel.Text = "Start public link";
        _btnTunnel.AutoSize = true;
        _btnTunnel.Enabled = false;
        _btnTunnel.Click += (_, _) => StartTunnel();
        bar.Controls.AddRange([_btnStart, _btnStop, _btnTunnel]);

        _status.Dock = DockStyle.Top;
        _status.Height = 28;
        _status.Padding = new Padding(14, 4, 14, 0);
        _status.Text = "Stopped";

        var grid = new TableLayoutPanel
        {
            Dock = DockStyle.Top,
            Height = 90,
            ColumnCount = 3,
            RowCount = 2,
            Padding = new Padding(12, 8, 12, 0),
        };
        grid.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 100));
        grid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        grid.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 120));
        grid.Controls.Add(new Label { Text = "Local MCP:", AutoSize = true, Anchor = AnchorStyles.Left }, 0, 0);
        _localBox.Text = _localMcpUrl;
        _localBox.ReadOnly = true;
        _localBox.Dock = DockStyle.Fill;
        grid.Controls.Add(_localBox, 1, 0);
        var copyLocal = new Button { Text = "Copy", Dock = DockStyle.Fill };
        copyLocal.Click += (_, _) => CopyText(_localMcpUrl);
        grid.Controls.Add(copyLocal, 2, 0);

        grid.Controls.Add(new Label { Text = "Public MCP:", AutoSize = true, Anchor = AnchorStyles.Left }, 0, 1);
        _publicBox.Text = "(start public link)";
        _publicBox.ReadOnly = true;
        _publicBox.Dock = DockStyle.Fill;
        grid.Controls.Add(_publicBox, 1, 1);
        _btnCopyUrl.Text = "Copy MCP URL";
        _btnCopyUrl.Dock = DockStyle.Fill;
        _btnCopyUrl.Click += (_, _) => CopyPublicMcp();
        grid.Controls.Add(_btnCopyUrl, 2, 1);

        var prompts = new FlowLayoutPanel
        {
            Dock = DockStyle.Top,
            Height = 44,
            Padding = new Padding(12, 8, 12, 4),
            WrapContents = false,
        };
        _btnCopySetup.Text = "Copy setup prompt";
        _btnCopySetup.AutoSize = true;
        _btnCopySetup.Click += (_, _) => CopyFilledPrompt("remote_mcp_setup.md");
        _btnCopyPush.Text = "Copy panel prompt";
        _btnCopyPush.AutoSize = true;
        _btnCopyPush.Click += (_, _) => CopyFilledPrompt("remote_mcp_push.md");
        prompts.Controls.AddRange([_btnCopySetup, _btnCopyPush]);

        _error.Dock = DockStyle.Fill;
        _error.ForeColor = Color.Firebrick;
        _error.Padding = new Padding(14, 8, 14, 8);
        _error.Text = "";

        Controls.Add(_error);
        Controls.Add(prompts);
        Controls.Add(grid);
        Controls.Add(_status);
        Controls.Add(bar);
        Controls.Add(tip);

        FormClosing += (_, _) => StopAll();

        _poll = new System.Windows.Forms.Timer { Interval = 1000 };
        _poll.Tick += (_, _) => ReadPublicUrlFile();
        _poll.Start();
    }

    static string FindProjectRoot()
    {
        var env = Environment.GetEnvironmentVariable("ARTIPHACT_ROOT");
        if (!string.IsNullOrWhiteSpace(env) && HasConnector(env)) return env;

        // Same canonical root as Artiphact.exe — gallery + MCP share pages.
        var installed = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Artiphact");
        if (HasConnector(installed)) return installed;

        foreach (var start in new[]
                 {
                     AppContext.BaseDirectory,
                     Directory.GetCurrentDirectory(),
                     Path.GetDirectoryName(Environment.ProcessPath) ?? "",
                 })
        {
            var dir = start;
            for (var i = 0; i < 8 && !string.IsNullOrEmpty(dir); i++)
            {
                if (HasConnector(dir)) return dir;
                dir = Path.GetDirectoryName(dir) ?? "";
            }
        }

        var desk = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),
            "This Is A Test For The Tablet");
        if (HasConnector(desk)) return desk;

        return Directory.GetCurrentDirectory();
    }

    static bool HasConnector(string root) =>
        File.Exists(Path.Combine(root, "connector", "mcp_http_server.py"))
        || File.Exists(Path.Combine(root, "connector", "mcp_server.py"));

    static string FindPython()
    {
        var local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        var candidates = new[]
        {
            Path.Combine(local, "Python", "pythoncore-3.14-64", "python.exe"),
            Path.Combine(local, "Python", "pythoncore-3.13-64", "python.exe"),
            Path.Combine(local, "Programs", "Python", "Python314", "python.exe"),
            Path.Combine(local, "Programs", "Python", "Python313", "python.exe"),
            Path.Combine(local, "Programs", "Python", "Python312", "python.exe"),
        };
        foreach (var c in candidates)
        {
            if (File.Exists(c) && !c.Contains("WindowsApps", StringComparison.OrdinalIgnoreCase))
                return c;
        }

        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = "where.exe",
                Arguments = "python",
                UseShellExecute = false,
                RedirectStandardOutput = true,
                CreateNoWindow = true,
            };
            using var p = Process.Start(psi);
            var output = p?.StandardOutput.ReadToEnd() ?? "";
            p?.WaitForExit(3000);
            foreach (var line in output.Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
            {
                if (File.Exists(line) && !line.Contains("WindowsApps", StringComparison.OrdinalIgnoreCase))
                    return line;
            }
        }
        catch { /* fall through */ }

        return "python";
    }

    void StartServer()
    {
        if (_server is { HasExited: false }) return;
        _error.Text = "";
        var script = Path.Combine(_root, "connector", "mcp_http_server.py");
        if (!File.Exists(script))
        {
            _error.Text = $"Missing {script}";
            return;
        }

        // IMPORTANT: do not RedirectStandardOutput/Error without draining them.
        // A full stdout pipe deadlocks uvicorn — TCP accepts but MCP never answers.
        var logPath = Path.Combine(_root, "connector", "mcp_http_server.log");
        var psi = new ProcessStartInfo
        {
            FileName = _python,
            Arguments = $"\"{script}\"",
            WorkingDirectory = Path.Combine(_root, "connector"),
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
        };
        psi.Environment["ARTIPHACT_ROOT"] = _root;
        psi.Environment["ARTIPHACT_MCP_HOST"] = "127.0.0.1";
        psi.Environment["ARTIPHACT_MCP_PORT"] = McpPort.ToString();
        psi.Environment["PLAYWRIGHT_BROWSERS_PATH"] = Path.Combine(_root, "connector", "browsers");
        psi.Environment["ARTIPHACT_PAGES"] = Path.Combine(_root, "connector", "pages");
        psi.Environment["PYTHONUNBUFFERED"] = "1";

        try
        {
            _server = Process.Start(psi);
        }
        catch (Exception ex)
        {
            _error.Text = ex.Message;
            return;
        }

        if (_server != null)
        {
            _server.OutputDataReceived += (_, e) =>
            {
                if (string.IsNullOrEmpty(e.Data)) return;
                try { File.AppendAllText(logPath, e.Data + Environment.NewLine); } catch { /* ignore */ }
            };
            _server.ErrorDataReceived += (_, e) =>
            {
                if (string.IsNullOrEmpty(e.Data)) return;
                try { File.AppendAllText(logPath, e.Data + Environment.NewLine); } catch { /* ignore */ }
            };
            _server.BeginOutputReadLine();
            _server.BeginErrorReadLine();
        }

        Thread.Sleep(800);
        if (_server is null || _server.HasExited)
        {
            var err = "";
            try
            {
                if (File.Exists(logPath))
                    err = File.ReadAllText(logPath);
            }
            catch { /* ignore */ }
            _error.Text = string.IsNullOrWhiteSpace(err)
                ? "MCP server exited immediately."
                : err.Trim()[..Math.Min(400, err.Trim().Length)];
            _server = null;
            return;
        }

        _status.Text = $"Server running on {_localMcpUrl}";
        _btnStart.Enabled = false;
        _btnStop.Enabled = true;
        _btnTunnel.Enabled = true;
    }

    void StartTunnel()
    {
        if (_server is null || _server.HasExited)
        {
            MessageBox.Show(this, "Start the server first.", "Artiphact Host");
            return;
        }
        if (_tunnel is { HasExited: false }) return;

        var warn = MessageBox.Show(
            this,
            "Public link exposes your local Artiphact MCP on the internet via Cloudflare.\n\n"
            + "Anyone with the URL can list panels and push pages while Host is running.\n"
            + "For ChatGPT Desktop prefer http://127.0.0.1:8766/mcp (no public link).\n\n"
            + "Continue?",
            "Artiphact Host — public link",
            MessageBoxButtons.YesNo,
            MessageBoxIcon.Warning);
        if (warn != DialogResult.Yes) return;

        try
        {
            if (File.Exists(_publicUrlFile)) File.Delete(_publicUrlFile);
        }
        catch { /* ignore */ }

        _publicBox.Text = "(waiting for Cloudflare…)";
        var script = Path.Combine(_root, "connector", "tunnel.py");
        var psi = new ProcessStartInfo
        {
            FileName = _python,
            Arguments = $"\"{script}\"",
            WorkingDirectory = Path.Combine(_root, "connector"),
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
        };
        psi.Environment["ARTIPHACT_BRIDGE_PORT"] = McpPort.ToString();
        psi.Environment["ARTIPHACT_PUBLIC_URL_FILE"] = _publicUrlFile;

        try
        {
            _tunnel = Process.Start(psi);
        }
        catch (Exception ex)
        {
            _error.Text = ex.Message;
            return;
        }

        _status.Text = "Tunnel starting…";
        if (_tunnel != null)
        {
            // Drain both pipes so cloudflared/python cannot stall on a full buffer.
            _tunnel.OutputDataReceived += (_, e) =>
            {
                if (string.IsNullOrEmpty(e.Data)) return;
                var line = e.Data;
                if (line.Contains("NO_CLOUDFLARED", StringComparison.Ordinal))
                    BeginInvoke(() => _error.Text = "cloudflared not found. Install Cloudflare Tunnel.");
                if (line.Contains("TUNNEL_URL_TIMEOUT", StringComparison.Ordinal))
                    BeginInvoke(() => _error.Text = "Timed out waiting for public URL.");
                if (line.Contains("PUBLIC_URL ", StringComparison.Ordinal))
                {
                    var url = line.Split("PUBLIC_URL ", 2)[^1].Trim();
                    BeginInvoke(() =>
                    {
                        _publicBox.Text = url;
                        _status.Text = "Public link ready — copy MCP URL";
                    });
                }
            };
            _tunnel.ErrorDataReceived += (_, e) => { /* discard — must drain */ };
            _tunnel.BeginOutputReadLine();
            _tunnel.BeginErrorReadLine();
            _tunnel.EnableRaisingEvents = true;
            _tunnel.Exited += (_, _) => BeginInvoke(() =>
            {
                if (_status.Text.StartsWith("Tunnel", StringComparison.Ordinal) ||
                    _status.Text.Contains("Public link", StringComparison.Ordinal))
                    _status.Text = "Tunnel stopped";
            });
        }
    }

    void ReadPublicUrlFile()
    {
        try
        {
            if (!File.Exists(_publicUrlFile)) return;
            var url = File.ReadAllText(_publicUrlFile).Trim();
            if (url.StartsWith("https://", StringComparison.Ordinal) && url != _publicBox.Text)
                _publicBox.Text = url;
        }
        catch { /* ignore */ }
    }

    string PublicMcpUrl()
    {
        var baseUrl = _publicBox.Text.Trim().TrimEnd('/');
        if (!baseUrl.StartsWith("https://", StringComparison.Ordinal)) return "";
        return baseUrl.EndsWith("/mcp", StringComparison.Ordinal) ? baseUrl : baseUrl + "/mcp";
    }

    void CopyPublicMcp()
    {
        var url = PublicMcpUrl();
        if (string.IsNullOrEmpty(url))
        {
            MessageBox.Show(this, "Start the public link first.", "Artiphact Host");
            return;
        }
        CopyText(url);
    }

    void CopyFilledPrompt(string name)
    {
        var path = Path.Combine(_root, "connector", "prompts", name);
        var body = File.Exists(path) ? File.ReadAllText(path) : "";
        var mcp = PublicMcpUrl();
        if (string.IsNullOrEmpty(mcp)) mcp = _localMcpUrl;
        body = body.Replace("{{MCP_URL}}", mcp).Replace("{{LOCAL_MCP_URL}}", _localMcpUrl);
        CopyText(body);
    }

    void CopyText(string text)
    {
        text = text.Trim();
        if (string.IsNullOrEmpty(text) || text.StartsWith('('))
        {
            MessageBox.Show(this, "Nothing to copy yet.", "Artiphact Host");
            return;
        }
        Clipboard.SetText(text);
        _status.Text = "Copied to clipboard";
    }

    void StopAll()
    {
        Kill(ref _tunnel);
        Kill(ref _server);
        try
        {
            if (File.Exists(_publicUrlFile)) File.Delete(_publicUrlFile);
        }
        catch { /* ignore */ }
        if (!_publicBox.Text.StartsWith("https://", StringComparison.Ordinal))
            _publicBox.Text = "(start public link)";
        _status.Text = "Stopped";
        _btnStart.Enabled = true;
        _btnStop.Enabled = false;
        _btnTunnel.Enabled = false;
    }

    static void Kill(ref Process? proc)
    {
        if (proc is null) return;
        try
        {
            if (!proc.HasExited)
            {
                proc.Kill(entireProcessTree: true);
                proc.WaitForExit(4000);
            }
        }
        catch { /* ignore */ }
        finally
        {
            proc.Dispose();
            proc = null;
        }
    }
}
