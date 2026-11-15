namespace FennsillFactory;

/// <summary>
/// First-run install: copy bundled factory + firmware into LocalAppData so a
/// lone FennsillFactory.exe download works without C:\factory or a zip layout.
/// </summary>
static class FactoryInstall
{
    public static string InstallRoot =>
        Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Fennsill");

    public static string FactoryDir => Path.Combine(InstallRoot, "factory");

    public static string EnsureInstalled()
    {
        var dest = FactoryDir;
        Directory.CreateDirectory(dest);

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
                    "Use Fennsill-Setup.zip / Fennsill Factory from the latest release, " +
                    "or rebuild with bundled payload.");
            }

            CopyTree(payload.FactorySrc, dest);
            var fwDest = Path.Combine(dest, "firmware");
            CopyTree(payload.FirmwareSrc, fwDest);
        }

        // Always refresh the installed exe next to the scripts.
        try
        {
            var exeDest = Path.Combine(dest, "FennsillFactory.exe");
            File.Copy(Application.ExecutablePath, exeDest, overwrite: true);
        }
        catch
        {
            /* file locked / in use — ignore */
        }

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

    static void CopyTree(string src, string dst)
    {
        Directory.CreateDirectory(dst);
        foreach (var file in Directory.EnumerateFiles(src, "*", SearchOption.AllDirectories))
        {
            var name = Path.GetFileName(file);
            if (name.Equals("master.key", StringComparison.OrdinalIgnoreCase)) continue;
            if (name.EndsWith(".csv", StringComparison.OrdinalIgnoreCase) &&
                file.Contains($"{Path.DirectorySeparatorChar}ledger{Path.DirectorySeparatorChar}", StringComparison.OrdinalIgnoreCase))
                continue;
            if (name.Equals("__pycache__", StringComparison.OrdinalIgnoreCase)) continue;

            var rel = Path.GetRelativePath(src, file);
            if (rel.Split(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
                    .Any(p => p.Equals("__pycache__", StringComparison.OrdinalIgnoreCase)))
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
            var lnk = Path.Combine(desktop, "Fennsill Factory.lnk");
            var t = Type.GetTypeFromProgID("WScript.Shell");
            if (t == null) return;
            dynamic shell = Activator.CreateInstance(t)!;
            var sc = shell.CreateShortcut(lnk);
            sc.TargetPath = exePath;
            sc.WorkingDirectory = workDir;
            sc.Save();
        }
        catch
        {
            /* optional */
        }
    }
}
