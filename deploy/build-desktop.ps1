param(
    [switch]$SkipSidecar,
    [switch]$IncludeModels
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location (Join-Path $repoRoot "frontend")
try {
    npm install
    npm run build
    if (-not $SkipSidecar) {
        $sidecarArgs = @{}
        if ($IncludeModels) {
            $sidecarArgs.IncludeModels = $true
        }
        & (Join-Path $repoRoot "deploy\build-local-sidecar.ps1") @sidecarArgs
    }
    npm run tauri build
}
finally {
    Pop-Location
}
