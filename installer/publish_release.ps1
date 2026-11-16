# Publish Desk + Factory and keep README version + download links in sync.
# Usage:
#   powershell -File installer\publish_release.ps1 -Version 0.1.15
param(
  [Parameter(Mandatory = $true)]
  [string]$Version,
  [switch]$SkipFactory,
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
$deskBuilt = Get-ChildItem $deskOut -Filter "*.exe" |
  Where-Object { $_.Name -match "Fennsill" -and $_.Name -notmatch "Factory" } |
  Sort-Object { if ($_.Name -eq "Fennsill.exe") { 0 } else { 1 } } |
  Select-Object -First 1
if (-not $deskBuilt) { throw "Desk exe not found in $deskOut" }
$deskExe = Join-Path $deskOut "Fennsill.exe"
if ($deskBuilt.FullName -ne $deskExe) {
  Copy-Item -Force $deskBuilt.FullName $deskExe
}

$assets = @($deskExe)
if (-not $SkipFactory) {
  Write-Host "Publishing Factory..."
  dotnet publish (Join-Path $Root "fennsill-factory\FennsillFactory.csproj") -c Release -o $facOut "-p:BaseIntermediateOutputPath=$facObj" --nologo
  $facBuilt = Get-ChildItem $facOut -Filter "*.exe" | Where-Object { $_.Name -match "Factory" } | Select-Object -First 1
  if (-not $facBuilt) { throw "Factory exe not found in $facOut" }
  $facExe = Join-Path $facOut "FennsillFactory.exe"
  # Published name is already FennsillFactory.exe — copying onto itself fails Stop.
  if ($facBuilt.FullName -ne $facExe) {
    Copy-Item -Force $facBuilt.FullName $facExe
  }
  $assets += $facExe
}

$base = "https://github.com/KCarino18/Fennsill/releases/download/$Tag"
$date = Get-Date -Format "yyyy-MM-dd"
$badge = "**Latest release: [$Tag](https://github.com/KCarino18/Fennsill/releases/tag/$Tag)** — $date"
$table = @"
| What | Download |
|------|----------|
| **Fennsill** (desk — self-installs to LocalAppData) | [Fennsill.exe]($base/Fennsill.exe) |
| **Fennsill Factory** (flasher — self-installs to LocalAppData) | [FennsillFactory.exe]($base/FennsillFactory.exe) |
| **All releases** | [github.com/KCarino18/Fennsill/releases](https://github.com/KCarino18/Fennsill/releases) |
"@

$readme = Join-Path $Root "README.md"
$lines = [System.Collections.Generic.List[string]]::new()
$lines.AddRange([string[]](Get-Content $readme))
for ($i = 0; $i -lt $lines.Count; $i++) {
  if ($lines[$i] -match '^\*\*Latest release:') {
    $lines[$i] = $badge
  }
}
# Replace only the download table block (header + separator + rows starting with |)
$start = -1
for ($i = 0; $i -lt $lines.Count; $i++) {
  if ($lines[$i] -eq '| What | Download |') { $start = $i; break }
}
if ($start -ge 0) {
  $end = $start
  while ($end -lt $lines.Count -and ($lines[$end].StartsWith('|') -or $lines[$end] -eq '')) {
    if ($end -gt $start -and $lines[$end] -eq '') { break }
    $end++
  }
  $newRows = $table -split "`r?`n" | Where-Object { $_ -ne '' }
  $lines.RemoveRange($start, $end - $start)
  $lines.InsertRange($start, [string[]]$newRows)
}
[IO.File]::WriteAllLines($readme, $lines)

git add README.md
git commit -m "Bump README latest release to $Tag."
if (-not $SkipPush) {
  git push origin HEAD
}

$notes = @"
Fennsill $Tag

- Desk: $base/Fennsill.exe
- Factory: $base/FennsillFactory.exe

Desk self-installs to %LOCALAPPDATA%\FennsillApp\.
"@
gh release create $Tag @assets --title "Fennsill $Tag" --notes $notes
Write-Host "Published $Tag"
Write-Host ($assets -join "`n")
