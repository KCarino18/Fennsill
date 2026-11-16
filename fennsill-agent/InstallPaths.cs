namespace FennsillAgent;

/// <summary>
/// Setup writes the installing user's LocalAppData so the LocalSystem service
/// still reads tokens/status under that user's %LOCALAPPDATA%\FennsillApp.
/// </summary>
static class InstallPaths
{
    public const string ServiceName = "FennsillAgent";
    public const string ServiceDisplayName = "FennSill Agent";

    public static string ProgramDataDir =>
        Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
            "Fennsill");

    public static string UserLocalAppDataFile =>
        Path.Combine(ProgramDataDir, "user_localappdata.txt");

    public static string ResolveUserLocalAppData()
    {
        try
        {
            if (File.Exists(UserLocalAppDataFile))
            {
                var line = File.ReadAllText(UserLocalAppDataFile)
                    .Trim()
                    .Split('\n', '\r')[0]
                    .Trim()
                    .Trim('"');
                if (!string.IsNullOrWhiteSpace(line) && Directory.Exists(line))
                    return line;
            }
        }
        catch
        {
            /* fall through */
        }

        var local = Environment.GetEnvironmentVariable("LOCALAPPDATA");
        if (!string.IsNullOrWhiteSpace(local))
            return local;

        return Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
    }

    public static string ResolveInstallRoot()
    {
        var root = Path.Combine(ResolveUserLocalAppData(), "FennsillApp");
        Directory.CreateDirectory(root);
        return root;
    }

    public static void ApplyProcessEnvironment()
    {
        var userLocal = ResolveUserLocalAppData();
        var root = ResolveInstallRoot();
        Environment.SetEnvironmentVariable("LOCALAPPDATA", userLocal);
        Environment.SetEnvironmentVariable("FENNSILL_ROOT", root);
        Environment.SetEnvironmentVariable(
            "PLAYWRIGHT_BROWSERS_PATH",
            Path.Combine(root, "connector", "browsers"));
        Environment.SetEnvironmentVariable("PYTHONUNBUFFERED", "1");
        var runtime = Path.Combine(root, "connector", "runtime");
        Environment.SetEnvironmentVariable("PYTHONPATH", runtime);
    }
}
