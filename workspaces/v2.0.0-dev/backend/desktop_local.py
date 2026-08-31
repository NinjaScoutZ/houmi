"""Entry point for the offline desktop Local Engine sidecar.

The Tauri shell starts this executable on loopback.  It deliberately uses the
existing local FastAPI runtime and SQLite database so the desktop app and the
developer workflow share the same API contract.
"""

from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(description="Houmi offline Local Engine")
    parser.add_argument("--host", default=os.environ.get("HOUMI_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("HOUMI_PORT", "4317")))
    args = parser.parse_args()

    os.environ.setdefault("HOUMI_RUNTIME_MODE", "local")
    os.environ.setdefault("HOUMI_HOST", args.host)
    os.environ.setdefault("HOUMI_PORT", str(args.port))
    os.environ.setdefault("HOUMI_AUTO_CREATE_SCHEMA", "1")

    import uvicorn

    uvicorn.run("app.main:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
