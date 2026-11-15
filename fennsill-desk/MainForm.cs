using System.Diagnostics;
using System.Text;
using System.Text.Json;

namespace FennsillDesk;

/// <summary>
/// Fennsill desk: panel status + local workers. AI pushes go straight to the
/// panel via Host MCP — no accumulating gallery of every AI page.
/// </summary>
public class MainForm : Form
{
    readonly string _root;
    readonly string _pagesDir;
    readonly Label _readyBanner = new();
    readonly Label _status = new();
    readonly Label _hint = new();
    readonly System.Windows.Forms.Timer _panelTimer = new();
    Process? _bridgeProcess;
    Process? _liveProcess;
    Process? _liveJobsProcess;
    bool _panelReady;
    bool _setupRanForThisPlug;
    string _panelPorts = "";

    public MainForm()
    {
        _root = FindProjectRoot();
        _pagesDir = Path.Combine(_root, "connector", "pages");
        Directory.CreateDirectory(_pagesDir);
        Directory.CreateDirectory(Path.Combine(_root, "connector", "inbox"));
        BuildUi();
        StartBackgroundServices();
        _panelTimer.Interval = 3000;
        _panelTimer.Tick += async (_, _) => await RefreshPanelStatus();
        _panelTimer.Start();
        _ = RefreshPanelStatus();
    }

    static string FindProjectRoot()
    {
        var env = Environment.GetEnvironmentVariable("FENNSILL_ROOT");
        if (!string.IsNullOrWhiteSpace(env) && HasConnector(env)) return env;

        var installed = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Fennsill");
        if (HasConnector(installed)) return installed;

        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir != null)
        {
            if (HasConnector(dir.FullName)) return dir.FullName;
            dir = dir.Parent;
        }

