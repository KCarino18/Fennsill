using System.Diagnostics;
using System.Reflection;
using System.ServiceProcess;
using Microsoft.Win32;

namespace FennsillSetup;

static class Program
{
    const string ServiceName = "FennsillAgent";
    const string ServiceDisplayName = "FennSill Agent";
    const string UninstallRegPath = @"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Fennsill";
    const string ProductName = "FennSill";

    [STAThread]
    static void Main(string[] args)
    {
        Application.SetHighDpiMode(HighDpiMode.SystemAware);
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);

        var uninstall = args.Any(a =>
            a.Equals("/uninstall", StringComparison.OrdinalIgnoreCase) ||
            a.Equals("-uninstall", StringComparison.OrdinalIgnoreCase) ||
            a.Equals("--uninstall", StringComparison.OrdinalIgnoreCase));
        var quiet = args.Any(a =>
            a.Equals("/S", StringComparison.OrdinalIgnoreCase) ||
            a.Equals("/silent", StringComparison.OrdinalIgnoreCase) ||
            a.Equals("-silent", StringComparison.OrdinalIgnoreCase));

        try
        {
            if (uninstall)
                Uninstall(quiet);
            else
                Install(quiet);
        }
        catch (Exception ex)
        {
            if (!quiet)
                MessageBox.Show(ex.ToString(), "FennSill Setup failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
            Environment.ExitCode = 1;
        }
    }

    static string ProductVersion
    {
        get
        {
            var info = Assembly.GetExecutingAssembly()
                .GetCustomAttribute<AssemblyInformationalVersionAttribute>()
                ?.InformationalVersion;
            if (!string.IsNullOrWhiteSpace(info))
            {
                // Strip any +git metadata from InformationalVersion.
                var v = info.Split('+', '-')[0].Trim();
                if (!string.IsNullOrWhiteSpace(v)) return v;
            }
            return Assembly.GetExecutingAssembly().GetName().Version?.ToString(3) ?? "0.0.0";
        }
    }

    static void Install(bool quiet)
    {
        if (!quiet)
        {
            var result = MessageBox.Show(
                "Install FennSill on this PC?\n\n" +
                "• Desk app (Device ID / Paste device key)\n" +
                "• FennSill Agent Windows service (USB cloud push — stays on when Desk is closed)\n" +
                "• Adds FennSill to Installed apps (Settings → Apps)\n\n" +
                "Admin permission is required to install the service.",
                "FennSill Setup",
                MessageBoxButtons.OKCancel,
                MessageBoxIcon.Information);
            if (result != DialogResult.OK) return;
        }

        var payload = FindPayloadRoot();
        if (payload == null)
            throw new InvalidOperationException(
                "Install payload was not found. Use the official FennsillSetup.exe release.");

        var userLocal = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        var dest = Path.Combine(userLocal, "FennsillApp");
        Directory.CreateDirectory(dest);

        TryStopService();
        RunSc($"stop {ServiceName}");
        Thread.Sleep(500);

        CopyTree(payload, dest);
        foreach (var name in new[] { "Fennsill.exe", "FennsillDesk.exe", "FennsillAgent.exe" })
        {
            var src = Path.Combine(payload, name);
            if (File.Exists(src))
                File.Copy(src, Path.Combine(dest, name == "FennsillDesk.exe" ? "Fennsill.exe" : name), overwrite: true);
        }

        EnsureCriticalFiles(dest);

        // Keep a copy of Setup for Apps & features → Uninstall.
        var setupDest = Path.Combine(dest, "FennsillSetup.exe");
        try
        {
            File.Copy(Application.ExecutablePath, setupDest, overwrite: true);
        }
        catch (IOException)
        {
            // Already running from dest — fine.
            if (!File.Exists(setupDest))
                throw;
        }

        var programData = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
            "Fennsill");
        Directory.CreateDirectory(programData);
        File.WriteAllText(
            Path.Combine(programData, "user_localappdata.txt"),
            userLocal + Environment.NewLine);
        File.WriteAllText(
            Path.Combine(programData, "install_root.txt"),
            dest + Environment.NewLine);

