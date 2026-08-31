import subprocess
from pathlib import Path

_build_done = False

def ensure_psd_cli_built():
    """Ensures houmi-psd-cli is freshly built in release mode. Thread/run-safe in-memory cache."""
    global _build_done
    if _build_done:
        return
    
    root_dir = Path(__file__).resolve().parent.parent.parent
    cli_dir = root_dir / "houmi-psd-cli"
    if not cli_dir.exists():
        cli_dir = root_dir / "manga-psd-cli"
    binary_path = cli_dir / "target" / "release" / "houmi-psd-cli.exe"
    if not binary_path.exists():
        binary_path = cli_dir / "target" / "release" / "manga-psd-cli.exe"
    
    if binary_path.exists():
        _build_done = True
        return

    print(f"\n[TEST HELPERS] Ensuring PSD CLI is built in {cli_dir}...")
    result = subprocess.run(["cargo", "build", "--release"], cwd=cli_dir, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to build PSD CLI: {result.stderr}")
        
    if not binary_path.exists():
        raise FileNotFoundError(f"PSD CLI binary not found at {binary_path}")
        
    print("[TEST HELPERS] PSD CLI binary is ready and verified.")
    _build_done = True
