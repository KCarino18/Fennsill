using System.Diagnostics;

namespace FennsillSetup;

static class Program
{
    [STAThread]
    static void Main()
    {
        Application.SetHighDpiMode(HighDpiMode.SystemAware);
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);

        var dir = AppContext.BaseDirectory.TrimEnd('\\', '/');
        var exe = FirstExisting(dir, "Fennsill.exe", "FennsillDesk.exe");
        var ps1 = FirstExisting(dir, "Install-Fennsill.ps1", "Install-FennsillDesk.ps1");

        if (exe == null)
        {
            MessageBox.Show(
                "Fennsill.exe was not found next to this installer.\n\nUnzip the full Fennsill folder (or copy the USB folder), then run FennsillSetup.exe again.",
                "Fennsill Setup",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            return;
        }

        if (ps1 == null)
        {
            MessageBox.Show(
                "Install-Fennsill.ps1 was not found next to this installer.\n\nUse the full setup zip (not only FennsillSetup.exe).",
                "Fennsill Setup",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            return;
        }

        var result = MessageBox.Show(
            "Install Fennsill on this PC?\n\nIt will copy files, set up Claude / ChatGPT / Cursor, and open Fennsill.",
            "Fennsill Setup",
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
                MessageBox.Show("Could not start PowerShell install.", "Fennsill Setup", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }
            proc.WaitForExit(120_000);
            if (proc.ExitCode != 0)
            {
                MessageBox.Show(
                    "Setup reported an error. You can still try opening Fennsill.exe from this folder.",
                    "Fennsill Setup",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Warning);
            }
        }
        catch (Exception ex)
        {
            MessageBox.Show(ex.Message, "Fennsill Setup", MessageBoxButtons.OK, MessageBoxIcon.Error);
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
