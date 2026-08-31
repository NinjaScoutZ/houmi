$ErrorActionPreference = "Stop"

# 1. Resolve ISCC.exe path
$iscc = "iscc.exe"
if (!(Get-Command $iscc -ErrorAction SilentlyContinue)) {
    $defaultPaths = @(
        "$env:LocalAppData\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    )
    foreach ($path in $defaultPaths) {
        if (Test-Path $path) {
            $iscc = $path
            break
        }
    }
}

Write-Host "Using Inno Setup Compiler: $iscc"

# 2. Download WebView2 Bootstrapper if it doesn't exist
$deployDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$wvBootstrapper = Join-Path $deployDir "MicrosoftEdgeWebview2Setup.exe"

if (!(Test-Path $wvBootstrapper)) {
    Write-Host "Downloading Microsoft Edge WebView2 Evergreen Bootstrapper..."
    $url = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
    Invoke-WebRequest -Uri $url -OutFile $wvBootstrapper -UseBasicParsing
    Write-Host "Download complete: $wvBootstrapper"
} else {
    Write-Host "WebView2 Bootstrapper already exists: $wvBootstrapper"
}

# 3. Compile Inno Setup Script
$issScript = Join-Path $deployDir "installer.iss"
Write-Host "Compiling Inno Setup script: $issScript"

& $iscc $issScript

Write-Host "Build complete! Setup is available in: dist\HoumiStudio-Setup.exe"
