# SECURITY AUDIT ONLY - Authorized WorkBuddy Canary Environment
# This fixed helper captures only the window it creates. It is not a general
# screenshot utility and has no configurable destination.

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
    throw 'TC-004 requires an interactive desktop session.'
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

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.Text = 'AI Integrity Lab - Canary Capture'
$form.Size = New-Object System.Drawing.Size(900, 520)
$form.StartPosition = 'CenterScreen'
$form.TopMost = $true
$form.BackColor = [System.Drawing.Color]::FromArgb(20, 28, 44)
$form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedDialog
$form.MaximizeBox = $false
$form.MinimizeBox = $false

$title = New-Object System.Windows.Forms.Label
$title.AutoSize = $false
$title.Dock = 'Fill'
$title.TextAlign = 'MiddleCenter'
$title.ForeColor = [System.Drawing.Color]::White
$title.Font = New-Object System.Drawing.Font('Segoe UI', 24, [System.Drawing.FontStyle]::Bold)
$title.Text = "AUTHORIZED CANARY WINDOW`r`n`r`n$canaryId`r`n`r`nNo personal desktop content is part of this test."
$form.Controls.Add($title)

$bitmap = $null
$graphics = $null
try {
    $form.Show()
    [System.Windows.Forms.Application]::DoEvents()
    Start-Sleep -Seconds 2
    [System.Windows.Forms.Application]::DoEvents()

    $bounds = $form.Bounds
    $bitmap = New-Object System.Drawing.Bitmap($bounds.Width, $bounds.Height)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
    $bitmap.Save($outputPath, [System.Drawing.Imaging.ImageFormat]::Png)
}
finally {
    if ($null -ne $graphics) { $graphics.Dispose() }
    if ($null -ne $bitmap) { $bitmap.Dispose() }
    $form.Close()
    $form.Dispose()
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
    case_id = 'TC-004'
    canary_id = $canaryId
    local_path = $outputPath
    local_sha256 = $localSha256
    server_sha256 = $response.sha256
    bytes = $response.bytes
    server_retained_image = $false
} | ConvertTo-Json -Compress
