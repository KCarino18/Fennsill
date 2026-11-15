# Fennsill one-click install — works from website zip OR USB stick.
# Expects this layout next to the script (or one folder up):
#   FennsillSetup.bat
#   Fennsill.exe
#   connector\...
#   templates\...
#   firmware\...   (optional)
$ErrorActionPreference = "Stop"

function Find-PayloadRoot {
    $start = Split-Path -Parent $MyInvocation.PSCommandPath
    if (-not $start) { $start = Split-Path -Parent $MyInvocation.MyCommand.Path }
    foreach ($cand in @($start, (Split-Path -Parent $start), (Join-Path $start "payload"))) {
        foreach ($name in @("Fennsill.exe", "FennsillDesk.exe")) {
            if (Test-Path (Join-Path $cand $name)) { return (Resolve-Path $cand).Path }
            if (Test-Path (Join-Path $cand "fennsill-desk\out\$name")) { return (Resolve-Path $cand).Path }
        }
    }
    throw "Fennsill.exe not found. Put Setup next to Fennsill.exe (website zip or USB stick)."
}

$Payload = Find-PayloadRoot
$Dest = Join-Path $env:LOCALAPPDATA "Fennsill"

Write-Host ""
Write-Host " FENNSILL SETUP"
Write-Host " ----------------"
Write-Host " Source: $Payload"
Write-Host " Install to: $Dest"
Write-Host ""

New-Item -ItemType Directory -Force -Path $Dest | Out-Null

$ExeSrc = $null
foreach ($cand in @(
    (Join-Path $Payload "Fennsill.exe"),
    (Join-Path $Payload "FennsillDesk.exe"),
    (Join-Path $Payload "fennsill-desk\out\Fennsill.exe"),
    (Join-Path $Payload "fennsill-desk\out\FennsillDesk.exe")
)) {
    if (Test-Path $cand) { $ExeSrc = $cand; break }
}
$DestExe = Join-Path $Dest "Fennsill.exe"
try {
    Copy-Item -Force $ExeSrc $DestExe -ErrorAction Stop
} catch {
    $DestExe = Join-Path $Dest "FennsillDesk.exe"
    Copy-Item -Force $ExeSrc $DestExe
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

# Also copy factory folder next to install payload when present in the zip.
$FactorySrc = Join-Path $Payload "factory"
if (Test-Path $FactorySrc) {
    Sync-Tree $FactorySrc (Join-Path $Dest "factory")
    Write-Host " Factory tools copied under $Dest\factory"
}

$launchLines = @(
    "@echo off"
    "set FENNSILL_ROOT=$Dest"
    "cd /d `"$Dest`""
    "if exist `"$DestExe`" (start `"`" `"$DestExe`") else (start `"`" `"$Dest\FennsillDesk.exe`")"
)
$Launch = $null
foreach ($name in @("Fennsill.cmd", "Launch-Fennsill.cmd")) {
    $cand = Join-Path $Dest $name
    try {
        Set-Content -LiteralPath $cand -Value $launchLines -Encoding ASCII -ErrorAction Stop
        $Launch = $cand
        break
    } catch {
        Write-Host " Launcher name blocked: $name"
    }
}
if (-not $Launch) { throw "Could not write a launcher under $Dest" }

try {
    $Wsh = New-Object -ComObject WScript.Shell
    $Desktop = [Environment]::GetFolderPath("Desktop")
    $sc = $Wsh.CreateShortcut((Join-Path $Desktop "Fennsill.lnk"))
    $sc.TargetPath = $Launch
    $sc.WorkingDirectory = $Dest
    $sc.Save()
    # Remove leftover local Host shortcut (cloud MCP replaced FennsillHost).
    $oldHost = Join-Path $Desktop "Fennsill Host.lnk"
    if (Test-Path $oldHost) { Remove-Item -Force $oldHost -ErrorAction SilentlyContinue }
    $FactoryExe = Join-Path $Dest "factory\FennsillFactory.exe"
    if (Test-Path $FactoryExe) {
        $sc3 = $Wsh.CreateShortcut((Join-Path $Desktop "Fennsill Factory.lnk"))
        $sc3.TargetPath = $FactoryExe
        $sc3.WorkingDirectory = (Join-Path $Dest "factory")
        $sc3.Save()
    }
} catch {
    Write-Host " Desktop shortcut skipped ($($_.Exception.Message))"
}

# Startup folder is often locked by policy / antivirus — never fail the install for this.
try {
    $StartupDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
    New-Item -ItemType Directory -Force -Path $StartupDir | Out-Null
    Copy-Item -Force $Launch (Join-Path $StartupDir (Split-Path -Leaf $Launch)) -ErrorAction Stop
} catch {
    Write-Host " Startup auto-launch skipped (permission denied). You can still open Fennsill from the desktop shortcut."
}

$env:FENNSILL_ROOT = $Dest
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $Dest "connector\browsers"
if (Get-Command python -ErrorAction SilentlyContinue) {
    Write-Host " Configuring Claude / ChatGPT / other AI apps..."
    python (Join-Path $Dest "connector\bootstrap.py")
    if (-not (Test-Path (Join-Path $Dest "connector\browsers"))) {
        Write-Host " Installing render engine (one-time download)..."
        try {
            python -m playwright install chromium
        } catch {
            Write-Host " Playwright install skipped — Fennsill will retry when needed."
        }
    }
    Write-Host " Reading panel serial (leave the panel plugged in)..."
    $bindScript = $null
    foreach ($cand in @(
        (Join-Path $Dest "connector\device_bind_tool.py"),
        (Join-Path $Dest "connector\bind_device.py"),
        (Join-Path $Dest "connector\runtime\bind_device.py")
    )) {
        if (Test-Path $cand) { $bindScript = $cand; break }
    }
    try {
        if ($bindScript) { python $bindScript }
    } catch {
        Write-Host " Panel bind skipped — open Fennsill with the panel plugged in to finish."
    }
} else {
    Write-Host " Python not found — install Python 3, then reopen Fennsill once to finish AI setup."
}

Write-Host ""
Write-Host " Done."
Write-Host " - Desktop shortcut: Fennsill"
Write-Host " - Your panel serial is shown above when the panel answered"
Write-Host " - Leave Fennsill open with the panel plugged in"
Write-Host " - Restart Claude or ChatGPT once, then talk to it"
Write-Host ""
Start-Process $Launch
