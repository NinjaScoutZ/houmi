param(
    [string]$Python = "backend\.venv\Scripts\python.exe",
    [string]$TargetTriple = "",
    [switch]$IncludeModels
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $repoRoot $Python
$stagingDir = Join-Path $repoRoot "frontend\src-tauri\binaries"
$buildDir = Join-Path $repoRoot "_build\houmi-local"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Python environment not found: $pythonPath"
}

if (-not $TargetTriple) {
    $rustInfo = & rustc -Vv
    $TargetTriple = ($rustInfo | Select-String "^host:").Line.Split(" ")[1]
}

New-Item -ItemType Directory -Force -Path $stagingDir | Out-Null
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null

# Never let a failed build leave an older sidecar that looks valid to Tauri.
$staleSource = Join-Path $buildDir "houmi-local.exe"
$staleDestination = Join-Path $stagingDir "houmi-local-$TargetTriple.exe"
Remove-Item -LiteralPath $staleSource,$staleDestination -Force -ErrorAction SilentlyContinue

$pyinstallerArgs = @(
    "--noconfirm",
    "--clean",
    "--onefile",
    "--name", "houmi-local",
    "--distpath", $buildDir,
    "--workpath", (Join-Path $buildDir "work"),
    "--specpath", $buildDir,
    "--paths", (Join-Path $repoRoot "backend"),
    "--hidden-import", "app.main",
    "--collect-data", "rapidocr_onnxruntime",
    "--collect-data", "pythainlp",
    "--copy-metadata", "rapidocr_onnxruntime",
    # These optional training/Paddle stacks are loaded lazily by features that
    # are not part of the base local editor. Keeping them out makes the
    # customer shell build practical; the model pack remains optional.
    "--exclude-module", "paddle",
    "--exclude-module", "paddlex",
    "--exclude-module", "modelscope",
    "--exclude-module", "torch",
    "--exclude-module", "torchvision",
    "--exclude-module", "ultralytics",
    (Join-Path $repoRoot "backend\desktop_local.py")
)

if ($IncludeModels) {
    $pyinstallerArgs += @(
        "--add-data",
        "$(Join-Path $repoRoot 'backend\models');backend\models"
    )
}

& $pythonPath -m PyInstaller @pyinstallerArgs

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

$source = Join-Path $buildDir "houmi-local.exe"
if (-not (Test-Path -LiteralPath $source)) {
    throw "PyInstaller did not produce the expected sidecar: $source"
}
$destination = $staleDestination
Copy-Item -LiteralPath $source -Destination $destination -Force
Write-Host "Built Tauri sidecar: $destination"
