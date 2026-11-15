namespace FennsillDesk;

/// <summary>
/// First-run install into LocalAppData so a downloaded Fennsill.exe works alone
/// (no unzip + Setup required for the desk payload).
/// </summary>
static class DeskInstall
{
    public static string InstallRoot =>
        Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Fennsill");

    public static string EnsureInstalled()
    {
        var dest = InstallRoot;
        Directory.CreateDirectory(dest);
        Directory.CreateDirectory(Path.Combine(dest, "connector"));
        Directory.CreateDirectory(Path.Combine(dest, "connector", "runtime"));
        Directory.CreateDirectory(Path.Combine(dest, "connector", "pages"));
        Directory.CreateDirectory(Path.Combine(dest, "connector", "inbox"));
        Directory.CreateDirectory(Path.Combine(dest, "firmware"));
        Directory.CreateDirectory(Path.Combine(dest, "templates"));

        var identity = Path.Combine(dest, "connector", "identity_status.py");
        var ports = Path.Combine(dest, "firmware", "panel_ports.py");
        var needCopy = !File.Exists(identity) || !File.Exists(ports);

        if (needCopy)
        {
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
        }

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
                || File.Exists(Path.Combine(connector, "runtime", "panel_status.py"));
            var hasPorts = File.Exists(Path.Combine(firmware, "panel_ports.py"));
            if (hasIdentity && hasPorts)
                return new Payload(connector, firmware, templates);
        }
        return null;
    }

    static void CopyTree(string src, string dst)
    {
        if (!Directory.Exists(src)) return;
        Directory.CreateDirectory(dst);
        foreach (var file in Directory.EnumerateFiles(src, "*", SearchOption.AllDirectories))
        {
            var rel = Path.GetRelativePath(src, file);
            if (rel.Split(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
                    .Any(p => p is "__pycache__" or "browsers" or "pages" or "inbox"))
                continue;
            var target = Path.Combine(dst, rel);
            Directory.CreateDirectory(Path.GetDirectoryName(target)!);
            File.Copy(file, target, overwrite: true);
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
