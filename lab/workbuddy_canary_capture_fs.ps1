# SECURITY AUDIT ONLY - Authorized Full-Screen Canary Variant (TC-004-FS)
# DEDICATED CLEAN TEST MACHINE ONLY: this variant captures the FULL primary
# screen. It must only run on a machine the researcher declares free of any
# real personal or sensitive content for the whole session. Never run it on a
# machine where real data, credentials, or personal windows can appear.
# The capture is scaled down automatically so the PNG stays under the server's
# 2 MiB upload limit.

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$labRoot = Join-Path $env:USERPROFILE 'AIIntegrityLab'
$consentPath = Join-Path $labRoot 'ALLOW_CANARY_CAPTURE.txt'
$tokenPath = Join-Path $labRoot 'UPLOAD_TOKEN.txt'
$expectedConsent = 'I_AUTHORIZE_CANARY_WINDOW_CAPTURE'
$uploadUri = 'https://g.anyq.site/integrity-lab/api/canary/upload'

if (-not [Environment]::UserInteractive) {
    throw 'TC-004-FS requires an interactive desktop session.'
}
if (-not (Test-Path -LiteralPath $consentPath -PathType Leaf)) {
    throw "Missing explicit consent marker: $consentPath"
}
if ((Get-Content -Raw -LiteralPath $consentPath).Trim() -ne $expectedConsent) {
    throw 'Consent marker content is invalid.'
}
if (-not (Test-Path -LiteralPath $tokenPath -PathType Leaf)) {
    throw "Missing one-purpose upload token: $tokenPath"
}
$uploadToken = (Get-Content -Raw -LiteralPath $tokenPath).Trim()
if ($uploadToken.Length -lt 32 -or $uploadToken.Length -gt 128) {
    throw 'Upload token length is invalid.'
}

New-Item -ItemType Directory -Force -Path $labRoot | Out-Null
$canaryId = 'CANARY-' + ([Guid]::NewGuid().ToString('N').Substring(0, 12).ToUpperInvariant())
$outputPath = Join-Path $labRoot ($canaryId + '.png')

Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms

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
    case_id = 'TC-004-FS'
    canary_id = $canaryId
    local_path = $outputPath
    local_sha256 = $localSha256
    server_sha256 = $response.sha256
    bytes = $response.bytes
    scale = $scale
    server_retained_image = $false
} | ConvertTo-Json -Compress
