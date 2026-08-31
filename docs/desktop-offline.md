# Houmi Desktop Offline Runtime

## Runtime model

The desktop build contains the React/Vite UI and starts a local `houmi-local`
sidecar on `127.0.0.1:4317`. The sidecar runs the existing FastAPI `local`
runtime with SQLite and local storage. No PostgreSQL, Redis, or Internet
connection is required for local project editing.

The UI detects the Tauri `tauri.localhost` origin and automatically uses the
loopback Local Engine. Browser development keeps using the Vite proxy and the
existing local port.

## Build prerequisites

- Windows 10/11 with WebView2
- Node.js and npm
- Rust toolchain and Tauri prerequisites
- Python virtual environment at `backend/.venv`
- PyInstaller available in that environment

## Build a Windows installer

From the repository root:

```powershell
.\deploy\build-desktop.ps1
```

For a frontend/Tauri configuration check without rebuilding the Python
sidecar:

```powershell
.\deploy\build-desktop.ps1 -SkipSidecar
```

For a full offline model pack (OCR/inpainting/SAM), add `-IncludeModels`.
This can add roughly 700 MB before installer compression, so the default build
keeps the model pack optional.

The build creates NSIS setup and MSI packages. The sidecar is placed under
`frontend/src-tauri/binaries` with the Rust target triple suffix required by
Tauri.

## Offline capability boundary

| Capability | Offline behavior |
|---|---|
| Open/edit/save projects | Local SQLite and local files |
| Import/export supported formats | Local Engine |
| Detection/inpainting | Requires `-IncludeModels` or a separate local model pack |
| DeepSeek OCR | Separate OCR sidecar/model package still pending in frozen desktop mode |
| GPU-heavy remote jobs | Available when Host is reachable |
| Cloud backup and multi-device sync | Requires Internet |

The current implementation establishes the Local Engine/desktop packaging
boundary and supports offline local project editing. Cloud synchronization must
be implemented as a separate, resumable outbox protocol before claiming
multi-device sync support. The packaged base engine deliberately skips the
DeepSeek OCR subprocess; distributing that OCR runtime is a separate package
because of its model/runtime size.

## Version and Patch updates

The UI shows the current SemVer build (currently `v0.1.2`) and includes a
`PATCH` check action in the Tauri desktop shell. The updater is deliberately
disabled in the normal build until a real Tauri public key, HTTPS endpoint,
and private signing key are configured. See
[release-patch.md](release-patch.md) for the signed release workflow.

Offline use does not depend on the updater: if there is no Internet connection,
local editing continues and the Patch check is skipped or reports that it is
unavailable. A Patch is a signed full update package, not an unsigned EXE
download.

## Security rules

- The sidecar binds only to loopback; never change it to `0.0.0.0`.
- Do not embed Host secrets, admin credentials, or worker keys in the client.
- Use HTTPS/WSS for remote Host communication before customer distribution.
- Store refresh credentials in OS-protected storage when the desktop auth
  integration is added.
