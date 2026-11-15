namespace FennsillFactory;

/// <summary>
/// First-run install into LocalAppData\FennsillApp\factory (not Fennsill\),
/// because some PCs block classic script names under %LOCALAPPDATA%\Fennsill\.
/// </summary>
static class FactoryInstall
{
    public static string InstallRoot =>
        Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "FennsillApp");

    public static string FactoryDir => Path.Combine(InstallRoot, "factory");

    public static string EnsureInstalled()
    {
        var dest = FactoryDir;
        SafeMkDir(dest);

        var provision = Path.Combine(dest, "provision.py");
        var ports = Path.Combine(dest, "firmware", "panel_ports.py");
        var needCopy = !File.Exists(provision) || !File.Exists(ports);

        if (needCopy)
        {
            var payload = FindBundledPayload();
            if (payload == null)
            {
                throw new DirectoryNotFoundException(
                    "Factory files are missing from this download.\n\n" +
                    "Re-download FennsillFactory.exe from the latest GitHub release.");
            }

            CopyTree(payload.FactorySrc, dest);
            CopyTree(payload.FirmwareSrc, Path.Combine(dest, "firmware"));
        }

        if (!File.Exists(Path.Combine(dest, "provision.py"))
            || !File.Exists(Path.Combine(dest, "firmware", "panel_ports.py")))
        {
            throw new IOException(
                "Could not install factory scripts (Windows blocked some files).\n\n" +
                "Allow FennsillFactory.exe in Controlled Folder Access / antivirus, then try again.");
        }

        try
        {
            File.Copy(Application.ExecutablePath, Path.Combine(dest, "FennsillFactory.exe"), overwrite: true);
        }
        catch { /* locked */ }

        Environment.SetEnvironmentVariable("FENNSILL_ROOT", dest);
        TryDesktopShortcut(Path.Combine(dest, "FennsillFactory.exe"), dest);
        return dest;
    }

    sealed record Payload(string FactorySrc, string FirmwareSrc);

    static Payload? FindBundledPayload()
    {
        var baseDir = AppContext.BaseDirectory.TrimEnd('\\', '/');
        var candidates = new[]
        {
            Path.Combine(baseDir, "payload"),
            baseDir,
            Path.GetFullPath(Path.Combine(baseDir, "..")),
        };

        foreach (var root in candidates)
        {
            var factory = root;
            if (File.Exists(Path.Combine(root, "factory", "provision.py")))
                factory = Path.Combine(root, "factory");
            if (!File.Exists(Path.Combine(factory, "provision.py")))
                continue;

            var fw = Path.Combine(factory, "firmware");
            if (!File.Exists(Path.Combine(fw, "panel_ports.py")))
                fw = Path.Combine(root, "firmware");
            if (!File.Exists(Path.Combine(fw, "panel_ports.py")))
                fw = Path.Combine(Path.GetDirectoryName(factory) ?? root, "firmware");
            if (!File.Exists(Path.Combine(fw, "panel_ports.py")))
                continue;

            return new Payload(factory, fw);
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
            var name = Path.GetFileName(file);
            if (name.Equals("master.key", StringComparison.OrdinalIgnoreCase)) continue;
            if (name.EndsWith(".csv", StringComparison.OrdinalIgnoreCase) &&
                file.Contains($"{Path.DirectorySeparatorChar}ledger{Path.DirectorySeparatorChar}", StringComparison.OrdinalIgnoreCase))
                continue;

            var rel = Path.GetRelativePath(src, file);
            if (rel.Split(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
                    .Any(p => p.Equals("__pycache__", StringComparison.OrdinalIgnoreCase)))
                continue;

            var target = Path.Combine(dst, rel);
            try
            {
                SafeMkDir(Path.GetDirectoryName(target)!);
                File.Copy(file, target, overwrite: true);
            }
            catch (UnauthorizedAccessException) { /* AV block */ }
            catch (IOException) { /* locked */ }
        }
    }

    static void TryDesktopShortcut(string exePath, string workDir)
    {
        try
        {
            if (!File.Exists(exePath)) return;
            var desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
            var lnk = Path.Combine(desktop, "Fennsill Factory.lnk");
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
