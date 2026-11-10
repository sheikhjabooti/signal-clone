"""Start the single ASGI worker on PythonAnywhere's managed Unix socket."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sys


def runtime_config(root: Path, home: Path, domain: str, socket: str) -> tuple[dict[str, str], list[str]]:
    if not re.fullmatch(r"[a-zA-Z0-9-]+\.(?:eu\.)?pythonanywhere\.com", domain):
        raise ValueError("Use the free account's PythonAnywhere domain.")
    if not socket or not Path(socket).is_absolute():
        raise ValueError("PythonAnywhere must supply an absolute DOMAIN_SOCKET path.")
    data = home / "signal-clone-data"
    env = {
        "DATA_DIR": str(data),
        "FRONTEND_DIR": str(root / "frontend/out"),
        "ALLOWED_ORIGINS": f"https://{domain}",
        "COOKIE_SECURE": "true",
        "SQLITE_JOURNAL_MODE": "DELETE",
        "SEED_DEMO": "true",
        "DEMO_OTP": "123456",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
    }
    args = [sys.executable, "-m", "uvicorn", "app.main:app",
            "--app-dir", str(root / "backend"), "--uds", socket,
            "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
    return env, args


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    env, command = runtime_config(root, Path.home(), args.domain, os.getenv("DOMAIN_SOCKET", ""))
    if not (root / "frontend/out/index.html").is_file():
        raise SystemExit("The built frontend is missing. Use the GitHub hosting release.")
    Path(env["DATA_DIR"]).mkdir(parents=True, exist_ok=True)
    os.environ.update(env)
    # The running chat app does not need the account-management credential.
    os.environ.pop("API_TOKEN", None)
    os.chdir(root)
    os.execv(sys.executable, command)


if __name__ == "__main__":
    main()
