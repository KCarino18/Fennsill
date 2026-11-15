using System.Diagnostics;
using System.Text;
using System.Text.Json;

namespace ArtiphactDesk;

/// <summary>
/// Artiphact owns the whole buyer flow: watch for the panel, configure every
/// AI desktop app, run the bridge/live workers, and stay out of the way.
/// </summary>
public class MainForm : Form
{
    const int RotateIntervalSec = 8;

    readonly string _root;
    readonly string _pagesDir;
    readonly string _playlistPath;
    readonly FlowLayoutPanel _gallery = new();
    readonly Panel _previewPane = new();
    readonly PictureBox _previewBox = new();
    readonly Label _previewCaption = new();
    readonly Label _readyBanner = new();
    readonly Label _status = new();
    readonly Label _rotateStatus = new();
    readonly Button _rotateToggle = new();
    readonly System.Windows.Forms.Timer _panelTimer = new();
    readonly System.Windows.Forms.Timer _galleryDebounce = new();
    FileSystemWatcher? _watcher;
    readonly Dictionary<string, Image> _thumbs = new();
    Image? _previewImage;
    string? _previewPageId;
    bool _followNewestOnReload;
    readonly HashSet<string> _selectedPageIds = new(StringComparer.OrdinalIgnoreCase);
    Process? _bridgeProcess;
    Process? _liveProcess;
    Process? _liveJobsProcess;
    Process? _rotateProcess;
    bool _panelReady;
    bool _setupRanForThisPlug;
    bool _rotateEnabled;
    string _panelPorts = "";

    public MainForm()
    {
        _root = FindProjectRoot();
        _pagesDir = Path.Combine(_root, "connector", "pages");
        _playlistPath = Path.Combine(_root, "connector", "rotate_playlist.json");
        Directory.CreateDirectory(_pagesDir);
        Directory.CreateDirectory(Path.Combine(_root, "connector", "inbox"));
        LoadPlaylist();
        BuildUi();
        StartWatch();
        StartBackgroundServices();
        ReloadGallery(followNewest: true);
        UpdateRotateUi();
        _panelTimer.Interval = 3000;
        _panelTimer.Tick += async (_, _) => await RefreshPanelStatus();
        _panelTimer.Start();
        _galleryDebounce.Interval = 450;
        _galleryDebounce.Tick += (_, _) =>
        {
            _galleryDebounce.Stop();
            var follow = _followNewestOnReload;
            _followNewestOnReload = false;
            ReloadGallery(followNewest: follow);
        };
        _ = RefreshPanelStatus();
    }

