using System.Diagnostics;
using System.Net.Http.Headers;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace FennsillDesk;

/// <summary>
/// On launch, check GitHub Releases for a newer FennSill Setup and apply it
/// (silent elevated install). Dev/project builds are skipped.
/// </summary>
static class AutoUpdate
{
    const string Owner = "KCarino18";
    const string Repo = "Fennsill";
    const string ApiLatest = $"https://api.github.com/repos/{Owner}/{Repo}/releases/latest";

    /// <returns>True if an update installer was launched and Desk should exit.</returns>
    public static async Task<bool> TryApplyAsync(Action<string>? status = null)
    {
        if (ShouldSkip())
            return false;

        try
        {
            status?.Invoke("Checking for updates…");
            using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(25) };
            client.DefaultRequestHeaders.UserAgent.ParseAdd("FennsillDesk-AutoUpdate");
            client.DefaultRequestHeaders.Accept.Add(
                new MediaTypeWithQualityHeaderValue("application/vnd.github+json"));

            using var resp = await client.GetAsync(ApiLatest);
            if (!resp.IsSuccessStatusCode)
                return false;

            await using var stream = await resp.Content.ReadAsStreamAsync();
            using var doc = await JsonDocument.ParseAsync(stream);
            var root = doc.RootElement;
            var tag = root.TryGetProperty("tag_name", out var tagEl) ? tagEl.GetString() ?? "" : "";
            var remote = ParseVersion(tag);
            var local = ParseVersion(Application.ProductVersion);
            if (remote is null || local is null || remote <= local)
                return false;

            string? setupUrl = null;
            if (root.TryGetProperty("assets", out var assets) && assets.ValueKind == JsonValueKind.Array)
            {
                foreach (var asset in assets.EnumerateArray())
                {
                    var name = asset.TryGetProperty("name", out var n) ? n.GetString() ?? "" : "";
                    if (!name.Equals("FennsillSetup.exe", StringComparison.OrdinalIgnoreCase))
                        continue;
                    setupUrl = asset.TryGetProperty("browser_download_url", out var u)
                        ? u.GetString()
                        : null;
                    break;
                }
            }
            if (string.IsNullOrWhiteSpace(setupUrl))
                return false;

            status?.Invoke($"Updating to {tag}…");
            var dir = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "FennsillApp",
                "updates");
            Directory.CreateDirectory(dir);
            var dest = Path.Combine(dir, $"FennsillSetup-{tag.TrimStart('v', 'V')}.exe");

            await using (var http = await client.GetStreamAsync(setupUrl))
            await using (var file = File.Create(dest))
                await http.CopyToAsync(file);

            // Elevated silent Setup refreshes Desk, Agent service, and payload.
            var psi = new ProcessStartInfo
            {
                FileName = dest,
                Arguments = "/S",
                UseShellExecute = true,
                Verb = "runas",
            };
            Process.Start(psi);
            status?.Invoke("Installer started — FennSill will reopen after update.");
            return true;
        }
        catch
        {
            // Offline / declined UAC / API blip — open the current app.
            return false;
        }
    }

    static bool ShouldSkip()
    {
        if (string.Equals(
                Environment.GetEnvironmentVariable("FENNSILL_SKIP_UPDATE"),
                "1",
                StringComparison.OrdinalIgnoreCase))
            return true;
        if (Debugger.IsAttached)
            return true;

        var baseDir = AppContext.BaseDirectory;
        if (baseDir.Contains("This Is A Test For The Tablet", StringComparison.OrdinalIgnoreCase))
            return true;
        if (baseDir.Contains($"{Path.DirectorySeparatorChar}bin{Path.DirectorySeparatorChar}", StringComparison.OrdinalIgnoreCase)
            && baseDir.Contains("fennsill-desk", StringComparison.OrdinalIgnoreCase))
            return true;

        return false;
    }

    static Version? ParseVersion(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw)) return null;
        var m = Regex.Match(raw.Trim(), @"(\d+\.\d+\.\d+)");
        if (!m.Success) return null;
        return Version.TryParse(m.Groups[1].Value, out var v) ? v : null;
    }
}