        var desktopProject = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),
            "This Is A Test For The Tablet");
        if (HasConnector(desktopProject)) return desktopProject;

        return Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", ".."));
    }

    static bool HasConnector(string root) =>
        File.Exists(Path.Combine(root, "connector", "mcp_server.py"))
        || File.Exists(Path.Combine(root, "connector", "mcp_http_server.py"));

    void BuildUi()
    {
        var bg = Color.FromArgb(18, 20, 24);
        var surface = Color.FromArgb(28, 31, 36);
        var text = Color.FromArgb(242, 240, 235);
        var muted = Color.FromArgb(154, 149, 140);

        Text = "Fennsill";
        Width = 720;
        Height = 420;
        MinimumSize = new Size(560, 360);
        StartPosition = FormStartPosition.CenterScreen;
        BackColor = bg;
        ForeColor = text;
        Font = new Font("Segoe UI", 10F);
        try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { /* default */ }

        var top = new Panel
        {
            Dock = DockStyle.Fill,
            BackColor = surface,
            Padding = new Padding(28, 24, 28, 24),
        };

        var title = new Label
        {
            Text = "Fennsill",
            Font = new Font("Segoe UI Semibold", 22F),
            ForeColor = text,
            AutoSize = true,
            Location = new Point(28, 28),
        };

        _readyBanner.Location = new Point(28, 78);
        _readyBanner.Size = new Size(640, 28);
        _readyBanner.Font = new Font("Segoe UI Semibold", 13F);
        _readyBanner.ForeColor = Color.FromArgb(232, 184, 74);
        _readyBanner.Text = "Waiting for panel…";

        _status.Location = new Point(28, 118);
        _status.AutoSize = true;
        _status.MaximumSize = new Size(640, 0);
        _status.ForeColor = muted;
        _status.Text = "Panel updates come from ChatGPT / Claude through Fennsill Host.";

        _hint.Location = new Point(28, 160);
        _hint.Size = new Size(640, 80);
        _hint.ForeColor = muted;
        _hint.Text =
            "Keep this app open while the panel is plugged in.\n" +
            "Run Fennsill Host for MCP / scheduled tasks.\n" +
            "AI pushes go to the panel — nothing piles up in a gallery here.";

        var actions = new FlowLayoutPanel
        {
            Location = new Point(28, 260),
            Size = new Size(640, 80),
            FlowDirection = FlowDirection.LeftToRight,
            WrapContents = true,
            BackColor = Color.Transparent,
        };

        Button ActionBtn(string label) => new()
        {
            Text = label,
            AutoSize = true,
            FlatStyle = FlatStyle.Flat,
            BackColor = Color.FromArgb(40, 44, 52),
            ForeColor = text,
            Padding = new Padding(12, 6, 12, 6),
            Margin = new Padding(0, 0, 8, 8),
            Cursor = Cursors.Hand,
        };

        var refresh = ActionBtn("Refresh");
        var importBtn = ActionBtn("Import HTML");
        var paste = ActionBtn("Paste page");
        refresh.Click += async (_, _) => await RefreshPanelStatus();
        importBtn.Click += async (_, _) => await ImportHtmlFile();
        paste.Click += async (_, _) => await PastePage();
        actions.Controls.Add(refresh);
        actions.Controls.Add(importBtn);
        actions.Controls.Add(paste);

        top.Controls.Add(title);
        top.Controls.Add(_readyBanner);
        top.Controls.Add(_status);
        top.Controls.Add(_hint);
        top.Controls.Add(actions);
        Controls.Add(top);
    }

    void StartBackgroundServices()
    {
        try
        {
            using var killer = StartPython("connector\\kill_orphans.py");
            killer?.WaitForExit(8000);
        }
        catch { /* still start fresh workers */ }
        _bridgeProcess = StartPython("connector\\http_bridge.py");
        _liveProcess = StartPython("connector\\live_watch.py");
        _liveJobsProcess = StartPython("connector\\live_jobs.py");
    }

    Process? StartPython(string relative)
    {
        var script = Path.Combine(_root, relative);
        if (!File.Exists(script)) return null;
        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = "python",
                Arguments = $"\"{script}\"",
                WorkingDirectory = _root,
                UseShellExecute = false,
                CreateNoWindow = true,
            };
            psi.Environment["FENNSILL_ROOT"] = _root;
            psi.Environment["FENNSILL_PAGES"] = _pagesDir;
            psi.Environment["PLAYWRIGHT_BROWSERS_PATH"] = Path.Combine(_root, "connector", "browsers");
            psi.Environment["PYTHONUNBUFFERED"] = "1";
            return Process.Start(psi);
        }
        catch
        {
            return null;
        }
    }

    async Task RefreshPanelStatus()
    {
        var script = Path.Combine(_root, "connector", "panel_status.py");
        if (!File.Exists(script)) return;
        var wasReady = _panelReady;
        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = "python",
                Arguments = $"\"{script}\"",
                WorkingDirectory = _root,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true,
            };
            psi.Environment["FENNSILL_ROOT"] = _root;
            using var proc = Process.Start(psi);
            if (proc == null) return;
            var stdout = await proc.StandardOutput.ReadToEndAsync();
            await proc.WaitForExitAsync();
            using var doc = JsonDocument.Parse(string.IsNullOrWhiteSpace(stdout) ? "{}" : stdout);
            _panelReady = doc.RootElement.TryGetProperty("ready", out var r) && r.GetBoolean();
            if (doc.RootElement.TryGetProperty("ports", out var ports) && ports.ValueKind == JsonValueKind.Array)
                _panelPorts = string.Join(", ", ports.EnumerateArray().Select(p => p.GetString()).Where(s => !string.IsNullOrEmpty(s)));
            else
                _panelPorts = "";
            _panelTimer.Interval = _panelReady ? 12000 : 3000;
        }
        catch
        {
            _panelReady = false;
        }

        if (_panelReady && !wasReady)
            _ = Task.Run(RunClientSetupOnce);
        if (!_panelReady)
            _setupRanForThisPlug = false;

        if (_panelReady)
        {
            _readyBanner.ForeColor = Color.FromArgb(120, 200, 140);
            _readyBanner.Text = "Fennsill panel connected";
            _status.Text = string.IsNullOrEmpty(_panelPorts) ? "Panel connected." : $"Panel {_panelPorts}";
        }
        else
        {
            _readyBanner.ForeColor = Color.FromArgb(232, 184, 74);
            _readyBanner.Text = "Waiting for panel…";
            _status.Text = string.IsNullOrEmpty(_panelPorts) ? "Waiting for panel." : $"Seen: {_panelPorts}";
        }
    }

    void RunClientSetupOnce()
    {
        if (_setupRanForThisPlug) return;
        _setupRanForThisPlug = true;
        var script = Path.Combine(_root, "connector", "install_clients.py");
        if (!File.Exists(script)) return;
        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = "python",
                Arguments = $"\"{script}\"",
                WorkingDirectory = _root,
                UseShellExecute = false,
                CreateNoWindow = true,
            };
            psi.Environment["FENNSILL_ROOT"] = _root;
            using var proc = Process.Start(psi);
            proc?.WaitForExit(60000);
        }
        catch { /* optional */ }
    }

    async Task PastePage()
    {
        string html;
        try { html = Clipboard.GetText(); }
        catch { html = ""; }
        if (string.IsNullOrWhiteSpace(html))
        {
            MessageBox.Show(this, "Clipboard is empty.", "Fennsill");
            return;
        }
        await IngestHtml(html, "clipboard");
    }

    async Task ImportHtmlFile()
    {
        using var dlg = new OpenFileDialog
        {
            Filter = "HTML (*.html;*.htm)|*.html;*.htm|All files|*.*",
            Title = "Import HTML page",
        };
        if (dlg.ShowDialog(this) != DialogResult.OK) return;
        try
        {
            var html = await File.ReadAllTextAsync(dlg.FileName);
            await IngestHtml(html, Path.GetFileName(dlg.FileName));
        }
        catch (Exception ex)
        {
            MessageBox.Show(this, ex.Message, "Import failed");
        }
    }

    async Task IngestHtml(string html, string source)
    {
        var script = Path.Combine(_root, "connector", "ingest_page.py");
        if (!File.Exists(script))
        {
            MessageBox.Show(this, "ingest_page.py missing.", "Fennsill");
            return;
        }
        _status.Text = "Sending to panel…";
        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = "python",
                Arguments = $"\"{script}\"",
                WorkingDirectory = _root,
                UseShellExecute = false,
                RedirectStandardInput = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true,
            };
            psi.Environment["FENNSILL_ROOT"] = _root;
            psi.Environment["FENNSILL_PAGES"] = _pagesDir;
            psi.Environment["PLAYWRIGHT_BROWSERS_PATH"] = Path.Combine(_root, "connector", "browsers");
            using var proc = Process.Start(psi);
            if (proc == null)
            {
                _status.Text = "Could not start ingest.";
                return;
            }
            var payload = JsonSerializer.Serialize(new { html, source, push = true });
            await proc.StandardInput.WriteAsync(payload);
            proc.StandardInput.Close();
            var stdout = await proc.StandardOutput.ReadToEndAsync();
            await proc.WaitForExitAsync();
            if (proc.ExitCode != 0)
            {
                _status.Text = "Import failed.";
                return;
            }
            var note = "Sent to the panel.";
            try
            {
                using var doc = JsonDocument.Parse(string.IsNullOrWhiteSpace(stdout) ? "{}" : stdout);
                if (doc.RootElement.TryGetProperty("note", out var n))
                    note = n.GetString() ?? note;
            }
            catch { /* keep default */ }
            _status.Text = note;
        }
        catch (Exception ex)
        {
            MessageBox.Show(this, ex.Message, "Import failed");
            _status.Text = "Import failed.";
        }
    }

    static void Kill(Process? p)
    {
        try
        {
            if (p is { HasExited: false })
            {
                p.Kill(entireProcessTree: true);
                p.Dispose();
            }
        }
        catch { /* ignore */ }
    }

    protected override void OnFormClosed(FormClosedEventArgs e)
    {
        _panelTimer.Stop();
        Kill(_liveProcess);
        Kill(_liveJobsProcess);
        Kill(_bridgeProcess);
        base.OnFormClosed(e);
    }
}
