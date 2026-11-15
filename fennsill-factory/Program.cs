namespace FennsillFactory;

static class Program
{
    [STAThread]
    static void Main()
    {
        Application.SetHighDpiMode(HighDpiMode.SystemAware);
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);

        try
        {
            FactoryInstall.EnsureInstalled();
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                ex.Message,
                "Fennsill Factory Setup",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            return;
        }

        Application.Run(new MainForm());
    }
}
