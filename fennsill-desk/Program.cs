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

        Application.Run(new MainForm());
        GC.KeepAlive(mutex);
    }
}
