# Houmi Studio Patch Release

## What is supported

The desktop client has a Tauri updater integration and displays its SemVer
version in the UI. A production Patch is a signed Tauri update bundle (the
Windows updater artifact is a signed `.nsis.zip`), not an unsigned executable
download. The client verifies the signature before installation and relaunches
after a successful update.

The normal installer build keeps updater artifacts disabled until release
credentials and a HTTPS endpoint are configured. This prevents a developer
build from accidentally shipping a non-functional or unsigned updater.

## First-time release setup

1. Generate a Tauri signing key once and store the private key outside this
   repository. Never put the private key in git, `.env`, a ticket, or a chat.
2. Put the generated public key in the release environment as
   `HOUMI_UPDATES_PUBKEY`.
3. Set `HOUMI_UPDATES_ENDPOINT` to a HTTPS static JSON URL or compatible
   update server. Do not use the raw `http://192.168.x.x` address or an
   unsecured public HTTP endpoint.
4. Set `TAURI_SIGNING_PRIVATE_KEY` to the private-key path/content expected by
   the Tauri CLI, and set `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` when applicable.

## Build a Patch

Use a SemVer patch version and keep all four version locations synchronized:

```powershell
.\deploy\set-version.ps1 -Version 0.1.1
$env:HOUMI_UPDATES_PUBKEY = '<public-key-content>'
$env:HOUMI_UPDATES_ENDPOINT = 'https://releases.example.invalid/houmi/latest.json'
$env:TAURI_SIGNING_PRIVATE_KEY = 'C:\secure\houmi-studio.key'
.\deploy\build-patch.ps1
```

The build produces the normal NSIS/MSI installers plus signed updater
artifacts. The private key is read only from the process environment by the
Tauri CLI; `build-patch.ps1` writes a temporary config containing only the
public key and endpoint, then removes it.

## Static manifest shape

Publish the generated `.nsis.zip` and its `.sig`, then publish a JSON similar
to this at `HOUMI_UPDATES_ENDPOINT`:

```json
{
  "version": "0.1.1",
  "notes": "Fixes text layout and offline project loading.",
  "pub_date": "2026-08-04T12:00:00Z",
  "platforms": {
    "windows-x86_64": {
      "url": "https://releases.example.invalid/houmi/Houmi-Studio_0.1.1_x64-setup.nsis.zip",
      "signature": "<contents of the generated .sig file>"
    }
  }
}
```

The signature field is the text inside the `.sig` file, not a URL to that
file. Keep the manifest and update bundle on HTTPS. Test the installed
previous version before announcing the release.

## Rollback and key safety

The default updater accepts only a version greater than the installed version.
If a bad Patch is published, ship a higher corrective Patch; do not delete or
replace the signing key. Losing the private key prevents existing installs
from accepting future updates.
