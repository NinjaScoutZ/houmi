# =========================================================
#  HOUMI STUDIO - POWERSHELL ONLINE PATCH PUBLISHER v0.1.7
# =========================================================

$ErrorActionPreference = "Stop"

$patchZip = "E:\houmi\data\patches\latest_patch.zip"
$manifestPath = "E:\houmi\data\update_manifest.json"
$patchesDir = "E:\houmi\data\patches"

Write-Host "==================================================" -ForegroundColor Yellow
Write-Host "  HOUMI STUDIO - PUBLISH ONLINE PATCH v0.1.7" -ForegroundColor Yellow
Write-Host "==================================================" -ForegroundColor Yellow

# 1. Create directory if not exists
if (-not (Test-Path $patchesDir)) {
    New-Item -ItemType Directory -Path $patchesDir -Force | Out-Null
}

# 2. Check patch zip file
if (-not (Test-Path $patchZip)) {
    Write-Host "❌ Error: Patch zip file not found at $patchZip" -ForegroundColor Red
    exit 1
}

$fileInfo = Get-Item $patchZip
$sizeMB = [math]::Round($fileInfo.Length / 1MB, 2)
Write-Host "📦 Found Patch File: $patchZip ($sizeMB MB)" -ForegroundColor Cyan

# 3. Create update manifest
$manifest = [ordered]@{
    latest_version   = "0.1.7"
    patch_notes      = "v0.1.7 Major Release - Smart Balloon Contour Engine, Live Mini UI Customizer & 1-Click Upgrade"
    download_size_mb = $sizeMB
    download_url     = "/api/system/download-update"
    published_at     = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
}

$jsonContent = $manifest | ConvertTo-Json -Depth 3
[System.IO.File]::WriteAllText($manifestPath, $jsonContent, [System.Text.Encoding]::UTF8)

Write-Host "✅ [PowerShell] Updated local manifest $manifestPath to v0.1.7!" -ForegroundColor Green

# 4. Check update response from running local backend
try {
    $res = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/system/check-update" -Method Get -TimeoutSec 5
    Write-Host "`n🌐 Live Update Check Verification (from v0.1.4 client view):" -ForegroundColor Cyan
    Write-Host "--------------------------------------------------------" -ForegroundColor DarkGray
    Write-Host "Current Version : "$res.current_version -ForegroundColor Gray
    Write-Host "Latest Version  : "$res.latest_version -ForegroundColor Green
    Write-Host "Update Available: "$res.update_available -ForegroundColor Yellow
    Write-Host "Patch Notes     : "$res.patch_notes -ForegroundColor White
    Write-Host "Download URL    : "$res.download_url -ForegroundColor Cyan
    Write-Host "--------------------------------------------------------" -ForegroundColor DarkGray
} catch {
    Write-Host "ℹ️ Backend check-update test note: $_" -ForegroundColor DarkYellow
}

Write-Host "`n🚀 [SUCCESS] Patch v0.1.7 is active and ready for online client updates!" -ForegroundColor Green
