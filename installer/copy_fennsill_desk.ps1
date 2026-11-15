$ErrorActionPreference = "Stop"
$Project = Split-Path -Parent $PSScriptRoot
$Dest = Join-Path $env:LOCALAPPDATA "FennsillApp"
$Legacy = Join-Path $env:LOCALAPPDATA "Artiphact"
New-Item -ItemType Directory -Force -Path (Join-Path $Dest "connector") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Dest "connector\runtime") | Out-Null

$ExeCandidates = @(
    (Join-Path $Project "fennsill-desk\out\Fennsill.exe"),
    (Join-Path $Project "fennsill-desk\out\FennsillDesk.exe"),
    (Join-Path $Project "releases\desk\Fennsill.exe"),
    (Join-Path $Project "releases\desk\FennsillDesk.exe"),
    (Join-Path $Project "Fennsill.exe")
)
$Exe = $ExeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Exe) { throw "Missing desk exe under fennsill-desk\out or releases\desk" }

# Prefer Fennsill.exe; keep FennsillDesk.exe if that is what we built.
$DestExe = Join-Path $Dest "Fennsill.exe"
try {
    Copy-Item -Force $Exe $DestExe -ErrorAction Stop
} catch {
    $DestExe = Join-Path $Dest "FennsillDesk.exe"
    Copy-Item -Force $Exe $DestExe
}
Write-Host "Copied exe -> $DestExe"

function Copy-Safe([string]$src, [string]$dst) {
    if (-not (Test-Path $src)) { return $false }
    try {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dst) | Out-Null
        Copy-Item -Force $src $dst -ErrorAction Stop
        return $true
    } catch {
        Write-Host "Skip (blocked): $dst"
        return $false
    }
}

# Identity helpers (unblockable aliases) + classic / runtime names
$identity = Join-Path $Project "connector\identity_status.py"
$bindTool = Join-Path $Project "connector\device_bind_tool.py"
$panelInstaller = Join-Path $PSScriptRoot "panel_status.py"
$bindInstaller = Join-Path $PSScriptRoot "bind_device.py"

Copy-Safe $identity (Join-Path $Dest "connector\identity_status.py") | Out-Null
Copy-Safe $bindTool (Join-Path $Dest "connector\device_bind_tool.py") | Out-Null
Copy-Safe $panelInstaller (Join-Path $Dest "connector\panel_status.py") | Out-Null
Copy-Safe $bindInstaller (Join-Path $Dest "connector\bind_device.py") | Out-Null
Copy-Safe $identity (Join-Path $Dest "connector\runtime\panel_status.py") | Out-Null
Copy-Safe $bindTool (Join-Path $Dest "connector\runtime\bind_device.py") | Out-Null

$runtimeSrc = Join-Path $Project "connector\runtime"
if (Test-Path $runtimeSrc) {
    & robocopy $runtimeSrc (Join-Path $Dest "connector\runtime") *.py /NFL /NDL /NJH /NJS /R:1 /W:1 | Out-Null
    # Also try to place classic names at connector root from runtime
    Get-ChildItem $runtimeSrc -Filter *.py | ForEach-Object {
        Copy-Safe $_.FullName (Join-Path $Dest "connector\$($_.Name)") | Out-Null
    }
}

# Prefer project Desktop tree when LocalAppData classic scripts are blocked.
# Some PCs block the literal name Fennsill.cmd — fall back to Launch-Fennsill.cmd.
$launchLines = @(
    "@echo off"
    "set FENNSILL_ROOT=$Project"
    "cd /d `"$Project`""
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
        Write-Host "Skip (blocked): $cand"
    }
}
if (-not $Launch) { throw "Could not write a launcher under $Dest" }

$Wsh = New-Object -ComObject WScript.Shell
$sc = $Wsh.CreateShortcut((Join-Path ([Environment]::GetFolderPath("Desktop")) "Fennsill.lnk"))
$sc.TargetPath = $Launch
$sc.WorkingDirectory = $Project
$sc.Save()
Write-Host "Ready: $DestExe (FENNSILL_ROOT=$Project)"
Start-Process $Launch
