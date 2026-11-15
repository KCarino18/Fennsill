using System.Diagnostics;
using System.Text;
using System.Text.Json;

namespace FennsillFactory;

/// <summary>
/// Standalone factory window (not Fennsill.exe). Select → Check → Flash.
/// </summary>
public sealed class MainForm : Form
{
    readonly ComboBox _devices = new();
    readonly Button _refreshBtn = new();
    readonly Button _checkBtn = new();
    readonly Button _flashBtn = new();
    readonly Label _checkStatus = new();
    readonly TextBox _log = new();
    readonly string _repoRoot;
    readonly string _factoryDir;

    List<JsonElement> _targets = new();
    string? _checkedPort;
    bool _busy;

    public MainForm()
    {
        _repoRoot = FindRepoRoot();
        _factoryDir = ResolveFactoryDir(_repoRoot);

        Text = "Fennsill Factory";
        Width = 720;
        Height = 560;
        MinimumSize = new Size(640, 480);
        StartPosition = FormStartPosition.CenterScreen;
        BackColor = Color.FromArgb(28, 28, 28);
        ForeColor = Color.FromArgb(235, 235, 235);
        Font = new Font("Segoe UI", 10f);

        var title = new Label
        {
            Text = "Fennsill Factory",
            Font = new Font("Segoe UI", 18f, FontStyle.Bold),
            AutoSize = true,
            Location = new Point(24, 20),
            ForeColor = Color.White,
            BackColor = Color.Transparent,
        };
        var subtitle = new Label
        {
            Text = "Select the e-ink panel → Check → Flash. Wipes TRMNL, installs Fennsill.",
            AutoSize = true,
            MaximumSize = new Size(650, 0),
            Location = new Point(24, 58),
            ForeColor = Color.FromArgb(180, 180, 180),
            BackColor = Color.Transparent,
        };

        var selectBox = MakeGroup("1. Select device", 24, 100, 656, 88);
        _devices.DropDownStyle = ComboBoxStyle.DropDownList;
        _devices.Width = 500;
        _devices.Location = new Point(16, 32);
        _devices.SelectedIndexChanged += (_, _) => ClearCheck();
        _refreshBtn.Text = "Refresh";
        _refreshBtn.Width = 100;
        _refreshBtn.Location = new Point(530, 30);
        _refreshBtn.Click += async (_, _) => await RefreshDevicesAsync();
        selectBox.Controls.Add(_devices);
        selectBox.Controls.Add(_refreshBtn);

        var checkBox = MakeGroup("2. Check", 24, 200, 656, 100);
        _checkBtn.Text = "Check selected device";
        _checkBtn.Width = 200;
        _checkBtn.Height = 36;
        _checkBtn.Location = new Point(16, 28);
        _checkBtn.Click += async (_, _) => await CheckAsync();
        _checkStatus.Text = "Not checked yet.";
        _checkStatus.AutoSize = true;
        _checkStatus.MaximumSize = new Size(620, 0);
        _checkStatus.Location = new Point(16, 70);
        _checkStatus.ForeColor = Color.FromArgb(180, 180, 180);
        checkBox.Controls.Add(_checkBtn);
        checkBox.Controls.Add(_checkStatus);

        var flashBox = MakeGroup("3. Flash", 24, 314, 656, 88);
        _flashBtn.Text = "Flash Fennsill";
        _flashBtn.Width = 624;
        _flashBtn.Height = 48;
        _flashBtn.Location = new Point(16, 26);
        _flashBtn.Font = new Font("Segoe UI", 12f, FontStyle.Bold);
        _flashBtn.Enabled = false;
        _flashBtn.BackColor = Color.FromArgb(45, 110, 70);
        _flashBtn.ForeColor = Color.White;
        _flashBtn.FlatStyle = FlatStyle.Flat;
        _flashBtn.Click += async (_, _) => await FlashAsync();
        flashBox.Controls.Add(_flashBtn);

        _log.Multiline = true;
        _log.ReadOnly = true;
        _log.ScrollBars = ScrollBars.Vertical;
        _log.BackColor = Color.FromArgb(18, 18, 18);
        _log.ForeColor = Color.FromArgb(210, 210, 210);
        _log.BorderStyle = BorderStyle.FixedSingle;
        _log.Location = new Point(24, 416);
        _log.Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right;
        _log.Width = 656;
        _log.Height = 90;

        Controls.Add(title);
        Controls.Add(subtitle);
        Controls.Add(selectBox);
        Controls.Add(checkBox);
        Controls.Add(flashBox);
        Controls.Add(_log);

        Shown += async (_, _) => await RefreshDevicesAsync();
    }

