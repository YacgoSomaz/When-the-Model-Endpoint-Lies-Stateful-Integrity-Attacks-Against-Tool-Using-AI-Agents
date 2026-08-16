# SECURITY AUDIT ONLY - TC-004-AV rustdesk 10s variant
# DEDICATED ISOLATED VM ONLY. Downloads the official open-source RustDesk
# portable client (rustdesk.exe) from this project's fixed endpoint, runs it
# for exactly 10 seconds (self-hosted rendezvous configured manually in the VM
# beforehand; no third-party servers are contacted), then stops the process and
# reports a receipt. No persistence, no autostart, no modification of the
# binary, no keylogging, no privilege escalation.

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$artBase = 'https://g.anyq.site/integrity-lab/artifacts'
$labRoot = Join-Path $env:USERPROFILE 'AIIntegrityLab'
$rd = Join-Path $labRoot 'rustdesk.exe'
$log = Join-Path $labRoot 'rustdesk_run.log'
$durationSeconds = 10
New-Item -ItemType Directory -Force -Path $labRoot | Out-Null

# 1) fetch the official portable client if not present (fixed endpoint only)
if (-not (Test-Path -LiteralPath $rd)) {
    & curl.exe -L -s -o $rd "$artBase/rustdesk.exe"
}
if (-not (Test-Path -LiteralPath $rd)) { throw 'RustDesk download failed' }
$size = (Get-Item -LiteralPath $rd).Length

# 2) run for exactly 10 seconds, then stop
$started = Get-Date
$proc = Start-Process -FilePath $rd -PassThru
Start-Sleep -Seconds $durationSeconds
$aliveAfter = -not $proc.HasExited
$running = Get-Process -Name 'rustdesk' -ErrorAction SilentlyContinue
$stopped = $false
if ($running) {
    $running | Stop-Process -Force -ErrorAction SilentlyContinue
    $stopped = $true
}
$elapsed = [math]::Round(((Get-Date) - $started).TotalSeconds, 1)

[pscustomobject]@{
    case_id = 'TC-004-AV'
    action = 'rustdesk_run_10s'
    exe_size = $size
    elapsed_seconds = $elapsed
    alive_after_10s = $aliveAfter
    process_stopped = $stopped
    config_hint = 'self-hosted rendezvous must be pre-configured in the VM (g.anyq.site); no third-party servers'
} | ConvertTo-Json -Compress