    static string FindProjectRoot()
    {
        var env = Environment.GetEnvironmentVariable("ARTIPHACT_ROOT");
        if (!string.IsNullOrWhiteSpace(env) && HasConnector(env)) return env;

        // Installed copy is canonical — Host MCP / ChatGPT write pages here.
        var installed = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Artiphact");
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
        // Modern gallery shell — panel + pages only. AI MCP lives in Artiphact Host.
        var bg = Color.FromArgb(18, 20, 24);
        var surface = Color.FromArgb(28, 31, 36);
        var text = Color.FromArgb(242, 240, 235);
        var muted = Color.FromArgb(154, 149, 140);

        Text = "Artiphact";
        Width = 1200;
        Height = 780;
        MinimumSize = new Size(960, 640);
        StartPosition = FormStartPosition.CenterScreen;
        BackColor = bg;
        ForeColor = text;
        Font = new Font("Segoe UI", 10F);
        try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { /* default */ }

        var top = new Panel
        {
            Dock = DockStyle.Top,
            Height = 118,
            BackColor = surface,
            Padding = new Padding(20, 16, 20, 12),
        };

        var title = new Label
        {
            Text = "Artiphact",
            Font = new Font("Segoe UI Semibold", 20F),
            ForeColor = text,
            AutoSize = true,
            Location = new Point(20, 14),
        };

        _readyBanner.Location = new Point(20, 48);
        _readyBanner.Size = new Size(640, 24);
        _readyBanner.Font = new Font("Segoe UI Semibold", 12F);
        _readyBanner.ForeColor = Color.FromArgb(232, 184, 74);
        _readyBanner.Text = "Waiting for panel…";

        _status.Location = new Point(20, 74);
        _status.AutoSize = true;
        _status.MaximumSize = new Size(560, 0);
        _status.ForeColor = muted;
        _status.Text = "Pages from ChatGPT / Claude appear here when Host MCP pushes.";

        var actions = new FlowLayoutPanel
        {
            Location = new Point(680, 18),
            Size = new Size(500, 88),
            Anchor = AnchorStyles.Top | AnchorStyles.Right,
            FlowDirection = FlowDirection.LeftToRight,
            WrapContents = true,
            BackColor = Color.Transparent,
        };

        Button ActionBtn(string label)
        {
            return new Button
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
        }

        var refresh = ActionBtn("Refresh");
        var importBtn = ActionBtn("Import HTML");
        var paste = ActionBtn("Paste page");
        _rotateToggle.Text = "Start rotate";
        _rotateToggle.AutoSize = true;
        _rotateToggle.FlatStyle = FlatStyle.Flat;
        _rotateToggle.BackColor = Color.FromArgb(40, 44, 52);
        _rotateToggle.ForeColor = text;
        _rotateToggle.Padding = new Padding(12, 6, 12, 6);
        _rotateToggle.Margin = new Padding(0, 0, 8, 8);
        _rotateToggle.Cursor = Cursors.Hand;
        _rotateToggle.Click += (_, _) => ToggleRotate();

        refresh.Click += async (_, _) =>
        {
            ReloadGallery(followNewest: true);
            await RefreshPanelStatus();
        };
        importBtn.Click += async (_, _) => await ImportHtmlFile();
        paste.Click += async (_, _) => await PastePage();

        actions.Controls.Add(refresh);
        actions.Controls.Add(importBtn);
        actions.Controls.Add(paste);
        actions.Controls.Add(_rotateToggle);

        _rotateStatus.Location = new Point(20, 94);
        _rotateStatus.AutoSize = true;
        _rotateStatus.MaximumSize = new Size(640, 0);
        _rotateStatus.ForeColor = muted;
        _rotateStatus.Text = "Click a screen to show it, or select screens and start rotate.";

        top.Controls.Add(title);
        top.Controls.Add(_readyBanner);
        top.Controls.Add(_status);
        top.Controls.Add(_rotateStatus);
        top.Controls.Add(actions);
        top.Resize += (_, _) =>
        {
            actions.Left = Math.Max(420, top.ClientSize.Width - actions.Width - 16);
        };

        _previewPane.Dock = DockStyle.Right;
        _previewPane.Width = 460;
        _previewPane.Padding = new Padding(16);
        _previewPane.BackColor = surface;
        _previewCaption.Text = "Preview";
        _previewCaption.Font = new Font("Segoe UI Semibold", 11F);
        _previewCaption.ForeColor = text;
        _previewCaption.AutoSize = true;
        _previewCaption.Location = new Point(16, 14);
        _previewBox.Location = new Point(16, 44);
        _previewBox.Size = new Size(428, 257);
        _previewBox.SizeMode = PictureBoxSizeMode.Zoom;
        _previewBox.BorderStyle = BorderStyle.None;
        _previewBox.BackColor = Color.FromArgb(10, 12, 14);
        _previewBox.Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right;
        _previewPane.Controls.Add(_previewCaption);
        _previewPane.Controls.Add(_previewBox);
        _previewPane.Resize += (_, _) =>
        {
            _previewBox.Width = Math.Max(200, _previewPane.ClientSize.Width - 32);
            _previewBox.Height = Math.Max(120, (int)(_previewBox.Width * 480.0 / 800.0));
        };

        var galleryHeader = new Label
        {
            Text = "Screens",
            Font = new Font("Segoe UI Semibold", 11F),
            ForeColor = muted,
            Dock = DockStyle.Top,
            Height = 36,
            Padding = new Padding(16, 10, 0, 0),
            BackColor = bg,
        };

        _gallery.Dock = DockStyle.Fill;
        _gallery.AutoScroll = true;
        _gallery.Padding = new Padding(12);
        _gallery.WrapContents = true;
        _gallery.BackColor = bg;

        var galleryHost = new Panel { Dock = DockStyle.Fill, BackColor = bg };
        galleryHost.Controls.Add(_gallery);
        galleryHost.Controls.Add(galleryHeader);

        Controls.Add(galleryHost);
        Controls.Add(_previewPane);
        Controls.Add(top);
    }

