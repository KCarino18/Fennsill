using System.Diagnostics;
using System.ServiceProcess;

namespace FennsillSetup;

static class Program
{
    const string ServiceName = "FennsillAgent";
    const string ServiceDisplayName = "Fennsill Agent";

    [STAThread]
    static void Main()
    {
        Application.SetHighDpiMode(HighDpiMode.SystemAware);
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);

        var result = MessageBox.Show(
            "Install Fennsill on this PC?\n\n" +
            "• Desk app (Device ID / Paste device key)\n" +
            "• Fennsill Agent Windows service (USB cloud push — stays on when Desk is closed)\n\n" +
            "Admin permission is required to install the service.",
            "Fennsill Setup",
            MessageBoxButtons.OKCancel,
            MessageBoxIcon.Information);
        if (result != DialogResult.OK) return;

        try
        {
            Install();
        }
        catch (Exception ex)
        {
            MessageBox.Show(ex.ToString(), "Fennsill Setup failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    static void Install()
    {
        var payload = FindPayloadRoot();
        if (payload == null)
        {
            MessageBox.Show(
                "Install payload was not found next to this Setup.\n\n" +
                "Use the official FennsillSetup.exe release (it bundles Desk + Agent + scripts).",
                "Fennsill Setup",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            return;
        }

        var userLocal = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        var dest = Path.Combine(userLocal, "FennsillApp");
        Directory.CreateDirectory(dest);

        // Stop existing agent so binaries under FennsillApp can be replaced.
        TryStopService();
        RunSc($"stop {ServiceName}");
        Thread.Sleep(500);

        CopyTree(payload, dest);
        // Prefer named release binaries if present in payload root.
        foreach (var name in new[] { "Fennsill.exe", "FennsillDesk.exe", "FennsillAgent.exe" })
        {
            var src = Path.Combine(payload, name);
            if (File.Exists(src))
                File.Copy(src, Path.Combine(dest, name == "FennsillDesk.exe" ? "Fennsill.exe" : name), overwrite: true);
        }

        // If payload nested connector under payload\connector, CopyTree already handled it.
        EnsureCriticalFiles(dest);

        var programData = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
            "Fennsill");
        Directory.CreateDirectory(programData);
        File.WriteAllText(
            Path.Combine(programData, "user_localappdata.txt"),
            userLocal + Environment.NewLine);

        var agentExe = Path.Combine(dest, "FennsillAgent.exe");
        if (!File.Exists(agentExe))
            throw new FileNotFoundException("FennsillAgent.exe missing after install.", agentExe);

        InstallOrUpdateService(agentExe);
        StartService();

        var deskExe = FirstExisting(dest, "Fennsill.exe", "FennsillDesk.exe")
            ?? throw new FileNotFoundException("Fennsill.exe missing after install.");
        TryDesktopShortcut(deskExe, dest);

        MessageBox.Show(
            "Fennsill is installed.\n\n" +
            $"Folder: {dest}\n" +
            "Service: Fennsill Agent (Automatic)\n\n" +
            "Next: open Desk → copy Device ID → link on the website → Paste device key.\n" +
            "ChatGPT/Claude use the cloud MCP URL + Bearer header.",
            "Fennsill Setup",
            MessageBoxButtons.OK,
            MessageBoxIcon.Information);

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
            // Don't overwrite a running service binary mid-copy awkwardly — stop service first.
            var target = Path.Combine(dst, rel);
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(target)!);
                File.Copy(file, target, overwrite: true);
            }
            catch (IOException)
            {
                /* locked — service binary may need stop first */
            }
            catch (UnauthorizedAccessException)
            {
                /* AV */
            }
        }
    }

    static void InstallOrUpdateService(string agentExe)
    {
        TryStopService();
        // sc.exe is reliable across Windows SKUs.
        RunSc($"stop {ServiceName}");
        RunSc($"delete {ServiceName}");
        // Brief pause so SCM releases the name.
        Thread.Sleep(800);
        var create = RunSc(
            $"create {ServiceName} binPath= \"{agentExe}\" start= auto DisplayName= \"{ServiceDisplayName}\"");
        if (create != 0)
            throw new InvalidOperationException(
                $"Could not create Windows service {ServiceName} (sc exit {create}).");
        RunSc($"description {ServiceName} \"Delivers cloud MCP pages to the Fennsill USB e-ink panel.\"");
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
        try
        {
            var desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
            var lnk = Path.Combine(desktop, "Fennsill.lnk");
            var t = Type.GetTypeFromProgID("WScript.Shell");
            if (t == null) return;
            dynamic shell = Activator.CreateInstance(t)!;
            var sc = shell.CreateShortcut(lnk);
            sc.TargetPath = exePath;
            sc.WorkingDirectory = workDir;
            sc.Description = "Fennsill Desk";
            sc.Save();
        }
        catch
        {
            /* optional */
        }
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
