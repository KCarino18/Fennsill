using System.Diagnostics;

namespace FennsillAgent;

/// <summary>
/// Owns the USB cloud agent process. Desk must not start/kill cloud_agent.py.
/// </summary>
sealed class CloudAgentHostedService : BackgroundService
{
    readonly ILogger<CloudAgentHostedService> _log;
    Process? _child;

    public CloudAgentHostedService(ILogger<CloudAgentHostedService> log)
    {
        _log = log;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        InstallPaths.ApplyProcessEnvironment();
        var root = InstallPaths.ResolveInstallRoot();
        _log.LogInformation("FennSill Agent root={Root}", root);

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await RunOnce(root, stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception ex)
            {
                _log.LogError(ex, "cloud_agent supervisor error");
            }

            if (stoppingToken.IsCancellationRequested)
                break;
            try
            {
                await Task.Delay(TimeSpan.FromSeconds(3), stoppingToken);
            }
            catch (OperationCanceledException)
            {
                break;
            }
        }

        StopChild();
    }

    async Task RunOnce(string root, CancellationToken stoppingToken)
    {
        var script = Path.Combine(root, "connector", "runtime", "cloud_agent.py");
        if (!File.Exists(script))
        {
            _log.LogWarning("cloud_agent.py missing at {Script}", script);
            await Task.Delay(TimeSpan.FromSeconds(10), stoppingToken);
            return;
        }

        var python = FindPython();
        var psi = new ProcessStartInfo
        {
            FileName = python,
            Arguments = $"\"{script}\"",
            WorkingDirectory = root,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        psi.Environment["LOCALAPPDATA"] = InstallPaths.ResolveUserLocalAppData();
        psi.Environment["FENNSILL_ROOT"] = root;
        psi.Environment["PLAYWRIGHT_BROWSERS_PATH"] = Path.Combine(root, "connector", "browsers");
        psi.Environment["PYTHONUNBUFFERED"] = "1";
        psi.Environment["PYTHONUTF8"] = "1";
        psi.Environment["PYTHONIOENCODING"] = "utf-8";
        psi.Environment["PYTHONPATH"] = Path.Combine(root, "connector", "runtime");

        _log.LogInformation("Starting cloud_agent via {Python}", python);
        var proc = Process.Start(psi);
        if (proc == null)
        {
            _log.LogError("Failed to start python for cloud_agent");
            await Task.Delay(TimeSpan.FromSeconds(5), stoppingToken);
            return;
        }

        _child = proc;
        proc.OutputDataReceived += (_, e) =>
        {
            if (!string.IsNullOrEmpty(e.Data))
                _log.LogInformation("agent: {Line}", e.Data);
        };
        proc.ErrorDataReceived += (_, e) =>
        {
            if (!string.IsNullOrEmpty(e.Data))
                _log.LogWarning("agent: {Line}", e.Data);
        };
        proc.BeginOutputReadLine();
        proc.BeginErrorReadLine();

        try
        {
            await proc.WaitForExitAsync(stoppingToken);
            _log.LogWarning("cloud_agent exited code={Code}", proc.ExitCode);
        }
        catch (OperationCanceledException)
        {
            StopChild();
            throw;
        }
        finally
        {
            try { proc.Dispose(); } catch { /* ignore */ }
            if (ReferenceEquals(_child, proc))
                _child = null;
        }
    }

    void StopChild()
    {
        var proc = _child;
        _child = null;
        if (proc == null) return;
        try
        {
            if (!proc.HasExited)
            {
                proc.Kill(entireProcessTree: true);
                proc.WaitForExit(5000);
            }
        }
        catch
        {
            /* ignore */
        }
        try { proc.Dispose(); } catch { /* ignore */ }
    }

    public override void Dispose()
    {
        StopChild();
        base.Dispose();
    }

    static string FindPython()
    {
        foreach (var name in new[] { "python", "py" })
        {
            try
            {
                var psi = new ProcessStartInfo
                {
                    FileName = name,
                    ArgumentList = { "--version" },
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                };
                using var p = Process.Start(psi);
                if (p is null) continue;
                p.WaitForExit(4000);
                if (p.ExitCode == 0) return name;
            }
            catch
            {
                /* try next */
            }
        }

        var userLocal = InstallPaths.ResolveUserLocalAppData();
        foreach (var cand in new[]
                 {
                     Path.Combine(userLocal, "Python", "pythoncore-3.14-64", "python.exe"),
                     Path.Combine(userLocal, "Python", "bin", "python.exe"),
                     Path.Combine(
                         Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                         "Python",
                         "pythoncore-3.14-64",
                         "python.exe"),
                 })
        {
            if (File.Exists(cand)) return cand;
        }

        return "python";
    }
}