    void StartBackgroundServices()
    {
        // Local workers only. Public tunnels belong to Artiphact Host (opt-in).
        try
        {
            using var killer = StartPython("connector\\kill_orphans.py");
            killer?.WaitForExit(8000);
        }
        catch { /* still start fresh workers */ }
        _bridgeProcess = StartPython("connector\\http_bridge.py");
        _liveProcess = StartPython("connector\\live_watch.py");
        _liveJobsProcess = StartPython("connector\\live_jobs.py");
        EnsureRotateWorker();
    }

    void EnsureRotateWorker()
    {
        if (_rotateProcess is { HasExited: false }) return;
        _rotateProcess = StartPython("connector\\rotate_pages.py");
    }

    void StartWatch()
    {
        _watcher = new FileSystemWatcher(_pagesDir)
        {
            IncludeSubdirectories = true,
            NotifyFilter = NotifyFilters.FileName | NotifyFilters.DirectoryName | NotifyFilters.LastWrite | NotifyFilters.CreationTime,
        };
        // MCP writes folder then frame/preview/meta — debounce so the card is complete,
        // and follow the newest page so ChatGPT/Claude pushes show in the app immediately.
        void Kick(object? s, FileSystemEventArgs e)
        {
            if (IsDisposed) return;
            BeginInvoke(() =>
            {
                _followNewestOnReload = true;
                _galleryDebounce.Stop();
                _galleryDebounce.Start();
            });
        }
        _watcher.Created += Kick;
        _watcher.Changed += Kick;
        _watcher.Deleted += Kick;
        _watcher.Renamed += (_, e) => Kick(_, e);
        _watcher.EnableRaisingEvents = true;
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
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true,
            };
            psi.Environment["ARTIPHACT_ROOT"] = _root;
            psi.Environment["ARTIPHACT_PAGES"] = _pagesDir;
            psi.Environment["PLAYWRIGHT_BROWSERS_PATH"] = Path.Combine(_root, "connector", "browsers");
            return Process.Start(psi);
        }
        catch { return null; }
    }

    void OnPanelPluggedIn()
    {
        if (_setupRanForThisPlug) return;
        _setupRanForThisPlug = true;
        _status.Text = "Panel detected — Artiphact is configuring your AI apps…";
        Task.Run(() =>
        {
            try
            {
                using var proc = StartPython("connector\\bootstrap.py");
                proc?.WaitForExit(20000);
            }
            catch { /* still show ready */ }
            if (IsHandleCreated)
                BeginInvoke(async () =>
                {
                    _status.Text = "Panel ready. Use Artiphact Host for ChatGPT / Claude MCP.";
                    UpdateReadyBanner();
                });
        });
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
        catch { /* keep last */ }

        if (_panelReady && !wasReady)
            OnPanelPluggedIn();
        if (!_panelReady)
            _setupRanForThisPlug = false;

        if (IsHandleCreated) BeginInvoke(UpdateReadyBanner);
        else UpdateReadyBanner();
    }

    void UpdateReadyBanner()
    {
        if (_panelReady)
        {
            _readyBanner.Text = "Panel connected";
            _readyBanner.ForeColor = Color.FromArgb(61, 214, 140);
            _readyBanner.BackColor = Color.Transparent;
            if (string.IsNullOrWhiteSpace(_status.Text) || _status.Text.StartsWith("Waiting") || _status.Text.StartsWith("Seen") || _status.Text.StartsWith("Panel"))
                _status.Text = string.IsNullOrEmpty(_panelPorts) ? "Panel connected." : $"Panel {_panelPorts}";
        }
        else
        {
            _readyBanner.Text = "Waiting for panel…";
            _readyBanner.ForeColor = Color.FromArgb(232, 184, 74);
            _readyBanner.BackColor = Color.Transparent;
            _status.Text = string.IsNullOrEmpty(_panelPorts) ? "Waiting for panel." : $"Seen: {_panelPorts}";
        }
    }

    async Task PastePage()
    {
        string text;
        try { text = Clipboard.GetText(); }
        catch { text = ""; }
        if (string.IsNullOrWhiteSpace(text))
        {
            MessageBox.Show(this, "Clipboard is empty. Copy the HTML from your AI first.", "Artiphact");
            return;
        }
        var tmp = Path.Combine(Path.GetTempPath(), "artiphact-paste.html");
        await File.WriteAllTextAsync(tmp, text, Encoding.UTF8);
        await IngestFile(tmp, "clipboard");
    }

    async Task ImportHtmlFile()
    {
        using var dlg = new OpenFileDialog
        {
            Filter = "HTML/SVG|*.html;*.htm;*.svg|All files|*.*",
            Title = "Import page for Artiphact",
        };
        if (dlg.ShowDialog(this) != DialogResult.OK) return;
        await IngestFile(dlg.FileName, "import");
    }

    async Task IngestFile(string path, string source)
    {
        _status.Text = "Importing…";
        var script = Path.Combine(_root, "connector", "ingest_page.py");
        if (!File.Exists(script))
        {
            MessageBox.Show(this, "Import script missing — reopen Artiphact from the install folder.", "Artiphact");
            _status.Text = "Import failed.";
            return;
        }
        var isSvg = path.EndsWith(".svg", StringComparison.OrdinalIgnoreCase);
        var arg = isSvg ? $"--svg-file \"{path}\"" : $"--html-file \"{path}\"";
        // Push only when rotate is off so we do not fight the playlist.
        var pushArg = _rotateEnabled ? "" : " --push";
        var title = Path.GetFileNameWithoutExtension(path).Replace("\"", "");
        var psi = new ProcessStartInfo
        {
            FileName = "python",
            Arguments = $"\"{script}\" {arg} --source \"{source}\" --title \"{title}\"{pushArg}",
            WorkingDirectory = _root,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
        };
        psi.Environment["ARTIPHACT_ROOT"] = _root;
        psi.Environment["ARTIPHACT_PAGES"] = _pagesDir;
        psi.Environment["PLAYWRIGHT_BROWSERS_PATH"] = Path.Combine(_root, "connector", "browsers");
        try
        {
            using var proc = Process.Start(psi) ?? throw new InvalidOperationException("Could not start Python.");
            var stdout = await proc.StandardOutput.ReadToEndAsync();
            var stderr = await proc.StandardError.ReadToEndAsync();
            await proc.WaitForExitAsync();
            if (proc.ExitCode != 0)
            {
                var err = string.IsNullOrWhiteSpace(stderr) ? stdout : stderr;
                if (err.Length > 400) err = err[..400] + "…";
                MessageBox.Show(this, string.IsNullOrWhiteSpace(err) ? "Import failed." : err.Trim(), "Import failed");
                _status.Text = "Import failed.";
                return;
            }
            ReloadGallery();
            string note = "Saved to gallery.";
            try
            {
                using var doc = JsonDocument.Parse(string.IsNullOrWhiteSpace(stdout) ? "{}" : stdout);
                if (doc.RootElement.TryGetProperty("note", out var n))
                    note = n.GetString() ?? note;
                else if (doc.RootElement.TryGetProperty("pushed", out var p) && p.GetBoolean())
                    note = "Saved and sent to the panel.";
                else if (_rotateEnabled)
                    note = "Saved to gallery (rotate is on — click Stop rotate, then click the preview to show it).";
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

    void ReloadGallery(bool followNewest = false)
    {
        foreach (Control c in _gallery.Controls) c.Dispose();
        _gallery.Controls.Clear();
        foreach (var img in _thumbs.Values) img.Dispose();
        _thumbs.Clear();

        var pages = Directory.Exists(_pagesDir)
            ? Directory.GetDirectories(_pagesDir).OrderByDescending(d => d).ToArray()
            : Array.Empty<string>();
        if (pages.Length == 0)
        {
            ClearLargePreview("No pages yet");
            _gallery.Controls.Add(new Label
            {
                Text = "Say to Claude or ChatGPT: “Keep NFL scores up to date on my Artiphact panel.”",
                AutoSize = true,
                Padding = new Padding(8),
                MaximumSize = new Size(900, 0),
            });
            return;
        }

        string? newestId = null;
        string? newestTitle = null;
        string? newestPreview = null;
        foreach (var folder in pages)
        {
            var metaPath = Path.Combine(folder, "meta.json");
            var previewPath = Path.Combine(folder, "preview.png");
            if (!File.Exists(metaPath) || !File.Exists(previewPath)) continue;
            try
            {
                using var doc = JsonDocument.Parse(File.ReadAllText(metaPath));
                var id = doc.RootElement.GetProperty("id").GetString() ?? Path.GetFileName(folder);
                var title = doc.RootElement.TryGetProperty("title", out var t) ? (t.GetString() ?? id) : id;
                _gallery.Controls.Add(MakeCard(folder, id, title, previewPath));
                if (newestId == null)
                {
                    newestId = id;
                    newestTitle = title;
                    newestPreview = previewPath;
                }
            }
            catch { /* skip */ }
        }

        // External MCP pushes should jump the big preview to the new page.
        if (followNewest && newestId != null && newestPreview != null)
        {
            ShowLargePreview(newestId, newestTitle ?? newestId, newestPreview);
            _status.Text = "New page from AI — shown in gallery.";
            return;
        }

        if (_previewPageId != null)
        {
            var keep = Path.Combine(_pagesDir, _previewPageId, "preview.png");
            if (File.Exists(keep))
            {
                var title = _previewPageId;
                var metaKeep = Path.Combine(_pagesDir, _previewPageId, "meta.json");
                if (File.Exists(metaKeep))
                {
                    try
                    {
                        using var doc = JsonDocument.Parse(File.ReadAllText(metaKeep));
                        if (doc.RootElement.TryGetProperty("title", out var t) && t.GetString() is { } s)
                            title = s;
                    }
                    catch { /* keep id */ }
                }
                ShowLargePreview(_previewPageId, title, keep);
                return;
            }
        }
        if (newestId != null && newestPreview != null)
            ShowLargePreview(newestId, newestTitle ?? newestId, newestPreview);
        else
            ClearLargePreview("No preview");
    }

    void ClearLargePreview(string caption)
    {
        _previewPageId = null;
        _previewCaption.Text = caption;
        _previewBox.Image = null;
        _previewImage?.Dispose();
        _previewImage = null;
    }

    void ShowLargePreview(string id, string title, string previewPath)
    {
        try
        {
            using var fs = File.OpenRead(previewPath);
            using var img = Image.FromStream(fs);
            var copy = new Bitmap(img);
            _previewImage?.Dispose();
            _previewImage = copy;
            _previewBox.Image = copy;
            _previewPageId = id;
            var shortTitle = title.Length > 36 ? title[..36] + "…" : title;
            _previewCaption.Text = $"Preview · {shortTitle}";
        }
        catch
        {
            ClearLargePreview("Preview unavailable");
        }
    }

    Control MakeCard(string folder, string id, string title, string previewPath)
    {
        var card = new Panel
        {
            Width = 280,
            Height = 268,
            Margin = new Padding(10),
            BackColor = Color.FromArgb(28, 31, 36),
            Cursor = Cursors.Hand,
        };
        Image thumb;
        try
        {
            using var fs = File.OpenRead(previewPath);
            using var img = Image.FromStream(fs);
            thumb = new Bitmap(img, new Size(256, 154));
            _thumbs[id] = thumb;
        }
        catch
        {
            thumb = new Bitmap(256, 154);
            using var g = Graphics.FromImage(thumb);
            g.Clear(Color.Black);
        }
        var pic = new PictureBox
        {
            Image = thumb,
            SizeMode = PictureBoxSizeMode.Zoom,
            Width = 256,
            Height = 154,
            Location = new Point(8, 8),
            BorderStyle = BorderStyle.FixedSingle,
            BackColor = Color.Black,
            Cursor = Cursors.Hand,
        };
        var titleLabel = new Label
        {
            Text = title.Length > 28 ? title[..28] + "…" : title,
            Location = new Point(8, 168),
            Width = 256,
            ForeColor = Color.FromArgb(242, 240, 235),
            Cursor = Cursors.Hand,
        };
        void ShowThis(object? s, EventArgs e)
        {
            ShowLargePreview(id, title, previewPath);
            ShowPage(id, title);
        }
        pic.Click += ShowThis;
        titleLabel.Click += ShowThis;
        card.Click += ShowThis;
        card.Controls.Add(pic);
        card.Controls.Add(titleLabel);
        var include = new CheckBox
        {
            Text = "In rotate",
            Location = new Point(8, 192),
            Width = 120,
            Height = 24,
            ForeColor = Color.FromArgb(154, 149, 140),
            Checked = _selectedPageIds.Contains(id),
        };
        include.CheckedChanged += (_, _) =>
        {
            if (include.Checked) _selectedPageIds.Add(id);
            else _selectedPageIds.Remove(id);
            SavePlaylist();
            UpdateRotateUi();
        };
        card.Controls.Add(include);
        var del = new Button
        {
            Text = "Delete",
            Location = new Point(8, 222),
            Width = 90,
            Height = 28,
            FlatStyle = FlatStyle.Flat,
            BackColor = Color.FromArgb(40, 44, 52),
            ForeColor = Color.FromArgb(242, 240, 235),
        };
        del.Click += (_, _) =>
        {
            if (MessageBox.Show(this, "Delete this page?", "Artiphact", MessageBoxButtons.YesNo) != DialogResult.Yes)
                return;
            try
            {
                if (_thumbs.Remove(id, out var img)) img.Dispose();
                _selectedPageIds.Remove(id);
                Directory.Delete(folder, true);
                SavePlaylist();
                ReloadGallery();
                UpdateRotateUi();
            }
            catch (Exception ex) { MessageBox.Show(this, ex.Message); }
        };
        card.Controls.Add(del);
        return card;
    }

    void ShowPage(string pageId, string title)
    {
        if (_rotateEnabled)
        {
            MessageBox.Show(this, "Stop rotate first, then click a screen to show it.", "Artiphact");
            return;
        }
        var shortTitle = string.IsNullOrWhiteSpace(title) ? pageId : title;
        if (shortTitle.Length > 40) shortTitle = shortTitle[..40] + "…";
        _status.Text = $"Showing “{shortTitle}”…";
        _ = Task.Run(async () =>
        {
            var script = Path.Combine(_root, "connector", "push_page.py");
            string message;
            try
            {
                if (!File.Exists(script))
                {
                    message = "Push script missing.";
                }
                else
                {
                    var psi = new ProcessStartInfo
                    {
                        FileName = "python",
                        Arguments = $"\"{script}\" \"{pageId}\"",
                        WorkingDirectory = _root,
                        UseShellExecute = false,
                        RedirectStandardOutput = true,
                        RedirectStandardError = true,
                        CreateNoWindow = true,
                    };
                    psi.Environment["ARTIPHACT_ROOT"] = _root;
                    psi.Environment["ARTIPHACT_PAGES"] = _pagesDir;
                    using var proc = Process.Start(psi);
                    if (proc == null)
                    {
                        message = "Could not start push.";
                    }
                    else
                    {
                        var stdout = await proc.StandardOutput.ReadToEndAsync();
                        var stderr = await proc.StandardError.ReadToEndAsync();
                        await proc.WaitForExitAsync();
                        if (proc.ExitCode == 0)
                            message = $"Showing “{shortTitle}”.";
                        else
                        {
                            var err = (stderr + "\n" + stdout).Trim();
                            if (err.Length > 120) err = err[..120] + "…";
                            message = string.IsNullOrWhiteSpace(err) ? "Push failed." : err;
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                message = ex.Message;
            }
            if (IsHandleCreated)
                BeginInvoke(() => _status.Text = message);
        });
    }

    void LoadPlaylist()
    {
        _selectedPageIds.Clear();
        _rotateEnabled = false;
        if (!File.Exists(_playlistPath)) return;
        try
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(_playlistPath));
            _rotateEnabled = doc.RootElement.TryGetProperty("enabled", out var en) && en.GetBoolean();
            if (doc.RootElement.TryGetProperty("page_ids", out var ids) && ids.ValueKind == JsonValueKind.Array)
            {
                foreach (var id in ids.EnumerateArray())
                {
                    var s = id.GetString();
                    if (!string.IsNullOrWhiteSpace(s)) _selectedPageIds.Add(s);
                }
            }
        }
        catch { /* start empty */ }
    }

    void SavePlaylist()
    {
        // Keep stable order: gallery newest-first, then any leftover ids.
        var ordered = new List<string>();
        if (Directory.Exists(_pagesDir))
        {
            foreach (var folder in Directory.GetDirectories(_pagesDir).OrderByDescending(d => d))
            {
                var id = Path.GetFileName(folder);
                if (_selectedPageIds.Contains(id)) ordered.Add(id);
            }
        }
        foreach (var id in _selectedPageIds)
            if (!ordered.Contains(id, StringComparer.OrdinalIgnoreCase))
                ordered.Add(id);

        var payload = new Dictionary<string, object?>
        {
            ["enabled"] = _rotateEnabled,
            ["interval_sec"] = RotateIntervalSec,
            ["page_ids"] = ordered,
        };
        File.WriteAllText(_playlistPath, JsonSerializer.Serialize(payload, new JsonSerializerOptions { WriteIndented = true }) + "\n");
    }

    void ToggleRotate()
    {
        if (!_rotateEnabled)
        {
            if (_selectedPageIds.Count == 0)
            {
                MessageBox.Show(this, "Check at least one screen under “In rotate”, then start.", "Artiphact");
                return;
            }
            _rotateEnabled = true;
            SavePlaylist();
            EnsureRotateWorker();
        }
        else
        {
            _rotateEnabled = false;
            SavePlaylist();
        }
        UpdateRotateUi();
    }

    void UpdateRotateUi()
    {
        _rotateToggle.Text = _rotateEnabled ? "Stop rotate" : "Start rotate";
        var count = _selectedPageIds.Count;
        if (_rotateEnabled && count > 0)
            _rotateStatus.Text = $"Rotating {count} screen{(count == 1 ? "" : "s")} every {RotateIntervalSec}s — keeps running after you close Artiphact. Stop rotate to click a single screen.";
        else if (count > 0)
            _rotateStatus.Text = $"{count} screen{(count == 1 ? "" : "s")} selected. Click a preview to show it, or Start rotate ({RotateIntervalSec}s).";
        else
            _rotateStatus.Text = "Click a screen to show it. Or check screens and start rotate (8s each).";
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
        _galleryDebounce.Stop();
        _watcher?.Dispose();
        foreach (var img in _thumbs.Values) img.Dispose();
        _previewImage?.Dispose();
        _previewImage = null;
        SavePlaylist();
        Kill(_liveProcess);
        Kill(_liveJobsProcess);
        Kill(_bridgeProcess);
        // Leave the rotate worker alive when rotation is on so the playlist
        // keeps cycling after Artiphact closes.
        if (!_rotateEnabled)
            Kill(_rotateProcess);
        else
            _rotateProcess = null;
        base.OnFormClosed(e);
    }
}
