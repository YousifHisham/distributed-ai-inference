param(
    [string]$MasterAddress = ""
)

$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent $PSScriptRoot

# ── Load .env ─────────────────────────────────────────────────────────────────
$envFile = Join-Path $RootDir ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
        $line = $_ -replace '\s+#.*$', ''          # strip inline comments
        if ($line -match '^([^=]+)=(.*)$') {
            $name  = $matches[1].Trim()
            $value = $matches[2].Trim()
            if (-not (Get-Item "env:$name" -ErrorAction SilentlyContinue)) {
                Set-Item "env:$name" $value
            }
        }
    }
}

# ── Detect this machine's LAN IP ──────────────────────────────────────────────
function Get-LanIP {
    $ip = Get-NetIPAddress -AddressFamily IPv4 |
          Where-Object { $_.InterfaceAlias -match 'Wi-Fi|Wireless|WLAN|Ethernet' -and
                         $_.IPAddress -notlike '127.*' -and
                         $_.IPAddress -notlike '169.254.*' } |
          Sort-Object PrefixLength |
          Select-Object -First 1 -ExpandProperty IPAddress
    return $ip
}

# ── Resolve master URL ─────────────────────────────────────────────────────────
$masterInput = if ($MasterAddress) { $MasterAddress } else { $env:MASTER_HTTP_URL }

if (-not $masterInput) {
    Write-Host "ERROR: No master address configured." -ForegroundColor Red
    Write-Host ""
    Write-Host "Either set MASTER_HTTP_URL in .env:"
    Write-Host "  MASTER_HTTP_URL=http://192.168.1.10:8000"
    Write-Host ""
    Write-Host "Or pass it as an argument:"
    Write-Host "  .\scripts\run-worker.ps1 192.168.1.10"
    exit 1
}

if ($masterInput -notmatch '^https?://') {
    $port = if ($env:MASTER_HTTP_PORT) { $env:MASTER_HTTP_PORT } else { "8000" }
    $masterInput = "http://${masterInput}:${port}"
}
$env:MASTER_HTTP_URL = $masterInput

# ── Resolve worker advertise host ─────────────────────────────────────────────
if (-not $env:WORKER_ADVERTISE_HOST) {
    $env:WORKER_ADVERTISE_HOST = Get-LanIP
}

if (-not $env:WORKER_ADVERTISE_HOST) {
    Write-Host "ERROR: Could not auto-detect this worker's LAN IP." -ForegroundColor Red
    Write-Host "Set WORKER_ADVERTISE_HOST in .env:"
    Write-Host "  WORKER_ADVERTISE_HOST=192.168.1.20"
    exit 1
}

# ── Start ─────────────────────────────────────────────────────────────────────
Write-Host "Starting worker container" -ForegroundColor Green
Write-Host "Master:    $($env:MASTER_HTTP_URL)"
Write-Host "Worker IP: $($env:WORKER_ADVERTISE_HOST)"
Write-Host ""

Set-Location $RootDir
docker compose -f docker-compose.worker.yml up --build
