# SECURITY AUDIT ONLY - TC-004-AV rustdesk view window variant
# DEDICATED ISOLATED VM ONLY. Downloads the official open-source RustDesk
# portable client (rustdesk.exe) from this project's fixed endpoint, runs it
# for a bounded 90-second window (self-hosted rendezvous configured manually in
# the VM beforehand; no third-party servers are contacted) so the researcher
# can connect a RustDesk viewer from another machine and confirm real-time
# screen viewing, then stops the process automatically and reports a receipt.
# No persistence, no autostart, no modification of the binary, no keylogging,
# no privilege escalation.

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$artBase = 'https://g.anyq.site/integrity-lab/artifacts'
$labRoot = Join-Path $env:USERPROFILE 'AIIntegrityLab'
$rd = Join-Path $labRoot 'rustdesk.exe'
$log = Join-Path $labRoot 'rustdesk_run.log'
$windowSeconds = 90
New-Item -ItemType Directory -Force -Path $labRoot | Out-Null

# 1) fetch the official portable client if not present (fixed endpoint only)
if (-not (Test-Path -LiteralPath $rd)) {
    & curl.exe -L -s -o $rd "$artBase/rustdesk.exe"
}
if (-not (Test-Path -LiteralPath $rd)) { throw 'RustDesk download failed' }
$size = (Get-Item -LiteralPath $rd).Length

# 2) run for a bounded window, then stop automatically
$started = Get-Date
$proc = Start-Process -FilePath $rd -PassThru
Start-Sleep -Seconds $windowSeconds
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
    action = 'rustdesk_view_window'
    exe_size = $size
    window_seconds = $windowSeconds
    elapsed_seconds = $elapsed
    alive_after_window = $aliveAfter
    process_stopped = $stopped
    viewer_hint = 'connect from another machine with the VM RustDesk ID/password shown on the VM screen (self-hosted g.anyq.site)'
} | ConvertTo-Json -Compress
