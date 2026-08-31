# Publish-Patch-v0.4.6.ps1 - Automated Publisher for v0.4.6 Hotfix Release
$ErrorActionPreference = "Stop"

Write-Host "===============================================================" -ForegroundColor Yellow
Write-Host "  HOUMI STUDIO - PUBLISH PATCH v0.4.6 HOTFIX RELEASE" -ForegroundColor Yellow
Write-Host "===============================================================" -ForegroundColor Yellow

$patchDir = "E:\houmi\data\patches"
if (-not (Test-Path $patchDir)) {
    New-Item -ItemType Directory -Path $patchDir -Force | Out-Null
}

$zipPath = Join-Path $patchDir "latest_patch.zip"
if (Test-Path $zipPath) {
    Remove-Item -Path $zipPath -Force
}

$tempZip = Join-Path $env:TEMP "houmi_patch_v0.4.6.zip"
if (Test-Path $tempZip) {
    Remove-Item -Path $tempZip -Force
}

Write-Host "📦 Creating patch archive for v0.4.6..." -ForegroundColor Cyan

# Exclude large development/virtualenv folders
$exclude = @(
    "*\.git*",
    "*\.venv*",
    "*\node_modules*",
    "*\data\*",
    "*\dist\*",
    "*\brain\*",
    "*\tmp\*",
    "*\.tempmediaStorage\*",
    "*\_codex_test_workspace_*"
)

# Zip essential codebase files
Get-ChildItem -Path "E:\houmi" -Exclude $exclude | Compress-Archive -DestinationPath $tempZip -Force

Copy-Item -Path $tempZip -Destination $zipPath -Force
Remove-Item -Path $tempZip -Force

Write-Host "✅ Patch zip published to $zipPath" -ForegroundColor Green
Write-Host "===============================================================" -ForegroundColor Yellow
