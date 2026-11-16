# Publish Setup (Desk + Agent service) + Factory; keep README version/links in sync.
# Usage:
#   powershell -File installer\publish_release.ps1 -Version 0.1.19
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
$agentOut = Join-Path $app "agent"
$facOut = Join-Path $app "factory"
$setupOut = Join-Path $app "setup"
$deskObj = Join-Path $app "desk-obj\"
$agentObj = Join-Path $app "agent-obj\"
$facObj = Join-Path $app "fac-obj\"
$setupObj = Join-Path $app "setup-obj\"
$setupPayload = Join-Path $Root "fennsill-setup\setup-payload"

Remove-Item -Recurse -Force $app -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force $setupPayload -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $deskOut, $agentOut, $facOut, $setupOut, $deskObj, $agentObj, $facObj, $setupObj, $setupPayload | Out-Null

function Sync-Tree([string]$src, [string]$dst) {
  if (-not (Test-Path -LiteralPath $src)) { return }
  New-Item -ItemType Directory -Force -Path $dst | Out-Null
  Get-ChildItem -LiteralPath $src -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
    $rel = $_.FullName.Substring($src.Length).TrimStart('\', '/')
    if ($rel -match '(^|\\|/)(__pycache__|browsers|pages|inbox)(\\|/|$)') { return }
    if ($_.Name -like '_debug_*') { return }
    $target = Join-Path $dst $rel
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
    Copy-Item -LiteralPath $_.FullName -Destination $target -Force
  }
}

Write-Host "Publishing Desk..."
dotnet publish (Join-Path $Root "fennsill-desk\FennsillDesk.csproj") -c Release -o $deskOut "-p:BaseIntermediateOutputPath=$deskObj" --nologo
$deskBuilt = Get-ChildItem $deskOut -Filter "*.exe" |
  Where-Object { $_.Name -match "Fennsill" -and $_.Name -notmatch "Factory|Setup|Agent" } |
  Sort-Object { if ($_.Name -eq "Fennsill.exe") { 0 } else { 1 } } |
  Select-Object -First 1
if (-not $deskBuilt) { throw "Desk exe not found in $deskOut" }
$deskExe = Join-Path $deskOut "Fennsill.exe"
if ($deskBuilt.FullName -ne $deskExe) {
  Copy-Item -Force $deskBuilt.FullName $deskExe
}

Write-Host "Publishing Agent service..."
dotnet publish (Join-Path $Root "fennsill-agent\FennsillAgent.csproj") -c Release -o $agentOut "-p:BaseIntermediateOutputPath=$agentObj" --nologo
$agentBuilt = Get-ChildItem $agentOut -Filter "FennsillAgent.exe" | Select-Object -First 1
if (-not $agentBuilt) { throw "FennsillAgent.exe not found in $agentOut" }
$agentExe = $agentBuilt.FullName

Write-Host "Staging Setup payload..."
Copy-Item -Force $deskExe (Join-Path $setupPayload "Fennsill.exe")
Copy-Item -Force $agentExe (Join-Path $setupPayload "FennsillAgent.exe")
Sync-Tree (Join-Path $Root "connector") (Join-Path $setupPayload "connector")
Sync-Tree (Join-Path $Root "firmware") (Join-Path $setupPayload "firmware")
Sync-Tree (Join-Path $Root "templates") (Join-Path $setupPayload "templates")
if (-not (Test-Path (Join-Path $setupPayload "connector\push_page.py"))) {
  throw "setup-payload missing connector\push_page.py"
}
if (-not (Test-Path (Join-Path $setupPayload "connector\runtime\cloud_agent.py"))) {
  throw "setup-payload missing cloud_agent.py"
}

Write-Host "Publishing Setup..."
dotnet publish (Join-Path $Root "fennsill-setup\FennsillSetup.csproj") -c Release -o $setupOut "-p:BaseIntermediateOutputPath=$setupObj" --nologo
$setupBuilt = Get-ChildItem $setupOut -Filter "FennsillSetup.exe" | Select-Object -First 1
if (-not $setupBuilt) { throw "FennsillSetup.exe not found in $setupOut" }
$setupExe = $setupBuilt.FullName

$assets = @($setupExe)
if (-not $SkipFactory) {
  Write-Host "Publishing Factory..."
  dotnet publish (Join-Path $Root "fennsill-factory\FennsillFactory.csproj") -c Release -o $facOut "-p:BaseIntermediateOutputPath=$facObj" --nologo
  $facBuilt = Get-ChildItem $facOut -Filter "*.exe" | Where-Object { $_.Name -match "Factory" } | Select-Object -First 1
  if (-not $facBuilt) { throw "Factory exe not found in $facOut" }
  $facExe = Join-Path $facOut "FennsillFactory.exe"
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
| **Fennsill Setup** (Desk + Agent service — run as Admin once) | [FennsillSetup.exe]($base/FennsillSetup.exe) |
| **Fennsill Factory** (flasher — manufacturing PC) | [FennsillFactory.exe]($base/FennsillFactory.exe) |
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

- Setup (Desk + Agent Windows service): $base/FennsillSetup.exe
- Factory: $base/FennsillFactory.exe

Run FennsillSetup.exe once as Administrator. It installs Desk, the always-on USB Agent service, and a desktop shortcut. Closing Desk no longer drops cloud check-in. Page pushes are MCP-only.
"@
gh release create $Tag @assets --title "Fennsill $Tag" --notes $notes
Write-Host "Published $Tag"
Write-Host ($assets -join "`n")
