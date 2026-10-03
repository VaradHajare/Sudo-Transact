# Opens an HTTPS tunnel to the backend on this laptop (http://localhost:8000) and prints the address
# to type into the phone app. The phone's mic only works over HTTPS. Keep this window open during the
# demo; press Ctrl+C to close the tunnel. Anyone with the address can reach the demo while it is open.
#
# Usage (from the repo root):  powershell -ExecutionPolicy Bypass -File mobile\tunnel.ps1

$cf = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
if (-not $cf) { $cf = "C:\Program Files (x86)\cloudflared\cloudflared.exe" }
if (-not (Test-Path $cf)) { Write-Host "cloudflared not found. Install it: winget install Cloudflare.cloudflared"; exit 1 }

try { Invoke-RestMethod http://localhost:8000/healthz -TimeoutSec 3 | Out-Null }
catch { Write-Host "The backend isn't running on port 8000. Start it first (see README)."; exit 1 }

Write-Host "Opening the tunnel..."
& $cf tunnel --no-autoupdate --url http://localhost:8000 2>&1 | ForEach-Object {
    $line = "$_"
    if ($line -match "(https://[a-z0-9-]+\.trycloudflare\.com)") {
        Write-Host ""
        Write-Host "  Type this into the phone app:  $($Matches[1])" -ForegroundColor Green
        Write-Host ""
    }
}
