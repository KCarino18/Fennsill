namespace FennsillDesk;

/// <summary>
/// First-run install into LocalAppData so a downloaded Fennsill.exe works alone.
/// Uses FennsillApp\ (not Fennsill\) because some PCs block classic script names
/// under %LOCALAPPDATA%\Fennsill\.
/// </summary>
static class DeskInstall
{
    public static string InstallRoot =>
        Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "FennsillApp");

    public static string EnsureInstalled()
    {
        var dest = InstallRoot;
        SafeMkDir(dest);
        SafeMkDir(Path.Combine(dest, "connector"));
        SafeMkDir(Path.Combine(dest, "connector", "runtime"));
        SafeMkDir(Path.Combine(dest, "connector", "pages"));
        SafeMkDir(Path.Combine(dest, "connector", "inbox"));
        SafeMkDir(Path.Combine(dest, "firmware"));
        SafeMkDir(Path.Combine(dest, "templates"));

        // Always refresh bundled scripts on launch so upgrades replace cloud_agent.py etc.
        // (Previously we only copied once — buyers kept an old agent and got Cloudflare 1010.)
        var payload = FindBundledPayload();
        if (payload != null)
        {
            if (Directory.Exists(payload.Connector))
                CopyTree(payload.Connector, Path.Combine(dest, "connector"));
            if (Directory.Exists(payload.Firmware))
                CopyTree(payload.Firmware, Path.Combine(dest, "firmware"));
            if (Directory.Exists(payload.Templates))
                CopyTree(payload.Templates, Path.Combine(dest, "templates"));
        }

        try
        {
            File.WriteAllText(
                Path.Combine(dest, "desk_payload_version.txt"),
                Application.ProductVersion + " " + DateTime.UtcNow.ToString("o") + Environment.NewLine);
        }
        catch { /* optional */ }

        try
        {
            File.Copy(Application.ExecutablePath, Path.Combine(dest, "FennsillDesk.exe"), overwrite: true);
        }
        catch { /* locked */ }

        Environment.SetEnvironmentVariable("FENNSILL_ROOT", dest);
        TryDesktopShortcut(Path.Combine(dest, "FennsillDesk.exe"), dest);
        return dest;
    }

    sealed record Payload(string Connector, string Firmware, string Templates);

    static Payload? FindBundledPayload()
    {
        var baseDir = AppContext.BaseDirectory.TrimEnd('\\', '/');
        foreach (var root in new[] { Path.Combine(baseDir, "payload"), baseDir })
        {
            var connector = Path.Combine(root, "connector");
            var firmware = Path.Combine(root, "firmware");
            var templates = Path.Combine(root, "templates");
            var hasIdentity = File.Exists(Path.Combine(connector, "identity_status.py"))
                || File.Exists(Path.Combine(connector, "runtime", "panel_status.py"))
                || File.Exists(Path.Combine(connector, "runtime", "bind_device.py"));
            var hasPorts = File.Exists(Path.Combine(firmware, "panel_ports.py"));
            if (hasIdentity && hasPorts)
                return new Payload(connector, firmware, templates);
        }
        return null;
    }

    static void SafeMkDir(string path)
    {
        try { Directory.CreateDirectory(path); }
        catch { /* ignore */ }
    }

    static void CopyTree(string src, string dst)
    {
        if (!Directory.Exists(src)) return;
        SafeMkDir(dst);
        foreach (var file in Directory.EnumerateFiles(src, "*", SearchOption.AllDirectories))
        {
            var rel = Path.GetRelativePath(src, file);
            var parts = rel.Split(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            if (parts.Any(p => p is "__pycache__" or "browsers" or "pages" or "inbox"))
                continue;
            // cloud_agent.py is owned by the Fennsill Agent Windows service / Setup.
            // Overwriting it from an older Desk payload caused post-reboot agent_crash.
            if (parts.Any(p => string.Equals(p, "cloud_agent.py", StringComparison.OrdinalIgnoreCase)))
                continue;
            var target = Path.Combine(dst, rel);
            try
            {
                SafeMkDir(Path.GetDirectoryName(target)!);
                File.Copy(file, target, overwrite: true);
            }
            catch (UnauthorizedAccessException)
            {
                /* Controlled Folder Access / AV — skip blocked name */
            }
            catch (IOException)
            {
                /* locked */
            }
        }
    }

    static void TryDesktopShortcut(string exePath, string workDir)
    {
        try
        {
            if (!File.Exists(exePath)) return;
            var desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
            var lnk = Path.Combine(desktop, "Fennsill.lnk");
            var t = Type.GetTypeFromProgID("WScript.Shell");
            if (t == null) return;
            dynamic shell = Activator.CreateInstance(t)!;
            var sc = shell.CreateShortcut(lnk);
            sc.TargetPath = exePath;
            sc.WorkingDirectory = workDir;
            sc.Save();
        }
        catch { /* optional */ }
    }
}
