param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$')]
    [string]$Version
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-Utf8NoBom {
    param(
        [string]$Path,
        [string]$Content
    )

    [System.IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

function Replace-FirstVersionField {
    param(
        [string]$Path,
        [string]$Pattern,
        [string]$Replacement
    )

    $content = Get-Content -LiteralPath $Path -Raw
    $regex = [regex]::new($Pattern)
    if (-not $regex.IsMatch($content)) {
        throw "Could not find a version field in $Path"
    }
    $updated = $regex.Replace($content, $Replacement, 1)
    Write-Utf8NoBom $Path $updated
}

# Keep the package, lockfile, Tauri bundle, and Rust crate versions aligned.
Replace-FirstVersionField (Join-Path $repoRoot "frontend\package.json") '("version"\s*:\s*")[^"]+("\s*,)' ('${1}' + $Version + '${2}')

$lockPath = Join-Path $repoRoot "frontend\package-lock.json"
$lockContent = Get-Content -LiteralPath $lockPath -Raw
$lockMatches = 0
$lockUpdated = [regex]::Replace($lockContent, '("version"\s*:\s*")[^"]+("\s*[,}])', {
        param($match)
        if ($script:lockMatches -lt 2) {
            $script:lockMatches++
            return $match.Groups[1].Value + $Version + $match.Groups[2].Value
        }
        return $match.Value
    })
if ($lockMatches -ne 2) {
    throw "Expected package-lock.json to contain the root and package version fields"
}
Write-Utf8NoBom $lockPath $lockUpdated

Replace-FirstVersionField (Join-Path $repoRoot "frontend\src-tauri\tauri.conf.json") '("version"\s*:\s*")[^"]+("\s*,)' ('${1}' + $Version + '${2}')
Replace-FirstVersionField (Join-Path $repoRoot "frontend\src-tauri\Cargo.toml") '(?m)^version\s*=\s*"[^"]+"' ('version = "' + $Version + '"')

# Sync backend updater.py and Inno Setup installer version
Replace-FirstVersionField (Join-Path $repoRoot "backend\app\routes\updater.py") '(CURRENT_VERSION\s*=\s*")[^"]+(")' ('${1}' + $Version + '${2}')

$installerPath = Join-Path $repoRoot "deploy\installer.iss"
if (Test-Path $installerPath) {
    Replace-FirstVersionField $installerPath '(#define MyAppVersion\s+")[^"]+(")' ('${1}' + $Version + '${2}')
}

Write-Host "Houmi Studio version set to $Version across all 6 configuration files!"
