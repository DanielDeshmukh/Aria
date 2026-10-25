# One-command public demo bring-up for Aria.
#   1. ensures the FastAPI server is up on :8000
#   2. (re)starts the Cloudflare quick tunnel (no account, no card, ~5 s)
#   3. updates the stable redirect page (../aria-demo-link) and pushes it
#   4. prints both URLs
# Run:  powershell -ExecutionPolicy Bypass -File .\start-demo.ps1
param([string]$RepoRoot = $PSScriptRoot)
$ErrorActionPreference = "Stop"

$stable = "https://danieldeshmukh.github.io/aria-demo-link/"
$redirectDir = Join-Path (Split-Path -Parent $RepoRoot) "aria-demo-link"
$cloudflared = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
if (-not (Test-Path $cloudflared)) { $cloudflared = "cloudflared" }

# 1. server
$up = $false
try { Invoke-WebRequest "http://localhost:8000/api/health" -UseBasicParsing -TimeoutSec 3 | Out-Null; $up = $true } catch {}
if (-not $up) {
    Write-Host "[1/4] starting uvicorn on :8000 ..."
    Start-Process -FilePath cmd -ArgumentList "/c","python -m uvicorn backend.main:app --port 8000 > %TEMP%\aria-8000.log 2>&1" -WorkingDirectory $RepoRoot
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        try { Invoke-WebRequest "http://localhost:8000/api/health" -UseBasicParsing -TimeoutSec 3 | Out-Null; $up = $true; break } catch { Start-Sleep 2 }
    }
    if (-not $up) { throw "uvicorn did not come up - check %TEMP%\aria-8000.log" }
} else { Write-Host "[1/4] uvicorn already up on :8000" }

# 2. tunnel — NEVER restart a healthy one (rapid kill/create makes Cloudflare
#    reject registration for a while and the raw hostname churns for nothing).
$tunUrl = $null
$tunUrlFile = "$env:TEMP\aria-tunnel-url.txt"
if ((Get-Process cloudflared -ErrorAction SilentlyContinue) -and (Test-Path $tunUrlFile)) {
    $candidate = (Get-Content $tunUrlFile -Raw).Trim()
    try {
        Invoke-WebRequest "$candidate/api/health" -UseBasicParsing -TimeoutSec 10 | Out-Null
        $tunUrl = $candidate
        Write-Host "[2/4] tunnel already healthy: $tunUrl (reusing)"
    } catch { }
}
if (-not $tunUrl) {
    Write-Host "[2/4] starting Cloudflare quick tunnel ..."
    Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep 1
    $tlog = "$env:TEMP\aria-tunnel.log"
    $tlog2 = "$env:TEMP\aria-tunnel.err.log"
    Remove-Item $tlog, $tlog2 -ErrorAction SilentlyContinue
    Start-Process -FilePath $cloudflared -ArgumentList "tunnel","--url","http://localhost:8000" -RedirectStandardOutput $tlog -RedirectStandardError $tlog2 -WindowStyle Hidden
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        foreach ($f in @($tlog, $tlog2)) {
            if (Test-Path $f) {
                $m = Select-String -Path $f -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -ErrorAction SilentlyContinue | Select-Object -First 1
                if ($m) { $tunUrl = $m.Matches[0].Value; break }
            }
        }
        if ($tunUrl) { break }
        Start-Sleep 2
    }
    if (-not $tunUrl) { throw "tunnel produced no URL - check %TEMP%\aria-tunnel*.log" }
    Set-Content $tunUrlFile $tunUrl -NoNewline
    # wait until DNS + origin actually answer (not just a printed URL)
    $deadline = (Get-Date).AddSeconds(180)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        try { Invoke-WebRequest "$tunUrl/api/health" -UseBasicParsing -TimeoutSec 15 | Out-Null; $ready = $true; break } catch { Start-Sleep 10 }
    }
    if (-not $ready) { throw "tunnel URL printed but not serving yet - see %TEMP%\aria-tunnel.err.log" }
    Write-Host "[3/4] tunnel ready: $tunUrl"
} else { Write-Host "[3/4] tunnel reused" }

# 3. stable redirect page
if (Test-Path (Join-Path $redirectDir ".git")) {
    $page = Join-Path $redirectDir "index.html"
    (Get-Content $page -Raw) -replace "https://[a-z0-9-]+\.trycloudflare\.com", $tunUrl |
        Set-Content $page -Encoding utf8 -NoNewline
    # git emits harmless stderr warnings (CRLF); PS5.1 would turn redirected
    # native stderr into a terminating error under EAP=Stop -> relax locally.
    $ErrorActionPreference = "Continue"
    git -C $redirectDir add index.html 2>$null | Out-Null
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    git -C $redirectDir -c user.name="DanielDeshmukh" -c user.email="qure.deshmukhdaniel@gmail.com" commit -m "chore: point live link at $stamp" 2>$null | Out-Null
    git -C $redirectDir push origin main 2>$null | Out-Null
    $pushOk = $LASTEXITCODE -eq 0
    $ErrorActionPreference = "Stop"
    if ($pushOk) { Write-Host "[4/4] stable redirect updated + pushed" }
    else { Write-Host "[4/4] WARNING: push failed - stable link may be stale (rerun this script)" -ForegroundColor Yellow }
} else {
    Write-Host "[4/4] WARNING: $redirectDir not found - stable link NOT updated"
}

Write-Host ""
Write-Host "Stable link : $stable"
Write-Host "Direct link : $tunUrl"
Write-Host "(keep this machine awake while evaluators test)"
