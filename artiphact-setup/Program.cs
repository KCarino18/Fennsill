using System.Diagnostics;

namespace ArtiphactSetup;

static class Program
{
    [STAThread]
    static void Main()
    {
        Application.SetHighDpiMode(HighDpiMode.SystemAware);
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);

        var dir = AppContext.BaseDirectory.TrimEnd('\\', '/');
        var exe = Path.Combine(dir, "Artiphact.exe");
        var ps1 = Path.Combine(dir, "Install-Artiphact.ps1");

        if (!File.Exists(exe))
        {
            MessageBox.Show(
                "Artiphact.exe was not found next to this installer.\n\nUnzip the full Artiphact folder (or copy the USB folder), then run ArtiphactSetup.exe again.",
                "Artiphact Setup",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            return;
        }

        if (!File.Exists(ps1))
        {
            MessageBox.Show(
                "Install-Artiphact.ps1 was not found next to this installer.",
                "Artiphact Setup",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            return;
        }

        var result = MessageBox.Show(
            "Install Artiphact on this PC?\n\nIt will copy files, set up Claude / ChatGPT / Cursor, and open Artiphact.",
            "Artiphact Setup",
            MessageBoxButtons.OKCancel,
            MessageBoxIcon.Information);
        if (result != DialogResult.OK) return;

        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = "powershell",
                Arguments = $"-NoProfile -ExecutionPolicy Bypass -File \"{ps1}\"",
                WorkingDirectory = dir,
                UseShellExecute = false,
                CreateNoWindow = false,
            };
            using var proc = Process.Start(psi);
            if (proc == null)
            {
                MessageBox.Show("Could not start PowerShell install.", "Artiphact Setup", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }
            proc.WaitForExit(120_000);
            if (proc.ExitCode != 0)
            {
                MessageBox.Show(
                    "Setup reported an error. You can still try opening Artiphact.exe from this folder.",
                    "Artiphact Setup",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Warning);
            }
        }
        catch (Exception ex)
        {
            MessageBox.Show(ex.Message, "Artiphact Setup", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}
