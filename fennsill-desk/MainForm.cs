using System.Diagnostics;
using System.Text;
using System.Text.Json;

namespace FennsillDesk;

/// <summary>
/// Fennsill desk: panel status + local workers. AI pushes go straight to the
/// panel via cloud MCP — no accumulating gallery of every AI page.
/// </summary>
public class MainForm : Form
{
    readonly string _root;
    readonly string _pagesDir;
    readonly Label _readyBanner = new();
    readonly Label _status = new();
    readonly Label _hint = new();
    readonly TextBox _deviceIdBox = new();
    readonly TextBox _serialBox = new();
    readonly TextBox _installKeyBox = new();
    readonly System.Windows.Forms.Timer _panelTimer = new();
    Process? _bridgeProcess;
    Process? _liveProcess;
    Process? _liveJobsProcess;
    Process? _cloudAgentProcess;
    bool _panelReady;
    bool _setupRanForThisPlug;
    string _panelPorts = "";
    string _deviceId = "";
    string _serial = "";
    string _installKey = "";

    public MainForm()
    {
        _root = FindProjectRoot();
        _pagesDir = Path.Combine(_root, "connector", "pages");
        Directory.CreateDirectory(_pagesDir);
        Directory.CreateDirectory(Path.Combine(_root, "connector", "inbox"));
        BuildUi();
        StartBackgroundServices();
        _panelTimer.Interval = 3000;
        _panelTimer.Tick += async (_, _) =>
        {
            EnsureCloudAgentRunning();
            await RefreshPanelStatus();
        };
        _panelTimer.Start();
        _ = RefreshPanelStatus();
    }

    void EnsureCloudAgentRunning()
    {
        try
        {
            if (_cloudAgentProcess is { HasExited: false })
                return;
            // Another Desk window (or a detached agent) may already be heartbeating.
            if (CloudAgentHealthy())
                return;
            _cloudAgentProcess = StartPythonScript("cloud_agent.py");
        }
        catch { /* best effort */ }
    }

