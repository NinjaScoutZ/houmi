param(
    [switch]$SkipSidecar,
    [switch]$IncludeModels
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $repoRoot "frontend"
$configPath = Join-Path $frontendRoot "src-tauri\tauri.conf.json"
$patchConfigPath = Join-Path $frontendRoot "src-tauri\tauri.conf.patch.json"

$publicKey = [Environment]::GetEnvironmentVariable("HOUMI_UPDATES_PUBKEY")
$endpoint = [Environment]::GetEnvironmentVariable("HOUMI_UPDATES_ENDPOINT")
$privateKey = [Environment]::GetEnvironmentVariable("TAURI_SIGNING_PRIVATE_KEY")

if ([string]::IsNullOrWhiteSpace($publicKey)) {
    throw "HOUMI_UPDATES_PUBKEY is required."
}
if ([string]::IsNullOrWhiteSpace($endpoint) -or -not $endpoint.StartsWith("https://")) {
    throw "HOUMI_UPDATES_ENDPOINT must be an HTTPS static JSON or update-server endpoint."
}
if ([string]::IsNullOrWhiteSpace($privateKey)) {
    throw "TAURI_SIGNING_PRIVATE_KEY is required. Keep the private key outside the repository."
}

$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$config.bundle.createUpdaterArtifacts = $true
if (-not $config.plugins) {
    $config | Add-Member -MemberType NoteProperty -Name plugins -Value ([pscustomobject]@{})
}
if (-not $config.plugins.updater) {
    $config.plugins | Add-Member -MemberType NoteProperty -Name updater -Value ([pscustomobject]@{})
}
$config.plugins.updater | Add-Member -MemberType NoteProperty -Name pubkey -Value $publicKey -Force
$config.plugins.updater | Add-Member -MemberType NoteProperty -Name endpoints -Value @($endpoint) -Force

# The temporary config contains only the public key and endpoint. The private
# signing key is consumed by Tauri from the environment and is never written.
$config | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $patchConfigPath -Encoding UTF8
$env:HOUMI_UPDATES_ENABLED = "1"

Push-Location $frontendRoot
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
    npm run tauri -- build --config $patchConfigPath
}
finally {
    Pop-Location
    if (Test-Path -LiteralPath $patchConfigPath) {
        Remove-Item -LiteralPath $patchConfigPath -Force
    }
}
