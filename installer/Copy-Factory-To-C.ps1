# Copy Fennsill Factory next to a fixed manufacturing path (C:\factory).
$ErrorActionPreference = "Stop"
$Project = Split-Path -Parent $PSScriptRoot
$Src = Join-Path $Project "factory"
if (-not (Test-Path $Src)) { throw "Missing $Src" }

$Dest = "C:\factory"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
& robocopy $Src $Dest /E /XD __pycache__ tools /XF master.key /NFL /NDL /NJH /NJS /R:1 /W:1 | Out-Null

$ExeCandidates = @(
    (Join-Path $Src "FennsillFactory.exe"),
    (Join-Path $Project "releases\factory\FennsillFactory.exe"),
    (Join-Path $Project "FennsillFactory.exe")
)
foreach ($exe in $ExeCandidates) {
    if (Test-Path $exe) {
        Copy-Item -Force $exe (Join-Path $Dest "FennsillFactory.exe")
        break
    }
}

Write-Host "Factory ready at $Dest"
if (Test-Path (Join-Path $Dest "FennsillFactory.exe")) {
    Write-Host "Open: $Dest\FennsillFactory.exe"
} else {
    Write-Host "Build the exe first: $Src\Build-Factory-Exe.bat"
}
