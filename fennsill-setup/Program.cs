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

        var agentExe = Path.Combine(dest, "FennsillAgent.exe");
        if (!File.Exists(agentExe))
            throw new FileNotFoundException("FennsillAgent.exe missing after install.", agentExe);

        InstallOrUpdateService(agentExe);
        StartService();

        var deskExe = FirstExisting(dest, "Fennsill.exe", "FennsillDesk.exe")
            ?? throw new FileNotFoundException("Fennsill.exe missing after install.");
        TryDesktopShortcut(deskExe, dest);
        TryStartMenuShortcut(deskExe, dest);
        // Remove legacy shortcut name from older installs.
        TryDeleteShortcut(
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "Fennsill.lnk"));
        RegisterUninstall(dest, deskExe, setupDest);

        if (!quiet)
        {
            MessageBox.Show(
                "FennSill is installed.\n\n" +
                $"Folder: {dest}\n" +
                "Service: FennSill Agent (Automatic)\n" +
                "Listed under Settings → Apps → Installed apps\n\n" +
                "Next: open Desk → copy Device ID → link on the website → Paste device key.\n" +
                "ChatGPT/Claude use the cloud MCP URL + Bearer header.",
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
        if (!File.Exists(push) || !File.Exists(agent))
            throw new InvalidOperationException(
                "Install payload is incomplete (missing push_page.py or cloud_agent.py). Re-download FennsillSetup.");
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