    static bool CloudAgentHealthy()
    {
        try
        {
            var path = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "FennsillApp",
                "cloud_agent_status.json");
            if (!File.Exists(path)) return false;
            if ((DateTime.UtcNow - File.GetLastWriteTimeUtc(path)).TotalSeconds > 45)
                return false;
            var text = File.ReadAllText(path);
            return text.Contains("\"ok\": true", StringComparison.OrdinalIgnoreCase)
                || text.Contains("\"ok\":true", StringComparison.OrdinalIgnoreCase);
        }
        catch
        {
            return false;
        }
    }

    static string FindProjectRoot()
    {
        var env = Environment.GetEnvironmentVariable("FENNSILL_ROOT");
        if (!string.IsNullOrWhiteSpace(env) && HasConnector(env)) return env;

        var installed = DeskInstall.InstallRoot;
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
        ResolveUnderRoot(root,
            "mcp_server.py", "mcp_http_server.py",
            "identity_status.py", "panel_status.py",
            "device_bind_tool.py", "bind_device.py") != null;

    static string? ResolveUnderRoot(string root, params string[] names)
    {
        foreach (var name in names)
        {
            foreach (var dir in new[]
                     {
                         Path.Combine(root, "connector"),
                         Path.Combine(root, "connector", "runtime"),
                     })
            {
                var path = Path.Combine(dir, name);
                if (File.Exists(path)) return path;
            }
        }
        return null;
    }

    string? ResolveConnectorScript(params string[] names) => ResolveUnderRoot(_root, names);

    void BuildUi()
    {
        var bg = Color.FromArgb(18, 20, 24);
        var surface = Color.FromArgb(28, 31, 36);
        var text = Color.FromArgb(242, 240, 235);
        var muted = Color.FromArgb(154, 149, 140);

        Text = "Fennsill";
        Width = 760;
        Height = 560;
        MinimumSize = new Size(640, 480);
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
            AutoScroll = true,
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
        _readyBanner.Size = new Size(680, 28);
        _readyBanner.Font = new Font("Segoe UI Semibold", 13F);
        _readyBanner.ForeColor = Color.FromArgb(232, 184, 74);
        _readyBanner.Text = "Waiting for panel…";

        _status.Location = new Point(28, 112);
        _status.AutoSize = true;
        _status.MaximumSize = new Size(680, 0);
        _status.ForeColor = muted;
        _status.Text = "Panel updates come from ChatGPT / Claude through cloud MCP.";

        var identityLabel = new Label
        {
            Text = "Copy these into the Fennsill website (Link your panel):",
            ForeColor = muted,
            AutoSize = true,
            Location = new Point(28, 148),
        };

        var identity = new TableLayoutPanel
        {
            Location = new Point(28, 176),
            Size = new Size(680, 132),
            ColumnCount = 3,
            RowCount = 3,
            BackColor = Color.Transparent,
        };
        identity.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 110));
        identity.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        identity.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 88));
        for (var i = 0; i < 3; i++)
            identity.RowStyles.Add(new RowStyle(SizeType.Absolute, 40));

        void StyleIdBox(TextBox box)
        {
            box.ReadOnly = true;
            box.BorderStyle = BorderStyle.FixedSingle;
            box.BackColor = Color.FromArgb(22, 24, 28);
            box.ForeColor = text;
            box.Font = new Font("Consolas", 10F);
            box.Dock = DockStyle.Fill;
            box.Margin = new Padding(0, 4, 8, 4);
        }

        Button CopyBtn(Func<string> getValue) => new()
        {
            Text = "Copy",
            FlatStyle = FlatStyle.Flat,
            BackColor = Color.FromArgb(40, 44, 52),
            ForeColor = text,
            Dock = DockStyle.Fill,
            Margin = new Padding(0, 4, 0, 4),
            Cursor = Cursors.Hand,
            Tag = getValue,
        };

        StyleIdBox(_deviceIdBox);
        StyleIdBox(_serialBox);
        StyleIdBox(_installKeyBox);
        _deviceIdBox.Text = "(not bound yet)";
        _serialBox.Text = "(not bound yet)";
        _installKeyBox.Text = "(not bound yet)";

        var copyDevice = CopyBtn(() => _deviceId);
        var copySerial = CopyBtn(() => _serial);
        var copyKey = CopyBtn(() => _installKey);
        void CopyClick(object? sender, EventArgs e)
        {
            if (sender is not Button btn || btn.Tag is not Func<string> getter) return;
            var value = getter();
            if (string.IsNullOrWhiteSpace(value))
            {
                MessageBox.Show(this, "Nothing to copy yet — plug the panel in so Fennsill can bind it.", "Fennsill");
                return;
            }
            try
            {
                Clipboard.SetText(value);
                _status.Text = "Copied — paste into the website.";
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, ex.Message, "Copy failed");
            }
        }
        copyDevice.Click += CopyClick;
        copySerial.Click += CopyClick;
        copyKey.Click += CopyClick;

        Label IdLabel(string caption) => new()
        {
            Text = caption,
            ForeColor = muted,
            Dock = DockStyle.Fill,
            TextAlign = ContentAlignment.MiddleLeft,
            Margin = new Padding(0, 4, 8, 4),
        };

        identity.Controls.Add(IdLabel("Device ID"), 0, 0);
        identity.Controls.Add(_deviceIdBox, 1, 0);
        identity.Controls.Add(copyDevice, 2, 0);
        identity.Controls.Add(IdLabel("Serial"), 0, 1);
        identity.Controls.Add(_serialBox, 1, 1);
        identity.Controls.Add(copySerial, 2, 1);
        identity.Controls.Add(IdLabel("Install key"), 0, 2);
        identity.Controls.Add(_installKeyBox, 1, 2);
        identity.Controls.Add(copyKey, 2, 2);

        _hint.Location = new Point(28, 318);
        _hint.Size = new Size(680, 56);
        _hint.ForeColor = muted;
        _hint.Text =
            "Device ID → website “Link your panel” only (not the ChatGPT/Claude MCP form).\n" +
            "MCP form: URL + Headers Authorization = Bearer <token> (cloud account).\n" +
            "Then Mint device key → Paste device key here, keep Fennsill open (panel check-in).";

        var actions = new FlowLayoutPanel
        {
            Location = new Point(28, 384),
            Size = new Size(680, 80),
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
        var pasteKey = ActionBtn("Paste device key");
        refresh.Click += async (_, _) => await RefreshPanelStatus();
        importBtn.Click += async (_, _) => await ImportHtmlFile();
        paste.Click += async (_, _) => await PastePage();
        pasteKey.Click += (_, _) => PasteCloudDeviceKey();
        actions.Controls.Add(refresh);
        actions.Controls.Add(importBtn);
        actions.Controls.Add(paste);
        actions.Controls.Add(pasteKey);

        top.Controls.Add(title);
        top.Controls.Add(_readyBanner);
        top.Controls.Add(_status);
        top.Controls.Add(identityLabel);
        top.Controls.Add(identity);
        top.Controls.Add(_hint);
        top.Controls.Add(actions);
        Controls.Add(top);
        ApplyIdentityUi();
    }

    void ApplyIdentityUi()
    {
        _deviceIdBox.Text = string.IsNullOrEmpty(_deviceId) ? "(not bound yet)" : _deviceId;
        _serialBox.Text = string.IsNullOrEmpty(_serial) ? "(not bound yet)" : _serial;
        _installKeyBox.Text = string.IsNullOrEmpty(_installKey) ? "(not bound yet)" : _installKey;
    }

    void StartBackgroundServices()
    {
        try
        {
            using var killer = StartPythonScript("kill_orphans.py");
            killer?.WaitForExit(8000);
        }
        catch { /* still start fresh workers */ }
        _bridgeProcess = StartPythonScript("http_bridge.py");
        _liveProcess = StartPythonScript("live_watch.py");
        _liveJobsProcess = StartPythonScript("live_jobs.py");
        // Cloud MCP jobs land here — heartbeat makes the panel “checked in”.
        // Only one agent process system-wide (duplicates steal jobs / fight USB).
        EnsureCloudAgentRunning();
    }

    Process? StartPythonScript(params string[] names)
    {
        var script = ResolveConnectorScript(names);
        if (script == null) return null;
        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = FindPython(),
                Arguments = $"\"{script}\"",
                WorkingDirectory = _root,
                UseShellExecute = false,
                CreateNoWindow = true,
            };
            psi.Environment["FENNSILL_ROOT"] = _root;
            psi.Environment["FENNSILL_PAGES"] = _pagesDir;
            psi.Environment["PLAYWRIGHT_BROWSERS_PATH"] = Path.Combine(_root, "connector", "browsers");
            psi.Environment["PYTHONUNBUFFERED"] = "1";
            // Workers import sibling modules from connector/ (or connector/runtime/).
            var scriptDir = Path.GetDirectoryName(script);
            if (!string.IsNullOrEmpty(scriptDir))
                psi.Environment["PYTHONPATH"] = scriptDir +
                    (string.IsNullOrEmpty(Environment.GetEnvironmentVariable("PYTHONPATH"))
                        ? ""
                        : (Path.PathSeparator + Environment.GetEnvironmentVariable("PYTHONPATH")));
            return Process.Start(psi);
        }
        catch
        {
            return null;
        }
    }

    async Task RefreshPanelStatus()
    {
        var script = ResolveConnectorScript("identity_status.py", "panel_status.py", "status_check.py");
        if (script == null) return;
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
            if (doc.RootElement.TryGetProperty("device_id", out var did))
                _deviceId = did.GetString()?.Trim().ToUpperInvariant() ?? "";
            if (doc.RootElement.TryGetProperty("serial", out var ser))
                _serial = ser.GetString()?.Trim() ?? "";
            if (doc.RootElement.TryGetProperty("install_key", out var ik))
                _installKey = ik.GetString()?.Trim() ?? "";
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

        var cloudLine = DescribeCloudCheckIn();
        if (_panelReady)
        {
            _readyBanner.ForeColor = Color.FromArgb(120, 200, 140);
            _readyBanner.Text = "Fennsill panel connected";
            var port = string.IsNullOrEmpty(_panelPorts) ? "Panel connected." : $"Panel {_panelPorts}";
            _status.Text = port + "  ·  " + cloudLine;
        }
        else
        {
            _readyBanner.ForeColor = Color.FromArgb(232, 184, 74);
            _readyBanner.Text = "Waiting for panel…";
            var seen = string.IsNullOrEmpty(_panelPorts) ? "Waiting for panel." : $"Seen: {_panelPorts}";
            _status.Text = seen + "  ·  " + cloudLine;
        }
        ApplyIdentityUi();
    }

    static string DescribeCloudCheckIn()
    {
        try
        {
            var app = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "FennsillApp");
            var tokenPath = Path.Combine(app, "cloud_device_token.txt");
            if (!File.Exists(tokenPath) || string.IsNullOrWhiteSpace(File.ReadAllText(tokenPath)))
                return "Cloud: no device key — Mint on mcp.fennsill.com → Paste device key";

            var statusPath = Path.Combine(app, "cloud_agent_status.json");
            if (!File.Exists(statusPath))
                return "Cloud: agent starting…";

            var age = DateTime.UtcNow - File.GetLastWriteTimeUtc(statusPath);
            var json = File.ReadAllText(statusPath);
            using var doc = JsonDocument.Parse(string.IsNullOrWhiteSpace(json) ? "{}" : json);
            var root = doc.RootElement;
            var ok = root.TryGetProperty("ok", out var okEl) && okEl.ValueKind == JsonValueKind.True;
            var hb = root.TryGetProperty("heartbeat_status", out var hbEl) && hbEl.TryGetInt32(out var hbCode)
                ? hbCode
                : 0;
            string? did = null;
            if (root.TryGetProperty("heartbeat", out var hbObj) &&
                hbObj.ValueKind == JsonValueKind.Object &&
                hbObj.TryGetProperty("device_id", out var didEl))
                did = didEl.GetString();

            if (ok && hb == 200 && age.TotalSeconds <= 90)
                return string.IsNullOrEmpty(did)
                    ? "Cloud: checked in"
                    : $"Cloud: checked in ({did})";

            if (age.TotalSeconds > 90)
                return "Cloud: agent stale — keep Fennsill open / Paste device key again";

            if (root.TryGetProperty("error", out var err) && err.GetString() is { Length: > 0 } errText)
                return "Cloud: " + errText;

            // Prefer the cloud JSON error (403 = inactive sub / unlinked device, etc.)
            if (root.TryGetProperty("heartbeat", out var hbPayload))
            {
                string? detail = null;
                if (hbPayload.ValueKind == JsonValueKind.Object)
                {
                    if (hbPayload.TryGetProperty("error", out var e1)) detail = e1.GetString();
                    else if (hbPayload.TryGetProperty("message", out var e2)) detail = e2.GetString();
                    if (hbPayload.TryGetProperty("code", out var c1) && c1.GetString() is { Length: > 0 } errCode)
                        detail = string.IsNullOrEmpty(detail) ? errCode : $"{errCode}: {detail}";
                }
                else if (hbPayload.ValueKind == JsonValueKind.String)
                    detail = hbPayload.GetString();
                if (!string.IsNullOrWhiteSpace(detail))
                    return $"Cloud: heartbeat {hb} — {detail}";
            }

            var cfBlocked = root.TryGetProperty("cloudflare_block", out var cf) && cf.ValueKind == JsonValueKind.True;
            var err1010 = false;
            if (root.TryGetProperty("heartbeat", out var hbErr) &&
                hbErr.ValueKind == JsonValueKind.Object &&
                hbErr.TryGetProperty("error", out var e1010))
            {
                var errStr = e1010.GetString() ?? "";
                err1010 = errStr.Contains("1010", StringComparison.OrdinalIgnoreCase)
                    || errStr.Contains("cloudflare", StringComparison.OrdinalIgnoreCase);
            }
            if (hb == 1010 || cfBlocked || err1010)
                return "Cloud: Cloudflare 1010 — updating agent / wait 2 min, keep Fennsill open";

            if (hb == 403)
                return "Cloud: heartbeat 403 — wait/backoff, or remint device key if it never clears";
            return hb == 0 ? "Cloud: agent not reaching mcp.fennsill.com" : $"Cloud: heartbeat HTTP {hb}";
        }
        catch
        {
            return "Cloud: status unknown";
        }
    }

    void RunClientSetupOnce()
    {
        if (_setupRanForThisPlug) return;
        _setupRanForThisPlug = true;
        try
        {
            var bind = ResolveConnectorScript("device_bind_tool.py", "bind_device.py");
            if (bind != null)
            {
                var psiBind = new ProcessStartInfo
                {
                    FileName = "python",
                    Arguments = $"\"{bind}\"",
                    WorkingDirectory = _root,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                };
                psiBind.Environment["FENNSILL_ROOT"] = _root;
                using var bindProc = Process.Start(psiBind);
                bindProc?.WaitForExit(45000);
            }
        }
        catch { /* bind optional until panel answers */ }

        var script = ResolveConnectorScript("install_clients.py");
        if (script == null) return;
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

        // Refresh identity from bind file after setup.
        try
        {
            BeginInvoke(async () => await RefreshPanelStatus());
        }
        catch { /* form may be closing */ }
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

    void PasteCloudDeviceKey()
    {
        string text;
        try { text = Clipboard.GetText()?.Trim() ?? ""; }
        catch { text = ""; }
        if (string.IsNullOrWhiteSpace(text))
        {
            MessageBox.Show(
                this,
                "Clipboard is empty.\n\nOn the account site: Mint device key → Copy → Paste device key here.\n" +
                "If your site is a LAN URL (not mcp.fennsill.com), also save that base URL to %LOCALAPPDATA%\\FennsillApp\\cloud_url.txt",
                "Fennsill");
            return;
        }

        // Allow pasting MCP / cloud base URL to point the agent at a LAN server.
        var maybeUrl = text.Split('\n', '\r')[0].Trim().TrimEnd('/');
        if (maybeUrl.StartsWith("http://", StringComparison.OrdinalIgnoreCase) ||
            maybeUrl.StartsWith("https://", StringComparison.OrdinalIgnoreCase))
        {
            if (maybeUrl.EndsWith("/mcp", StringComparison.OrdinalIgnoreCase))
                maybeUrl = maybeUrl[..^4].TrimEnd('/');
            try
            {
                var dir = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "FennsillApp");
                Directory.CreateDirectory(dir);
                File.WriteAllText(Path.Combine(dir, "cloud_url.txt"), maybeUrl + Environment.NewLine);
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, ex.Message, "Could not save cloud URL");
                return;
            }
            try { _cloudAgentProcess?.Kill(entireProcessTree: true); } catch { /* ignore */ }
            _cloudAgentProcess = StartPythonScript("cloud_agent.py");
            _status.Text = "Cloud URL saved — " + maybeUrl;
            MessageBox.Show(
                this,
                $"Cloud URL saved:\n{maybeUrl}\n\nNow copy the device key from the site and Paste device key again.",
                "Fennsill",
                MessageBoxButtons.OK,
                MessageBoxIcon.Information);
            return;
        }

        if (text.StartsWith("Bearer ", StringComparison.OrdinalIgnoreCase))
            text = text[7..].Trim();
        // Device keys are long tokens; reject accidental HTML paste.
        if (text.Contains('<') || text.Length < 20)
        {
            MessageBox.Show(
                this,
                "That clipboard text does not look like a device key.\n\nMint the key on the account site, copy it, then try again.",
                "Fennsill");
            return;
        }
        try
        {
            var dir = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "FennsillApp");
            Directory.CreateDirectory(dir);
            File.WriteAllText(Path.Combine(dir, "cloud_device_token.txt"), text + Environment.NewLine);
        }
        catch (Exception ex)
        {
            MessageBox.Show(this, ex.Message, "Could not save device key");
            return;
        }

        try { _cloudAgentProcess?.Kill(entireProcessTree: true); } catch { /* ignore */ }
        _cloudAgentProcess = StartPythonScript("cloud_agent.py");
        _status.Text = "Cloud device key saved — agent checking in…";
        MessageBox.Show(
            this,
            "Device key saved.\n\nKeep Fennsill open with the panel plugged in so ChatGPT/Claude can push pages.\n" +
            "Agent cloud = cloud_url.txt if set, otherwise https://mcp.fennsill.com",
            "Fennsill",
            MessageBoxButtons.OK,
            MessageBoxIcon.Information);
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
        var script = ResolveConnectorScript("ingest_page.py");
        if (script == null)
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
        // Do NOT kill the cloud agent — it must keep heartbeating so ChatGPT
        // still sees the panel online after Desk is closed.
        base.OnFormClosed(e);
    }

    static string FindPython()
    {
        foreach (var name in new[] { "python", "py" })
        {
            try
            {
                var psi = new ProcessStartInfo
                {
                    FileName = name,
                    ArgumentList = { "--version" },
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                };
                using var p = Process.Start(psi);
                if (p is null) continue;
                p.WaitForExit(4000);
                if (p.ExitCode == 0) return name;
            }
            catch { /* try next */ }
        }
        var local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        foreach (var cand in new[]
                 {
                     Path.Combine(local, "Python", "pythoncore-3.14-64", "python.exe"),
                     Path.Combine(local, "Python", "bin", "python.exe"),
                 })
        {
            if (File.Exists(cand)) return cand;
        }
        return "python";
    }
}
