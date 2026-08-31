# =========================================================
#  HOUMI STUDIO - POWERSHELL ONLINE PATCH PUBLISHER v0.4.5
# =========================================================

$ErrorActionPreference = "Stop"

$patchZip = "E:\houmi\backend\data\patches\latest_patch.zip"
$manifestPath = "E:\houmi\backend\data\update_manifest.json"
$rootManifestPath = "E:\houmi\data\update_manifest.json"
$patchesDir = "E:\houmi\backend\data\patches"

Write-Host "==================================================" -ForegroundColor Yellow
Write-Host "  HOUMI STUDIO - PUBLISH ONLINE PATCH v0.4.5 Release" -ForegroundColor Yellow
Write-Host "==================================================" -ForegroundColor Yellow

# 1. Create directory if not exists
if (-not (Test-Path $patchesDir)) {
    New-Item -ItemType Directory -Path $patchesDir -Force | Out-Null
}

# Auto-build latest patch zip (includes automatic frontend dist build check)
Write-Host "⚡ [Auto-Build] Packaging latest frontend dist & backend code..." -ForegroundColor Yellow
Push-Location "E:\houmi\backend"
.venv\Scripts\python.exe scripts\build_patch.py
Pop-Location

# 2. Check patch zip file
if (-not (Test-Path $patchZip)) {
    Write-Host "❌ Error: Patch zip file not found at $patchZip" -ForegroundColor Red
    exit 1
}

$fileInfo = Get-Item $patchZip
$sizeMB = [math]::Round($fileInfo.Length / 1MB, 2)
Write-Host "📦 Found Patch File: $patchZip ($sizeMB MB)" -ForegroundColor Cyan

# 3. Create update manifest for v0.4.5
$manifest = [ordered]@{
    latest_version   = "0.4.5"
    patch_notes      = "v0.4.5 Release - Dual-Slash (//) TXT Translation File Import Support"
    download_size_mb = $sizeMB
    download_url     = "/api/system/download-update"
    published_at     = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
}

$jsonContent = $manifest | ConvertTo-Json -Depth 3
[System.IO.File]::WriteAllText($manifestPath, $jsonContent, [System.Text.Encoding]::UTF8)
if (Test-Path "E:\houmi\data") {
    [System.IO.File]::WriteAllText($rootManifestPath, $jsonContent, [System.Text.Encoding]::UTF8)
}

Write-Host "✅ [PowerShell] Updated manifest files to v0.4.5!" -ForegroundColor Green

# 4. Notify dev_patch_service in backend
Push-Location "E:\houmi\backend"
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, '.'); from app.services.dev_patch_service import record_dev_patch; record_dev_patch({'is_customer_release': True, 'customer_version': '0.4.5', 'changes': [{'category': 'Added', 'description': 'Full support for importing paired // English & // Thai translation text files'}]})"
Pop-Location

Write-Host "🚀 Patch v0.4.5 published successfully!" -ForegroundColor Green
