# Fennsill buyer diagnostic — paste into PowerShell on the panel PC.
$ErrorActionPreference = "Continue"
$app = Join-Path $env:LOCALAPPDATA "FennsillApp"
$cloud = "https://mcp.fennsill.com"
$urlFile = Join-Path $app "cloud_url.txt"
if (Test-Path $urlFile) {
  $line = (Get-Content $urlFile -TotalCount 1).Trim().TrimEnd("/")
  if ($line -match "/mcp$") { $line = $line.Substring(0, $line.Length - 4).TrimEnd("/") }
  if ($line -match "^https?://") { $cloud = $line }
}
$token = ""
foreach ($name in @("cloud_device_token.txt", "device_token.txt")) {
  $p = Join-Path $app $name
  if (Test-Path $p) {
    $token = (Get-Content $p -Raw).Trim()
    if ($token.ToLower().StartsWith("bearer ")) { $token = $token.Substring(7).Trim() }
    if ($token) { break }
  }
}

Write-Host "Fennsill cloud check-in"
Write-Host "  app folder: $app"
Write-Host "  exists:     $(Test-Path $app)"
Write-Host "  cloud:      $cloud"
Write-Host "  device key: $(if ($token) { "YES ($($token.Length) chars)" } else { "MISSING" })"
Write-Host ""

function Invoke-Fenn([string]$Path, [string]$Tok) {
  $headers = @{
    "User-Agent" = "FennsillDesk/1.0 (Windows; check-cloud-in)"
    "Accept" = "application/json"
  }
  if ($Tok) { $headers["Authorization"] = "Bearer $Tok" }
  try {
    $r = Invoke-WebRequest -Uri ($cloud + $Path) -Headers $headers -UseBasicParsing -TimeoutSec 25
    return @{ Status = [int]$r.StatusCode; Body = $r.Content }
  } catch {
    $resp = $_.Exception.Response
    if ($resp) {
      $code = [int]$resp.StatusCode
      $reader = New-Object IO.StreamReader($resp.GetResponseStream())
      return @{ Status = $code; Body = $reader.ReadToEnd() }
    }
    return @{ Status = 0; Body = $_.Exception.Message }
  }
}

$cfg = Invoke-Fenn "/api/config" ""
Write-Host "GET /api/config -> $($cfg.Status)"
Write-Host "  $($cfg.Body)"
if ($cfg.Status -ne 200) {
  Write-Host "FAIL: cannot reach cloud."
  exit 1
}
if (-not $token) {
  Write-Host "FAIL: no device key. Mint on https://mcp.fennsill.com then Paste device key in Fennsill.exe"
  exit 2
}
$hb = Invoke-Fenn "/api/agent/heartbeat" $token
Write-Host "GET /api/agent/heartbeat -> $($hb.Status)"
Write-Host "  $($hb.Body)"
if ($hb.Status -eq 200) { Write-Host "OK: check-in works."; exit 0 }
if ($hb.Status -eq 401) { Write-Host "FAIL: bad/wrong key (often pasted account Bearer). Remint device key."; exit 3 }
if ($hb.Status -eq 403) { Write-Host "FAIL: 403 refused (inactive access or unlinked). Remint; renew if mint fails."; exit 4 }
Write-Host "FAIL: unexpected. Send this output to support."
exit 5
