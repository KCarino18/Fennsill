# Artiphact one-click install — works from website zip OR USB stick.
# Expects this layout next to the script (or one folder up):
#   ArtiphactSetup.bat
#   Artiphact.exe
#   connector\...
#   templates\...
#   firmware\...   (optional)
$ErrorActionPreference = "Stop"

function Find-PayloadRoot {
    $start = Split-Path -Parent $MyInvocation.PSCommandPath
    if (-not $start) { $start = Split-Path -Parent $MyInvocation.MyCommand.Path }
    foreach ($cand in @($start, (Split-Path -Parent $start), (Join-Path $start "payload"))) {
        if (Test-Path (Join-Path $cand "Artiphact.exe")) { return (Resolve-Path $cand).Path }
        if (Test-Path (Join-Path $cand "artiphact-desk\out\Artiphact.exe")) { return (Resolve-Path $cand).Path }
    }
    throw "Artiphact.exe not found. Put Setup next to Artiphact.exe (website zip or USB stick)."
}

$Payload = Find-PayloadRoot
$Dest = Join-Path $env:LOCALAPPDATA "Artiphact"

Write-Host ""
Write-Host " ARTIPHACT SETUP"
Write-Host " ----------------"
Write-Host " Source: $Payload"
Write-Host " Install to: $Dest"
Write-Host ""

New-Item -ItemType Directory -Force -Path $Dest | Out-Null

$ExeSrc = Join-Path $Payload "Artiphact.exe"
if (-not (Test-Path $ExeSrc)) {
    $ExeSrc = Join-Path $Payload "artiphact-desk\out\Artiphact.exe"
}
Copy-Item -Force $ExeSrc (Join-Path $Dest "Artiphact.exe")

$HostSrc = Join-Path $Payload "ArtiphactHost.exe"
if (-not (Test-Path $HostSrc)) {
    $HostSrc = Join-Path $Payload "artiphact-host\out\ArtiphactHost.exe"
}
if (Test-Path $HostSrc) {
    Copy-Item -Force $HostSrc (Join-Path $Dest "ArtiphactHost.exe")
}

function Sync-Tree([string]$src, [string]$dst) {
    if (-not (Test-Path $src)) { return }
    New-Item -ItemType Directory -Force -Path $dst | Out-Null
    & robocopy $src $dst /E /XD __pycache__ pages inbox /NFL /NDL /NJH /NJS /R:1 /W:1 | Out-Null
}

# Prefer packaged payload folders; fall back to project layout.
$ConnSrc = Join-Path $Payload "connector"
if (-not (Test-Path $ConnSrc)) { $ConnSrc = Join-Path (Split-Path -Parent $Payload) "connector" }
$TemplSrc = Join-Path $Payload "templates"
if (-not (Test-Path $TemplSrc)) { $TemplSrc = Join-Path (Split-Path -Parent $Payload) "templates" }
$FwSrc = Join-Path $Payload "firmware"
if (-not (Test-Path $FwSrc)) { $FwSrc = Join-Path (Split-Path -Parent $Payload) "firmware" }

Sync-Tree $ConnSrc (Join-Path $Dest "connector")
Sync-Tree $TemplSrc (Join-Path $Dest "templates")
Sync-Tree $FwSrc (Join-Path $Dest "firmware")

$Launch = Join-Path $Dest "Artiphact.cmd"
@(
    "@echo off"
    "set ARTIPHACT_ROOT=$Dest"
    "cd /d `"$Dest`""
    "start `"`" `"$Dest\Artiphact.exe`""
) | Set-Content -Encoding ASCII $Launch

try {
    $Wsh = New-Object -ComObject WScript.Shell
    $Desktop = [Environment]::GetFolderPath("Desktop")
    $sc = $Wsh.CreateShortcut((Join-Path $Desktop "Artiphact.lnk"))
    $sc.TargetPath = $Launch
    $sc.WorkingDirectory = $Dest
    $sc.Save()
    $HostExe = Join-Path $Dest "ArtiphactHost.exe"
    if (Test-Path $HostExe) {
        $sc2 = $Wsh.CreateShortcut((Join-Path $Desktop "Artiphact Host.lnk"))
        $sc2.TargetPath = $HostExe
        $sc2.WorkingDirectory = $Dest
        $sc2.Save()
    }
} catch {
    Write-Host " Desktop shortcut skipped ($($_.Exception.Message))"
}

# Startup folder is often locked by policy / antivirus — never fail the install for this.
try {
    $StartupDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
    New-Item -ItemType Directory -Force -Path $StartupDir | Out-Null
    Copy-Item -Force $Launch (Join-Path $StartupDir "Artiphact.cmd") -ErrorAction Stop
} catch {
    Write-Host " Startup auto-launch skipped (permission denied). You can still open Artiphact from the desktop shortcut."
}

$env:ARTIPHACT_ROOT = $Dest
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $Dest "connector\browsers"
if (Get-Command python -ErrorAction SilentlyContinue) {
    Write-Host " Configuring Claude / ChatGPT / other AI apps..."
    python (Join-Path $Dest "connector\bootstrap.py")
    if (-not (Test-Path (Join-Path $Dest "connector\browsers"))) {
        Write-Host " Installing render engine (one-time download)..."
        try {
            python -m playwright install chromium
        } catch {
            Write-Host " Playwright install skipped — Artiphact will retry when needed."
        }
    }
    Write-Host " Reading panel serial (leave the panel plugged in)..."
    try {
        python (Join-Path $Dest "connector\bind_device.py")
    } catch {
        Write-Host " Panel bind skipped — open Artiphact with the panel plugged in to finish."
    }
} else {
    Write-Host " Python not found — install Python 3, then reopen Artiphact once to finish AI setup."
}

Write-Host ""
Write-Host " Done."
Write-Host " - Desktop shortcut: Artiphact"
Write-Host " - Your panel serial is shown above when the panel answered"
Write-Host " - Leave Artiphact open with the panel plugged in"
Write-Host " - Restart Claude or ChatGPT once, then talk to it"
Write-Host ""
Start-Process $Launch
