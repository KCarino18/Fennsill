namespace FennsillDesk;

static class Program
{
    [STAThread]
    static void Main()
    {
        // One Fennsill window only — reopening used to stack dozens of python
        // workers and make COM3 look busy to ChatGPT.
        using var mutex = new Mutex(true, @"Local\FennsillDeskSingleInstance", out var created);
        if (!created)
        {
            MessageBox.Show(
                "FennSill is already running.",
                "FennSill",
                MessageBoxButtons.OK,
                MessageBoxIcon.Information);
            return;
        }

        Application.SetHighDpiMode(HighDpiMode.SystemAware);
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);

        try
        {
            DeskInstall.EnsureInstalled();
        }
        catch
        {
            // Still open the app — FindProjectRoot may use the project folder.
        }

        // Installed builds: pull the latest GitHub release Setup if newer.
        // Project/dev builds skip (see AutoUpdate.ShouldSkip).
        var updating = false;
        try
        {
            updating = AutoUpdate.TryApplyAsync().GetAwaiter().GetResult();
        }
        catch
        {
            // Continue with the current build.
        }
        if (updating)
        {
            GC.KeepAlive(mutex);
            return;
        }

        Application.Run(new MainForm());
        GC.KeepAlive(mutex);
    }
}
