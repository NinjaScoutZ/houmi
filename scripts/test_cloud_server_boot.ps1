# Verification script for DOBKLE Cloud Hub Server Startup
$ErrorActionPreference = "Stop"

Write-Host "🔍 Testing DOBKLE Cloud Server Pre-flight Diagnostics..." -ForegroundColor Cyan

$process = Start-Process -FilePath "python" -ArgumentList "scripts\start_cloud_hub.py --dry-run" -Wait -PassThru -NoNewWindow

if ($process.ExitCode -eq 0) {
    Write-Host "✅ Pre-flight dry-run check succeeded with Exit Code 0" -ForegroundColor Green
    Exit 0
} else {
    Write-Host "❌ Pre-flight dry-run check failed with Exit Code $($process.ExitCode)" -ForegroundColor Red
    Exit 1
}
