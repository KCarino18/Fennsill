using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace FennsillDesk;

/// <summary>
/// Shared local display queue (JSON + preview PNGs) owned with the Agent.
/// </summary>
static class DisplayQueue
{
    public static string QueuePath(string root) =>
        Path.Combine(root, "connector", "display_queue.json");

    public static string LockPath(string root) => QueuePath(root) + ".lock";

    public sealed class Item
    {
        public string Id { get; set; } = "";
        public string JobId { get; set; } = "";
        public string Title { get; set; } = "";
        public int HoldSec { get; set; }
        public string PreviewPath { get; set; } = "";
        public string FramePath { get; set; } = "";
        public string Status { get; set; } = "waiting";
        public string CreatedAt { get; set; } = "";
        public double? HeldUntil { get; set; }
    }

    public static List<Item> Load(string root)
    {
        var path = QueuePath(root);
        if (!File.Exists(path)) return new List<Item>();
        try
        {
            using var _ = AcquireSidecarLock(root);
            var text = File.ReadAllText(path, Encoding.UTF8);
            if (string.IsNullOrWhiteSpace(text)) return new List<Item>();
            using var doc = JsonDocument.Parse(text);
            if (!doc.RootElement.TryGetProperty("items", out var items) ||
                items.ValueKind != JsonValueKind.Array)
                return new List<Item>();
            var list = new List<Item>();
            foreach (var el in items.EnumerateArray())
            {
                var id = el.TryGetProperty("id", out var idEl) ? idEl.GetString() ?? "" : "";
                if (string.IsNullOrWhiteSpace(id)) continue;
                double? held = null;
                if (el.TryGetProperty("held_until", out var hu) &&
                    hu.ValueKind == JsonValueKind.Number &&
                    hu.TryGetDouble(out var hv))
                    held = hv;
                list.Add(new Item
                {
                    Id = id,
                    JobId = el.TryGetProperty("job_id", out var j) ? j.GetString() ?? "" : "",
                    Title = el.TryGetProperty("title", out var t) ? t.GetString() ?? "" : "",
                    HoldSec = el.TryGetProperty("hold_sec", out var h) && h.TryGetInt32(out var hs) ? hs : 0,
                    PreviewPath = el.TryGetProperty("preview_path", out var p) ? p.GetString() ?? "" : "",
                    FramePath = el.TryGetProperty("frame_path", out var f) ? f.GetString() ?? "" : "",
                    Status = el.TryGetProperty("status", out var s) ? s.GetString() ?? "waiting" : "waiting",
                    CreatedAt = el.TryGetProperty("created_at", out var c) ? c.GetString() ?? "" : "",
                    HeldUntil = held,
                });
            }
            return list;
        }
        catch
        {
            return new List<Item>();
        }
    }

    /// <summary>Same sidecar lock file the Agent uses (display_queue.json.lock).</summary>
    static FileStream AcquireSidecarLock(string root)
    {
        var lockPath = LockPath(root);
        Directory.CreateDirectory(Path.GetDirectoryName(lockPath)!);
        var deadline = DateTime.UtcNow.AddSeconds(8);
        while (true)
        {
            try
            {
                return new FileStream(
                    lockPath,
                    FileMode.OpenOrCreate,
                    FileAccess.ReadWrite,
                    FileShare.None);
            }
            catch (IOException)
            {
                if (DateTime.UtcNow >= deadline) throw;
                Thread.Sleep(50);
            }
        }
    }

    static void Save(string root, List<Item> items)
    {
        var path = QueuePath(root);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var arr = new JsonArray();
        foreach (var it in items)
        {
            var obj = new JsonObject
            {
                ["id"] = it.Id,
                ["job_id"] = it.JobId,
                ["title"] = it.Title,
                ["hold_sec"] = it.HoldSec,
                ["preview_path"] = it.PreviewPath,
                ["frame_path"] = it.FramePath,
                ["status"] = it.Status,
                ["created_at"] = it.CreatedAt,
            };
            if (it.HeldUntil is double hu)
                obj["held_until"] = hu;
            else
                obj["held_until"] = null;
            arr.Add(obj);
        }
        var rootObj = new JsonObject
        {
            ["version"] = 1,
            ["items"] = arr,
            ["updated_at"] = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ"),
        };
        var json = rootObj.ToJsonString(new JsonSerializerOptions { WriteIndented = true });
        var tmp = path + ".tmp";
        using (AcquireSidecarLock(root))
        {
            File.WriteAllText(tmp, json, Encoding.UTF8);
            File.Move(tmp, path, overwrite: true);
        }
    }

    public static bool Move(string root, string itemId, int direction)
    {
        var items = Load(root);
        var idx = items.FindIndex(i => i.Id == itemId);
        if (idx < 0) return false;
        if (string.Equals(items[idx].Status, "showing", StringComparison.OrdinalIgnoreCase))
            return false;
        var newIdx = idx + direction;
        if (newIdx < 0 || newIdx >= items.Count) return false;
        if (string.Equals(items[newIdx].Status, "showing", StringComparison.OrdinalIgnoreCase))
            return false;
        (items[idx], items[newIdx]) = (items[newIdx], items[idx]);
        Save(root, items);
        return true;
    }

    public static Item? Remove(string root, string itemId)
    {
        var items = Load(root);
        var idx = items.FindIndex(i => i.Id == itemId);
        if (idx < 0) return null;
        var removed = items[idx];
        items.RemoveAt(idx);
        Save(root, items);
        TryDelete(removed.PreviewPath);
        TryDelete(removed.FramePath);
        return removed;
    }

    static void TryDelete(string path)
    {
        if (string.IsNullOrWhiteSpace(path) || !File.Exists(path)) return;
        try { File.Delete(path); } catch { /* ok */ }
    }

    public static async Task CompleteCloudJobAsync(string jobId, bool ok, string error)
    {
        if (string.IsNullOrWhiteSpace(jobId)) return;
        try
        {
            var app = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "FennsillApp");
            var tokenPath = Path.Combine(app, "cloud_device_token.txt");
            if (!File.Exists(tokenPath)) return;
            var token = (await File.ReadAllTextAsync(tokenPath)).Trim();
            if (token.StartsWith("Bearer ", StringComparison.OrdinalIgnoreCase))
                token = token[7..].Trim();
            if (string.IsNullOrWhiteSpace(token)) return;

            var cloud = "https://mcp.fennsill.com";
            var urlFile = Path.Combine(app, "cloud_url.txt");
            if (File.Exists(urlFile))
            {
                var line = (await File.ReadAllTextAsync(urlFile)).Trim().Split('\n')[0].Trim().TrimEnd('/');
                if (line.EndsWith("/mcp", StringComparison.OrdinalIgnoreCase))
                    line = line[..^4].TrimEnd('/');
                if (line.StartsWith("http://", StringComparison.OrdinalIgnoreCase) ||
                    line.StartsWith("https://", StringComparison.OrdinalIgnoreCase))
                    cloud = line;
            }

            using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(20) };
            client.DefaultRequestHeaders.TryAddWithoutValidation("Authorization", "Bearer " + token);
            var body = JsonSerializer.Serialize(new { ok, error });
            using var content = new StringContent(body, Encoding.UTF8, "application/json");
            await client.PostAsync($"{cloud}/api/agent/jobs/{jobId}/complete", content);
        }
        catch
        {
            // Best-effort; Agent reclaim will eventually clear stale claims.
        }
    }
}