    static GroupBox MakeGroup(string title, int x, int y, int w, int h)
    {
        return new GroupBox
        {
            Text = title,
            Location = new Point(x, y),
            Size = new Size(w, h),
            ForeColor = Color.FromArgb(220, 220, 220),
            BackColor = Color.FromArgb(36, 36, 36),
        };
    }

    void ClearCheck()
    {
        _checkedPort = null;
        _flashBtn.Enabled = false;
        _checkStatus.Text = "Selection changed — press Check.";
        _checkStatus.ForeColor = Color.FromArgb(180, 180, 180);
    }

    void Log(string line)
    {
        if (InvokeRequired)
        {
            BeginInvoke(() => Log(line));
            return;
        }
        _log.AppendText(line + Environment.NewLine);
    }

    string? SelectedPort()
    {
        if (_devices.SelectedIndex < 0 || _devices.SelectedIndex >= _targets.Count)
            return null;
        if (_targets[_devices.SelectedIndex].TryGetProperty("port", out var p))
            return p.GetString();
        return null;
    }

    async Task RefreshDevicesAsync()
    {
        if (_busy) return;
        SetBusy(true, "Scanning…");
        try
        {
            var (code, stdout, stderr) = await RunPythonAsync(new[] { "provision.py", "--list", "--json" });
            _targets = new List<JsonElement>();
            _devices.Items.Clear();
            ClearCheck();

            if (string.IsNullOrWhiteSpace(stdout))
            {
                _checkStatus.Text = "No devices. Plug in the XIAO e-ink panel.";
                _checkStatus.ForeColor = Color.FromArgb(230, 80, 80);
                Log(stderr.Trim().Length > 0 ? stderr.Trim() : "No output from scanner.");
                return;
            }

            using var doc = JsonDocument.Parse(stdout);
            if (doc.RootElement.TryGetProperty("targets", out var arr))
            {
                foreach (var row in arr.EnumerateArray())
                {
                    _targets.Add(row.Clone());
                    var port = row.GetProperty("port").GetString() ?? "?";
                    var kind = row.TryGetProperty("kind", out var k) ? k.GetString() : "?";
                    var desc = row.TryGetProperty("description", out var d) ? d.GetString() : "";
                    _devices.Items.Add($"{port}   [{kind}]   {desc}");
                }
            }

            if (_devices.Items.Count > 0)
            {
                _devices.SelectedIndex = 0;
                _checkStatus.Text = $"Found {_devices.Items.Count} candidate(s). Press Check.";
                _checkStatus.ForeColor = Color.FromArgb(180, 180, 180);
                Log($"Listed {_devices.Items.Count} target(s).");
            }
            else
            {
                _checkStatus.Text = "No e-ink panel found (random COM devices are ignored).";
                _checkStatus.ForeColor = Color.FromArgb(230, 80, 80);
                Log(code == 0 ? "Empty target list." : stderr.Trim());
            }
        }
        catch (Exception ex)
        {
            MessageBox.Show(this, ex.Message, "Fennsill Factory", MessageBoxButtons.OK, MessageBoxIcon.Error);
            Log("ERROR: " + ex.Message);
        }
        finally
        {
            SetBusy(false);
        }
    }

