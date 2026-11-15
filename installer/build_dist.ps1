# Builds a folder you can ZIP for the website or copy to a USB stick.
$ErrorActionPreference = "Stop"
$Project = Split-Path -Parent $PSScriptRoot
$Out = Join-Path $Project "dist\Fennsill"
$Exe = Join-Path $Project "Fennsill.exe"
if (-not (Test-Path $Exe)) {
    $Exe = Join-Path $Project "fennsill-desk\out\Fennsill.exe"
}
if (-not (Test-Path $Exe)) { throw "Publish Fennsill.exe first." }

if (Test-Path $Out) { Remove-Item -Recurse -Force $Out }
New-Item -ItemType Directory -Force -Path $Out | Out-Null

Copy-Item -Force $Exe (Join-Path $Out "Fennsill.exe")
Copy-Item -Force (Join-Path $PSScriptRoot "Install-Fennsill.ps1") (Join-Path $Out "Install-Fennsill.ps1")

function Sync-Tree($src, $dst) {
    if (-not (Test-Path $src)) { return }
    New-Item -ItemType Directory -Force -Path $dst | Out-Null
    & robocopy $src $dst /E /XD __pycache__ pages inbox /NFL /NDL /NJH /NJS /R:1 /W:1 | Out-Null
}
# Keep the download/USB package lean (skip Playwright browser cache — installed on first use).
function Sync-Connector($src, $dst) {
    if (-not (Test-Path $src)) { return }
    New-Item -ItemType Directory -Force -Path $dst | Out-Null
    & robocopy $src $dst /E /XD __pycache__ pages inbox browsers /NFL /NDL /NJH /NJS /R:1 /W:1 | Out-Null
}
Sync-Connector (Join-Path $Project "connector") (Join-Path $Out "connector")
Sync-Tree (Join-Path $Project "templates") (Join-Path $Out "templates")
Sync-Tree (Join-Path $Project "firmware") (Join-Path $Out "firmware")
# Optional tunnel helper if present and small enough
if (Test-Path (Join-Path $Project "connector\bin\cloudflared.exe")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $Out "connector\bin") | Out-Null
    Copy-Item -Force (Join-Path $Project "connector\bin\cloudflared.exe") (Join-Path $Out "connector\bin\cloudflared.exe")
}

@(
    "@echo off"
    "title Fennsill Setup"
    "cd /d `"%~dp0`""
    "echo."
    "echo  FENNSILL SETUP"
    "echo  Website download or USB stick — same installer."
    "echo."
    "powershell -NoProfile -ExecutionPolicy Bypass -File `"%~dp0Install-Fennsill.ps1`""
    "if errorlevel 1 ("
    "  echo Setup failed."
    "  pause"
    "  exit /b 1"
    ")"
    "echo."
    "echo Installed. You can close this window."
    "timeout /t 4 >nul"
) | Set-Content -Encoding ASCII (Join-Path $Out "FennsillSetup.bat")

@(
    "Fennsill"
    "========"
    ""
    "Install from this folder (USB stick or unzipped website download):"
    "  Double-click  FennsillSetup.bat"
    ""
    "Then:"
    "  1. Plug in the panel"
    "  2. Leave Fennsill open"
    "  3. Restart Claude or ChatGPT once"
    "  4. Talk to your AI"
) | Set-Content -Encoding ASCII (Join-Path $Out "README.txt")

# Zip for website
$Zip = Join-Path $Project "dist\Fennsill-Setup.zip"
if (Test-Path $Zip) { Remove-Item -Force $Zip }
Compress-Archive -Path (Join-Path $Out "*") -DestinationPath $Zip -Force

Write-Host "USB / folder: $Out"
Write-Host "Website zip:  $Zip"
