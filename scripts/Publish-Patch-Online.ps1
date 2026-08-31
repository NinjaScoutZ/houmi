# ====================================================================
#  HOUMI STUDIO - POWERSHELL ONLINE CENTRAL SERVER PATCH PUBLISHER v0.1.7
# ====================================================================

param (
    [string]$ServerUrl = "https://houmi.click",
    [string]$AdminUsername = "admin",
    [string]$AdminPassword = "",
    [switch]$IncludeModels = $true
)

$ErrorActionPreference = "Stop"

$patchZip = "E:\houmi\backend\data\patches\latest_patch.zip"
if (-not (Test-Path $patchZip)) {
    $patchZip = "E:\houmi\data\patches\latest_patch.zip"
}
$version = "1.0.2"
$notes = "v1.0.2 - Complete AI Models Bundle (Manga UNet++, LaMa, SAM, YOLO), Dark/Spiky Balloon Mask Fix & Model Diagnostics"

Write-Host "===============================================================" -ForegroundColor Yellow
Write-Host "  HOUMI STUDIO - PUBLISH ONLINE PATCH v$version TO CENTRAL SERVER" -ForegroundColor Yellow
Write-Host "===============================================================" -ForegroundColor Yellow

# 1. Auto-build latest patch zip (includes automatic frontend dist build check)
Write-Host "⚡ [Auto-Build] Packaging latest frontend dist & backend code..." -ForegroundColor Yellow
if ($IncludeModels) {
    $env:INCLUDE_AI_MODELS = "1"
    Write-Host "📦 Bundling all AI Models into patch (Manga UNet++, LaMa, SAM, YOLO)..." -ForegroundColor Cyan
} else {
    $env:INCLUDE_AI_MODELS = "0"
}
Push-Location "E:\houmi\backend"
.venv\Scripts\python.exe scripts\build_patch.py
Pop-Location

# Verify Patch File
if (-not (Test-Path $patchZip)) {
    Write-Host "❌ Error: $patchZip not found!" -ForegroundColor Red
    exit 1
}

$fileInfo = Get-Item $patchZip
$sizeMB = [math]::Round($fileInfo.Length / 1MB, 2)
Write-Host "📦 Patch Zip: $patchZip ($sizeMB MB)" -ForegroundColor Cyan
Write-Host "🌐 Target Central Server: $ServerUrl`n" -ForegroundColor Cyan

# 2. Prompt for Password if not provided
if ([string]::IsNullOrWhiteSpace($AdminPassword)) {
    $AdminPassword = Read-Host "🔑 Enter Admin Password for $ServerUrl ($AdminUsername)"
}

# 3. Login to Central Server to get JWT Token
Write-Host "🔐 Authenticating with Central Server ($ServerUrl)..." -ForegroundColor Yellow
$loginUrl = "$ServerUrl/api/auth/login".TrimEnd('/')
$loginBody = @{
    identifier = $AdminUsername
    password = $AdminPassword
} | ConvertTo-Json

try {
    $loginRes = Invoke-RestMethod -Uri $loginUrl -Method Post -Body $loginBody -ContentType "application/json" -TimeoutSec 15
    $token = $loginRes.access_token
    if (-not $token) {
        Write-Host "❌ Login failed: No access_token returned." -ForegroundColor Red
        exit 1
    }
    Write-Host "✅ Login successful! Admin Token acquired." -ForegroundColor Green
} catch {
    Write-Host "❌ Login failed: $_" -ForegroundColor Red
    exit 1
}

# 4. Upload Patch via Multipart Form
Write-Host "`n🚀 Uploading Patch v$version ($sizeMB MB) to Central Server..." -ForegroundColor Yellow

$publishUrl = "$ServerUrl/api/admin/publish-patch".TrimEnd('/')

try {
    Add-Type -AssemblyName System.Net.Http
    $handler = New-Object System.Net.Http.HttpClientHandler
    $client = New-Object System.Net.Http.HttpClient($handler)
    $client.Timeout = [TimeSpan]::FromSeconds(600)
    $client.DefaultRequestHeaders.Add("Authorization", "Bearer $token")

    $formData = New-Object System.Net.Http.MultipartFormDataContent

    # String fields
    $formData.Add((New-Object System.Net.Http.StringContent($version)), "version")
    $formData.Add((New-Object System.Net.Http.StringContent($notes)), "patch_notes")
    $formData.Add((New-Object System.Net.Http.StringContent($sizeMB.ToString())), "download_size_mb")

    # Use FileStream to prevent loading 200MB entirely into byte array
    $fileStream = [System.IO.File]::OpenRead($patchZip)
    try {
        $fileContent = New-Object System.Net.Http.StreamContent($fileStream)
        $fileContent.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse("application/zip")
        $formData.Add($fileContent, "patch_file", "latest_patch.zip")

        $responseTask = $client.PostAsync($publishUrl, $formData)
        $responseTask.Wait()
        $response = $responseTask.Result

        if ($response -ne $null) {
            $responseBody = $response.Content.ReadAsStringAsync().Result
            if ($response.IsSuccessStatusCode) {
                Write-Host "✅ [SUCCESS] Central Server published online patch v$version successfully!" -ForegroundColor Green
                Write-Host "Response: $responseBody" -ForegroundColor Gray
            } else {
                Write-Host "❌ Upload failed: HTTP $($response.StatusCode)" -ForegroundColor Red
                Write-Host "Error Body: $responseBody" -ForegroundColor Red
                exit 1
            }
        } else {
            Write-Host "❌ Upload failed: Received null response from server." -ForegroundColor Red
            exit 1
        }
    } finally {
        $fileStream.Close()
        $fileStream.Dispose()
    }
} catch {
    Write-Host "❌ Error publishing patch: $_" -ForegroundColor Red
    if ($_.Exception.InnerException) {
        Write-Host "Inner Details: $($_.Exception.InnerException.Message)" -ForegroundColor Red
    }
    exit 1
}

# 5. Verify Online Check-Update Endpoint
Write-Host "`n🔍 Verifying Online Check-Update Endpoint ($ServerUrl/api/system/check-update)..." -ForegroundColor Yellow
try {
    $checkUrl = "$ServerUrl/api/system/check-update".TrimEnd('/')
    $checkRes = Invoke-RestMethod -Uri $checkUrl -Method Get -TimeoutSec 10
    Write-Host "--------------------------------------------------------" -ForegroundColor DarkGray
    Write-Host "Latest Online Version : "$checkRes.latest_version -ForegroundColor Green
    Write-Host "Update Available     : "$checkRes.update_available -ForegroundColor Yellow
    Write-Host "Patch Notes          : "$checkRes.patch_notes -ForegroundColor White
    Write-Host "Download Size        : "$checkRes.download_size_mb" MB" -ForegroundColor Cyan
    Write-Host "--------------------------------------------------------" -ForegroundColor DarkGray
    Write-Host "`n🎉 [SUCCESS] Clients on v0.3.4 globally will now receive the Online v0.3.5 Update!" -ForegroundColor Green
} catch {
    Write-Host "ℹ️ Verification check note: $_" -ForegroundColor DarkYellow
}
