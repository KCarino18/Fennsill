# Publish Desk (+ optional Factory) and keep README version in sync.
# Usage:
#   powershell -File installer\publish_release.ps1 -Version 0.1.14
#   powershell -File installer\publish_release.ps1 -Version 0.1.14 -Factory
param(
  [Parameter(Mandatory = $true)]
  [string]$Version,
  [switch]$Factory,
  [switch]$SkipPush
)

$ErrorActionPreference = "Stop"
$Version = $Version.TrimStart("v", "V")
$Tag = "v$Version"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$app = Join-Path $env:LOCALAPPDATA "FennsillApp\tmp\publish-$Version"
$deskOut = Join-Path $app "desk"
$facOut = Join-Path $app "factory"
$deskObj = Join-Path $app "desk-obj\"
$facObj = Join-Path $app "fac-obj\"
Remove-Item -Recurse -Force $app -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $deskOut, $facOut, $deskObj, $facObj | Out-Null

Write-Host "Publishing Desk..."
dotnet publish (Join-Path $Root "fennsill-desk\FennsillDesk.csproj") -c Release -o $deskOut "-p:BaseIntermediateOutputPath=$deskObj" --nologo
$deskBuilt = Get-ChildItem $deskOut -Filter "*.exe" | Where-Object { $_.Name -match "Fennsill" } | Select-Object -First 1
if (-not $deskBuilt) { throw "Desk exe not found in $deskOut" }
$deskExe = Join-Path $deskOut "Fennsill.exe"
Copy-Item -Force $deskBuilt.FullName $deskExe

$assets = @($deskExe)
if ($Factory) {
  Write-Host "Publishing Factory..."
  dotnet publish (Join-Path $Root "fennsill-factory\FennsillFactory.csproj") -c Release -o $facOut "-p:BaseIntermediateOutputPath=$facObj" --nologo
  $facBuilt = Get-ChildItem $facOut -Filter "*.exe" | Where-Object { $_.Name -match "Factory" } | Select-Object -First 1
  if (-not $facBuilt) { throw "Factory exe not found in $facOut" }
  $facExe = Join-Path $facOut "FennsillFactory.exe"
  Copy-Item -Force $facBuilt.FullName $facExe
  $assets += $facExe
}

$readme = Join-Path $Root "README.md"
$readmeText = Get-Content $readme -Raw
$badge = "**Latest release: [$Tag](https://github.com/KCarino18/Fennsill/releases/tag/$Tag)** — $(Get-Date -Format 'yyyy-MM-dd')"
if ($readmeText -match '(?m)^\*\*Latest release:.*\*\*.*$') {
  $readmeText = [regex]::Replace($readmeText, '(?m)^\*\*Latest release:.*\*\*.*$', $badge)
} else {
  $readmeText = $readmeText -replace '(?m)^(## One-click downloads \(Windows\)\s*)$', "`$1`r`n`r`n$badge`r`n"
}
Set-Content -Path $readme -Value $readmeText -NoNewline

git add README.md
git commit -m "Bump README latest release to $Tag."
if (-not $SkipPush) {
  git push origin HEAD
}

$notes = @"
Fennsill $Tag

See README for install steps. Desk self-installs to %LOCALAPPDATA%\FennsillApp\.
"@
gh release create $Tag @assets --title "Fennsill $Tag" --notes $notes
Write-Host "Published $Tag"
Write-Host ($assets -join "`n")