        if (!quiet)
        {
            MessageBox.Show(
                "Next: FennSill will install Python and Playwright (needed for USB page pushes).\n" +
                "This needs internet and may take a few minutes.",
                "FennSill Setup",
                MessageBoxButtons.OK,
                MessageBoxIcon.Information);
        }

        EnsureRuntime(dest, quiet);

        var agentExe = Path.Combine(dest, "FennsillAgent.exe");
        if (!File.Exists(agentExe))
            throw new FileNotFoundException("FennsillAgent.exe missing after install.", agentExe);

        InstallOrUpdateService(agentExe);
        StartService();
        WaitForAgentStatus(dest, quiet);

        var deskExe = FirstExisting(dest, "Fennsill.exe", "FennsillDesk.exe")
            ?? throw new FileNotFoundException("Fennsill.exe missing after install.");
        TryDesktopShortcut(deskExe, dest);
        TryStartMenuShortcut(deskExe, dest);
        // Remove legacy shortcut name from older installs.
        TryDeleteShortcut(
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "Fennsill.lnk"));
        InstallQuickStartPdf(dest, payload);
        RegisterUninstall(dest, deskExe, setupDest);

        if (!quiet)
        {
            MessageBox.Show(
                "FennSill is installed.\n\n" +
                $"Folder: {dest}\n" +
                "Service: FennSill Agent (Automatic)\n" +
                "Listed under Settings → Apps → Installed apps\n" +
                "Quick Start PDF saved to your Desktop.\n\n" +
                "Next: plug in the panel → copy Device ID → link on the website → Paste device key.\n" +
                "Then connect ChatGPT/Claude/Cursor with the account MCP URL + Bearer header.",
                "FennSill Setup",
                MessageBoxButtons.OK,
                MessageBoxIcon.Information);
        }

        try
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = deskExe,
                WorkingDirectory = dest,
                UseShellExecute = true,
            });
        }
        catch
        {
            /* optional */
        }
    }

    static void Uninstall(bool quiet)
    {
        if (!quiet)
        {
            var result = MessageBox.Show(
                "Uninstall FennSill?\n\nThis removes the Agent service, Desk files, shortcuts, and the Apps entry.",
                "FennSill Setup",
                MessageBoxButtons.OKCancel,
                MessageBoxIcon.Warning);
            if (result != DialogResult.OK) return;
        }

        TryStopService();
        RunSc($"stop {ServiceName}");
        Thread.Sleep(500);
        RunSc($"delete {ServiceName}");

        var dest = ResolveInstallRoot();
        TryDeleteShortcut(
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "FennSill.lnk"));
        TryDeleteShortcut(
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "FennSill Quick Start.pdf"));
        TryDeleteShortcut(
            Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.CommonStartMenu),
                "Programs",
                "FennSill",
                "FennSill.lnk"));
        try
        {
            var startDir = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.CommonStartMenu),
                "Programs",
                "FennSill");
            if (Directory.Exists(startDir))
                Directory.Delete(startDir, recursive: true);
        }
        catch { /* optional */ }

        UnregisterUninstall();

        try
        {
            var programData = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
                "Fennsill");
            if (Directory.Exists(programData))
                Directory.Delete(programData, recursive: true);
        }
        catch { /* optional */ }

        // Delete install tree after this process exits if we are running from inside it.
        var setupInDest = Path.Combine(dest, "FennsillSetup.exe");
        var runningFromDest = string.Equals(
            Path.GetFullPath(Application.ExecutablePath),
            Path.GetFullPath(setupInDest),
            StringComparison.OrdinalIgnoreCase);

        if (runningFromDest)
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = "cmd.exe",
                Arguments = $"/C timeout /t 2 /nobreak >nul & rmdir /s /q \"{dest}\"",
                UseShellExecute = false,
                CreateNoWindow = true,
            });
        }
        else if (Directory.Exists(dest))
        {
            try { Directory.Delete(dest, recursive: true); }
            catch
            {
                Process.Start(new ProcessStartInfo
                {
                    FileName = "cmd.exe",
                    Arguments = $"/C timeout /t 2 /nobreak >nul & rmdir /s /q \"{dest}\"",
                    UseShellExecute = false,
                    CreateNoWindow = true,
                });
            }
        }

        if (!quiet)
        {
            MessageBox.Show(
                "FennSill has been uninstalled.",
                "FennSill Setup",
                MessageBoxButtons.OK,
                MessageBoxIcon.Information);
        }
    }

    static string ResolveInstallRoot()
    {
        try
        {
            var marker = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
                "Fennsill",
                "install_root.txt");
            if (File.Exists(marker))
            {
                var line = File.ReadAllText(marker).Trim().Split('\n', '\r')[0].Trim().Trim('"');
                if (!string.IsNullOrWhiteSpace(line)) return line;
            }
        }
        catch { /* fall through */ }

        using (var key = Registry.LocalMachine.OpenSubKey(UninstallRegPath))
        {
            var loc = key?.GetValue("InstallLocation") as string;
            if (!string.IsNullOrWhiteSpace(loc)) return loc.TrimEnd('\\');
        }

        return Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "FennsillApp");
    }

    static void RegisterUninstall(string dest, string deskExe, string setupExe)
    {
        using var key = Registry.LocalMachine.CreateSubKey(UninstallRegPath)
            ?? throw new InvalidOperationException("Could not write Uninstall registry key (need Admin).");

        var sizeKb = EstimateSizeKb(dest);
        key.SetValue("DisplayName", ProductName);
        key.SetValue("DisplayVersion", ProductVersion);
        key.SetValue("Publisher", "FennSill");
        key.SetValue("InstallLocation", dest);
        key.SetValue("InstallDate", DateTime.Now.ToString("yyyyMMdd"));
        key.SetValue("DisplayIcon", deskExe + ",0");
        key.SetValue("UninstallString", $"\"{setupExe}\" /uninstall");
        key.SetValue("QuietUninstallString", $"\"{setupExe}\" /uninstall /S");
        key.SetValue("NoModify", 1, RegistryValueKind.DWord);
        key.SetValue("NoRepair", 1, RegistryValueKind.DWord);
        key.SetValue("EstimatedSize", sizeKb, RegistryValueKind.DWord);
        key.SetValue("URLInfoAbout", "https://github.com/KCarino18/Fennsill");
        key.SetValue("HelpLink", "https://github.com/KCarino18/Fennsill/releases");
    }

    static void UnregisterUninstall()
    {
        try
        {
            Registry.LocalMachine.DeleteSubKeyTree(UninstallRegPath, throwOnMissingSubKey: false);
        }
        catch
        {
            /* optional */
        }
    }

    static int EstimateSizeKb(string dest)
    {
        try
        {
            long bytes = 0;
            foreach (var file in Directory.EnumerateFiles(dest, "*", SearchOption.AllDirectories))
            {
                try { bytes += new FileInfo(file).Length; }
                catch { /* skip */ }
            }
            return (int)Math.Max(1, bytes / 1024);
        }
        catch
        {
            return 1;
        }
    }

    static void EnsureRuntime(string dest, bool quiet)
    {
        var script = Path.Combine(dest, "connector", "runtime", "ensure_runtime.py");
        if (!File.Exists(script))
            throw new FileNotFoundException("ensure_runtime.py missing from install payload.", script);

        // Prefer an already-installed interpreter to run the bootstrap script.
        var launcher = FindBootstrapPython();
        if (launcher == null)
        {
            TryWingetPython();
            launcher = FindBootstrapPython();
        }
        if (launcher == null)
            throw new InvalidOperationException(
                "Python was not found and could not be bootstrapped. Install Python 3.12+ from python.org, then re-run FennSill Setup.");

        var psi = new ProcessStartInfo
        {
            FileName = launcher.Value.FileName,
            Arguments = string.IsNullOrEmpty(launcher.Value.PrefixArgs)
                ? $"\"{script}\""
                : $"{launcher.Value.PrefixArgs} \"{script}\"",
            WorkingDirectory = dest,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        psi.Environment["FENNSILL_ROOT"] = dest;
        psi.Environment["PLAYWRIGHT_BROWSERS_PATH"] = Path.Combine(dest, "connector", "browsers");
        psi.Environment["PYTHONUNBUFFERED"] = "1";
        psi.Environment["LOCALAPPDATA"] =
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);

        using var proc = Process.Start(psi)
            ?? throw new InvalidOperationException("Could not start ensure_runtime.py");
        var stdout = proc.StandardOutput.ReadToEnd();
        var stderr = proc.StandardError.ReadToEnd();
        proc.WaitForExit(30 * 60 * 1000);
        var combined = (stdout + "\n" + stderr).Trim();
        if (proc.ExitCode != 0)
        {
            var detail = string.IsNullOrWhiteSpace(combined) ? $"exit {proc.ExitCode}" : combined;
            if (detail.Length > 2500) detail = detail[^2500..];
            throw new InvalidOperationException(
                "FennSill could not finish installing Python / Playwright.\n\n" + detail);
        }

        var pyPath = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
            "Fennsill",
            "python_path.txt");
        if (!File.Exists(pyPath))
            throw new InvalidOperationException("ensure_runtime did not write python_path.txt.");

        var browsers = Path.Combine(dest, "connector", "browsers");
        var chrome = Directory.Exists(browsers)
            ? Directory.GetFiles(browsers, "chrome.exe", SearchOption.AllDirectories)
            : Array.Empty<string>();
        if (chrome.Length == 0)
            throw new InvalidOperationException(
                "Playwright Chromium was not installed under connector\\browsers.");
        // Playwright 1.49+ launches chrome-headless-shell for page render.
        var headless = Directory.GetFiles(
            browsers, "chrome-headless-shell.exe", SearchOption.AllDirectories);
        if (headless.Length == 0)
            throw new InvalidOperationException(
                "Playwright chrome-headless-shell.exe missing under connector\\browsers. "
                + "Re-run Setup with internet so browsers finish installing.");
    }

    static (string FileName, string PrefixArgs)? FindBootstrapPython()
    {
        foreach (var name in new[] { "py", "python" })
        {
            try
            {
                var args = name == "py" ? "-3 --version" : "--version";
                var psi = new ProcessStartInfo
                {
                    FileName = name,
                    Arguments = args,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                };
                using var p = Process.Start(psi);
                if (p == null) continue;
                p.WaitForExit(5000);
                if (p.ExitCode != 0) continue;
                return name == "py" ? (name, "-3") : (name, "");
            }
            catch
            {
                /* try next */
            }
        }

        var local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        foreach (var cand in new[]
                 {
                     Path.Combine(local, "Programs", "Python", "Python312", "python.exe"),
                     Path.Combine(local, "Programs", "Python", "Python313", "python.exe"),
                     Path.Combine(local, "Python", "pythoncore-3.12-64", "python.exe"),
                     Path.Combine(local, "Python", "pythoncore-3.14-64", "python.exe"),
                     Path.Combine(local, "Python", "bin", "python.exe"),
                 })
        {
            if (File.Exists(cand)) return (cand, "");
        }
        return null;
    }

    static void TryWingetPython()
    {
        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = "winget",
                Arguments =
                    "install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements --disable-interactivity",
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            };
            using var p = Process.Start(psi);
            p?.WaitForExit(15 * 60 * 1000);
        }
        catch
        {
            /* ensure_runtime will try again / fail clearly */
        }
    }

    static void WaitForAgentStatus(string dest, bool quiet)
    {
        var statusPath = Path.Combine(dest, "cloud_agent_status.json");
        // Also check LocalAppData FennsillApp — status is written there by cloud_agent.
        var appStatus = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "FennsillApp",
            "cloud_agent_status.json");
        for (var i = 0; i < 20; i++)
        {
            Thread.Sleep(1000);
            foreach (var path in new[] { appStatus, statusPath })
            {
                try
                {
                    if (!File.Exists(path)) continue;
                    var text = File.ReadAllText(path);
                    if (text.Contains("\"agent_crash\"", StringComparison.OrdinalIgnoreCase))
                        throw new InvalidOperationException(
                            "FennSill Agent started but crashed. Re-run Setup or check python_path.txt.\n\n" + text);
                    // Any status file means the agent process is writing — missing key is OK.
                    if (text.Contains("heartbeat", StringComparison.OrdinalIgnoreCase) ||
                        text.Contains("missing_device_token", StringComparison.OrdinalIgnoreCase) ||
                        text.Contains("\"ok\"", StringComparison.OrdinalIgnoreCase))
                        return;
                }
                catch (InvalidOperationException)
                {
                    throw;
                }
                catch
                {
                    /* retry */
                }
            }
        }
        if (!quiet)
        {
            MessageBox.Show(
                "FennSill Agent was installed but has not written status yet.\n" +
                "Plug in the panel, open Desk, and use Paste device key. If Cloud stays offline, re-run Setup.",
                "FennSill Setup",
                MessageBoxButtons.OK,
                MessageBoxIcon.Warning);
        }
    }

    static void InstallQuickStartPdf(string dest, string payload)
    {
        string? src = null;
        foreach (var cand in new[]
                 {
                     Path.Combine(payload, "FennSill-Quick-Start.pdf"),
                     Path.Combine(payload, "quickstart", "FennSill-Quick-Start.pdf"),
                     Path.Combine(AppContext.BaseDirectory, "payload", "FennSill-Quick-Start.pdf"),
                     Path.Combine(AppContext.BaseDirectory, "FennSill-Quick-Start.pdf"),
                 })
        {
            if (File.Exists(cand)) { src = cand; break; }
        }
        if (src == null) return;

        try
        {
            var appCopy = Path.Combine(dest, "FennSill Quick Start.pdf");
            File.Copy(src, appCopy, overwrite: true);
            var desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
            File.Copy(src, Path.Combine(desktop, "FennSill Quick Start.pdf"), overwrite: true);
        }
        catch
        {
            /* best effort */
        }
    }

    static string? FindPayloadRoot()
    {
        var baseDir = AppContext.BaseDirectory.TrimEnd('\\', '/');
        foreach (var root in new[]
                 {
                     Path.Combine(baseDir, "payload"),
                     baseDir,
                     Path.Combine(baseDir, "setup-payload"),
                 })
        {
            if (File.Exists(Path.Combine(root, "FennsillAgent.exe")) &&
                (File.Exists(Path.Combine(root, "Fennsill.exe")) ||
                 File.Exists(Path.Combine(root, "FennsillDesk.exe"))) &&
                (Directory.Exists(Path.Combine(root, "connector")) ||
                 File.Exists(Path.Combine(root, "connector", "runtime", "cloud_agent.py"))))
                return root;
        }
        return null;
    }

    static void EnsureCriticalFiles(string dest)
    {
        var push = Path.Combine(dest, "connector", "push_page.py");
        var agent = Path.Combine(dest, "connector", "runtime", "cloud_agent.py");
        var ensure = Path.Combine(dest, "connector", "runtime", "ensure_runtime.py");
        if (!File.Exists(push) || !File.Exists(agent) || !File.Exists(ensure))
            throw new InvalidOperationException(
                "Install payload is incomplete (missing push_page.py, cloud_agent.py, or ensure_runtime.py). Re-download FennsillSetup.");
    }

    static void CopyTree(string src, string dst)
    {
        foreach (var file in Directory.EnumerateFiles(src, "*", SearchOption.AllDirectories))
        {
            var rel = Path.GetRelativePath(src, file);
            var parts = rel.Split(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            if (parts.Any(p => p is "__pycache__" or "browsers" or "pages" or "inbox" or "setup-payload"))
                continue;
            var target = Path.Combine(dst, rel);
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(target)!);
                File.Copy(file, target, overwrite: true);
            }
            catch (IOException) { /* locked */ }
            catch (UnauthorizedAccessException) { /* AV */ }
        }
    }

    static void InstallOrUpdateService(string agentExe)
    {
        TryStopService();
        RunSc($"stop {ServiceName}");
        RunSc($"delete {ServiceName}");
        Thread.Sleep(800);
        var create = RunSc(
            $"create {ServiceName} binPath= \"{agentExe}\" start= auto DisplayName= \"{ServiceDisplayName}\"");
        if (create != 0)
            throw new InvalidOperationException(
                $"Could not create Windows service {ServiceName} (sc exit {create}).");
        RunSc($"description {ServiceName} \"Delivers cloud MCP pages to the FennSill USB e-ink panel.\"");
    }

    static void StartService()
    {
        var code = RunSc($"start {ServiceName}");
        if (code != 0)
        {
            try
            {
                using var sc = new ServiceController(ServiceName);
                sc.Start();
                sc.WaitForStatus(ServiceControllerStatus.Running, TimeSpan.FromSeconds(20));
            }
            catch (Exception ex)
            {
                throw new InvalidOperationException(
                    $"Service installed but failed to start (sc={code}). {ex.Message}", ex);
            }
        }
    }

    static void TryStopService()
    {
        try
        {
            using var sc = new ServiceController(ServiceName);
            if (sc.Status is ServiceControllerStatus.Running or ServiceControllerStatus.StartPending)
            {
                sc.Stop();
                sc.WaitForStatus(ServiceControllerStatus.Stopped, TimeSpan.FromSeconds(20));
            }
        }
        catch
        {
            /* not installed yet */
        }
    }

    static int RunSc(string args)
    {
        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = "sc.exe",
                Arguments = args,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            };
            using var p = Process.Start(psi);
            if (p == null) return -1;
            p.WaitForExit(30000);
            return p.ExitCode;
        }
        catch
        {
            return -1;
        }
    }

    static void TryDesktopShortcut(string exePath, string workDir)
    {
        TryWriteShortcut(
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "FennSill.lnk"),
            exePath,
            workDir);
    }

    static void TryStartMenuShortcut(string exePath, string workDir)
    {
        try
        {
            var dir = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.CommonStartMenu),
                "Programs",
                "FennSill");
            Directory.CreateDirectory(dir);
            TryWriteShortcut(Path.Combine(dir, "FennSill.lnk"), exePath, workDir);
        }
        catch
        {
            /* optional */
        }
    }

    static void TryWriteShortcut(string lnkPath, string exePath, string workDir)
    {
        try
        {
            if (!File.Exists(exePath)) return;
            var t = Type.GetTypeFromProgID("WScript.Shell");
            if (t == null) return;
            dynamic shell = Activator.CreateInstance(t)!;
            var sc = shell.CreateShortcut(lnkPath);
            sc.TargetPath = exePath;
            sc.WorkingDirectory = workDir;
            sc.Description = "FennSill Desk";
            sc.Save();
        }
        catch
        {
            /* optional */
        }
    }

    static void TryDeleteShortcut(string lnkPath)
    {
        try
        {
            if (File.Exists(lnkPath)) File.Delete(lnkPath);
        }
        catch { /* optional */ }
    }

    static string? FirstExisting(string dir, params string[] names)
    {
        foreach (var name in names)
        {
            var path = Path.Combine(dir, name);
            if (File.Exists(path)) return path;
        }
        return null;
    }
}