    async Task CheckAsync()
    {
        if (_busy) return;
        var port = SelectedPort();
        if (string.IsNullOrEmpty(port))
        {
            MessageBox.Show(this, "Select a device first.", "Fennsill Factory", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }

        SetBusy(true, "Checking…");
        _checkStatus.Text = $"Checking {port}…";
        _checkStatus.ForeColor = Color.FromArgb(180, 180, 180);
        Log($"CHECK {port}");
        try
        {
            var (code, stdout, stderr) = await RunPythonAsync(new[] { "provision.py", "--check", "--port", port, "--json" });
            if (code != 0 || string.IsNullOrWhiteSpace(stdout))
                throw new InvalidOperationException(string.IsNullOrWhiteSpace(stderr) ? "Check failed." : stderr.Trim());

            using var doc = JsonDocument.Parse(stdout);
            var target = doc.RootElement.GetProperty("target");
            var kind = target.TryGetProperty("kind", out var k) ? k.GetString() : "?";
            var reason = target.TryGetProperty("reason", out var r) ? r.GetString() : "";
            _checkedPort = port;
            _flashBtn.Enabled = true;
            _checkStatus.Text = $"OK — {port} is a Fennsill e-ink / XIAO panel.\n{kind}: {reason}";
            _checkStatus.ForeColor = Color.FromArgb(120, 200, 140);
            Log($"CHECK OK [{kind}] {reason}");
        }
        catch (Exception ex)
        {
            _checkedPort = null;
            _flashBtn.Enabled = false;
            _checkStatus.Text = "Failed — " + ex.Message;
            _checkStatus.ForeColor = Color.FromArgb(230, 80, 80);
            Log("CHECK FAILED: " + ex.Message);
            MessageBox.Show(this, ex.Message, "Check failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        finally
        {
            SetBusy(false);
        }
    }

    async Task FlashAsync()
    {
        if (_busy) return;
        var port = SelectedPort();
        if (string.IsNullOrEmpty(port) || !string.Equals(port, _checkedPort, StringComparison.OrdinalIgnoreCase))
        {
            MessageBox.Show(this, "Run Check on the selected device first.", "Fennsill Factory", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            _flashBtn.Enabled = false;
            return;
        }

        var confirm = MessageBox.Show(
            this,
            $"Erase chip on {port} and install Fennsill?\n\nThis wipes TRMNL / stock firmware.",
            "Flash panel?",
            MessageBoxButtons.OKCancel,
            MessageBoxIcon.Warning);
        if (confirm != DialogResult.OK) return;

        SetBusy(true, "Flashing…");
        _flashBtn.Text = "Flashing…";
        Log($"FLASH {port} (erase + Fennsill)");
        try
        {
            var (code, stdout, stderr) = await RunPythonAsync(new[] { "provision.py", "--port", port, "--json" }, longTimeout: true);
            if (code != 0)
                throw new InvalidOperationException(TrimErr(stdout, stderr));

            // provision prints progress on stdout; last JSON object line is the result.
            var jsonLine = ExtractLastJsonObject(stdout);
            if (jsonLine is null)
                throw new InvalidOperationException(TrimErr(stdout, stderr));

            using var doc = JsonDocument.Parse(jsonLine);
            var serial = doc.RootElement.GetProperty("serial").GetString();
            var deviceId = doc.RootElement.GetProperty("device_id").GetString();
            var keyFp = doc.RootElement.TryGetProperty("key_fingerprint", out var fp) ? fp.GetString() : "";
            _checkedPort = null;
            _flashBtn.Enabled = false;
            _checkStatus.Text = $"Flashed — serial {serial}   id {deviceId}";
            _checkStatus.ForeColor = Color.FromArgb(120, 200, 140);
            Log($"FLASH OK serial={serial} device_id={deviceId} key_fp={keyFp}");
            MessageBox.Show(
                this,
                $"Serial: {serial}\nDevice ID: {deviceId}\n\nThis serial never changes across PCs.",
                "Flashed",
                MessageBoxButtons.OK,
                MessageBoxIcon.Information);
            await RefreshDevicesAsync();
        }
        catch (Exception ex)
        {
            Log("FLASH FAILED: " + ex.Message);
            MessageBox.Show(this, ex.Message, "Flash failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
            _flashBtn.Enabled = _checkedPort != null;
        }
        finally
        {
            _flashBtn.Text = "Flash Fennsill";
            SetBusy(false);
        }
    }

    void SetBusy(bool busy, string? status = null)
    {
        _busy = busy;
        _refreshBtn.Enabled = !busy;
        _checkBtn.Enabled = !busy;
        if (!busy)
            _flashBtn.Enabled = _checkedPort != null;
        else
            _flashBtn.Enabled = false;
        if (status != null && busy)
            _checkStatus.Text = status;
        UseWaitCursor = busy;
    }

    async Task<(int code, string stdout, string stderr)> RunPythonAsync(string[] args, bool longTimeout = false)
    {
        if (!Directory.Exists(_factoryDir))
            throw new DirectoryNotFoundException($"factory folder missing next to the project:\n{_factoryDir}");

        var python = FindPython();
        var psi = new ProcessStartInfo
        {
            FileName = python,
            WorkingDirectory = _factoryDir,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        foreach (var a in args)
            psi.ArgumentList.Add(a);

        psi.Environment["PYTHONUNBUFFERED"] = "1";
        psi.Environment["FENNSILL_ROOT"] = _repoRoot;
        // Keep tools off Bitdefender's virtual disk (virtual_file.log PermissionError).
        var tmp = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "FennsillApp", "tmp");
        try { Directory.CreateDirectory(tmp); } catch { /* best effort */ }
        psi.Environment["TEMP"] = tmp;
        psi.Environment["TMP"] = tmp;
        psi.Environment["TMPDIR"] = tmp;

        using var proc = new Process { StartInfo = psi, EnableRaisingEvents = true };
        var stdout = new StringBuilder();
        var stderr = new StringBuilder();
        proc.OutputDataReceived += (_, e) =>
        {
            if (e.Data is null) return;
            stdout.AppendLine(e.Data);
            Log(e.Data);
        };
        proc.ErrorDataReceived += (_, e) =>
        {
            if (e.Data is null) return;
            stderr.AppendLine(e.Data);
            Log(e.Data);
        };

        if (!proc.Start())
            throw new InvalidOperationException("Could not start Python.");

        proc.BeginOutputReadLine();
        proc.BeginErrorReadLine();

        var timeout = longTimeout ? TimeSpan.FromMinutes(15) : TimeSpan.FromMinutes(2);
        using var cts = new CancellationTokenSource(timeout);
        try
        {
            await proc.WaitForExitAsync(cts.Token);
        }
        catch (OperationCanceledException)
        {
            try { proc.Kill(entireProcessTree: true); } catch { /* ignore */ }
            throw new TimeoutException("Factory step timed out.");
        }

        return (proc.ExitCode, stdout.ToString(), stderr.ToString());
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
                p.WaitForExit(5000);
                if (p.ExitCode == 0) return name;
            }
            catch
            {
                // try next
            }
        }
        throw new InvalidOperationException(
            "Python not found. Install Python 3 and ensure it is on PATH.\n" +
            "Factory.exe uses factory\\provision.py to talk to the panel.");
    }

    static string? ExtractLastJsonObject(string text)
    {
        string? last = null;
        using var reader = new StringReader(text);
        string? line;
        while ((line = reader.ReadLine()) != null)
        {
            var t = line.Trim();
            if (t.StartsWith('{') && t.EndsWith('}'))
                last = t;
        }
        return last;
    }

    static string TrimErr(string stdout, string stderr)
    {
        var err = (stderr ?? "").Trim();
        if (err.Length > 0) return err;
        var outT = (stdout ?? "").Trim();
        return outT.Length > 0 ? outT : "Unknown flash error.";
    }

    static string ResolveFactoryDir(string repoRoot)
    {
        var nested = Path.Combine(repoRoot, "factory");
        if (File.Exists(Path.Combine(nested, "provision.py")))
            return nested;
        if (File.Exists(Path.Combine(repoRoot, "provision.py")))
            return repoRoot;
        return nested;
    }

    static bool HasFirmware(string root) =>
        File.Exists(Path.Combine(root, "firmware", "panel_ports.py"))
        || File.Exists(Path.Combine(root, "factory", "firmware", "panel_ports.py"));

    static string FindRepoRoot()
    {
        // Prefer the LocalAppData install created by FactoryInstall.
        var installed = FactoryInstall.FactoryDir;
        if (File.Exists(Path.Combine(installed, "provision.py")) && HasFirmware(installed))
            return installed;

        var env = Environment.GetEnvironmentVariable("FENNSILL_ROOT");
        if (!string.IsNullOrWhiteSpace(env)
            && (File.Exists(Path.Combine(env, "factory", "provision.py"))
                || File.Exists(Path.Combine(env, "provision.py")))
            && HasFirmware(env))
            return Path.GetFullPath(env);

        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        for (var i = 0; i < 8 && dir != null; i++, dir = dir.Parent)
        {
            // Exe sitting in …/factory/ (C:\factory or zip\factory)
            if (File.Exists(Path.Combine(dir.FullName, "provision.py"))
                && (File.Exists(Path.Combine(dir.FullName, "firmware", "panel_ports.py"))
                    || (dir.Parent != null
                        && File.Exists(Path.Combine(dir.Parent.FullName, "firmware", "panel_ports.py")))))
            {
                if (dir.Parent != null
                    && File.Exists(Path.Combine(dir.Parent.FullName, "firmware", "panel_ports.py")))
                    return dir.Parent.FullName;
                return dir.FullName;
            }

            if (Directory.Exists(Path.Combine(dir.FullName, "factory"))
                && File.Exists(Path.Combine(dir.FullName, "factory", "provision.py"))
                && HasFirmware(dir.FullName))
                return dir.FullName;
        }

        var beside = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, ".."));
        if (Directory.Exists(Path.Combine(beside, "factory")) && HasFirmware(beside))
            return beside;

        return Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", ".."));
    }
}
