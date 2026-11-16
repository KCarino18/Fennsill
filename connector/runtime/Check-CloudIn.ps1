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
    "User-Agent" = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    "Accept" = "application/json, text/plain, */*"
    "Accept-Language" = "en-US,en;q=0.9"
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

$code = 0
$cfg = Invoke-Fenn "/api/config" ""
Write-Host "GET /api/config -> $($cfg.Status)"
Write-Host "  $($cfg.Body)"
if ($cfg.Status -ne 200) {
  Write-Host "FAIL: cannot reach cloud."
  $code = 1
} elseif (-not $token) {
  Write-Host "FAIL: no device key. Mint on https://mcp.fennsill.com then Paste device key in Fennsill.exe"
  $code = 2
} else {
  $hb = Invoke-Fenn "/api/agent/heartbeat" $token
  Write-Host "GET /api/agent/heartbeat -> $($hb.Status)"
  Write-Host "  $($hb.Body)"
  if ($hb.Status -eq 200) { Write-Host "OK: check-in works."; $code = 0 }
  elseif ($hb.Status -eq 401) { Write-Host "FAIL: bad/wrong key (often pasted account Bearer). Remint device key."; $code = 3 }
  elseif ($hb.Status -eq 403) { Write-Host "FAIL: 403 refused (inactive access or unlinked). Remint; renew if mint fails."; $code = 4 }
  else { Write-Host "FAIL: unexpected. Send this output to support."; $code = 5 }
}

Write-Host ""
Write-Host "Done (exit $code). Copy everything above and send it."
if ($Host.Name -eq "ConsoleHost") {
  Write-Host "Press Enter to close..."
  [void][Console]::ReadLine()
}
exit $code
