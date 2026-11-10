"""Container entrypoint. Prepare persistent storage, drop root, run one worker."""
from pathlib import Path
import os
import sys


def main() -> None:
    data = Path(os.getenv("DATA_DIR", "/var/data")).resolve()
    if data == Path("/") or data == Path("/app"):
        raise SystemExit("DATA_DIR must point to a dedicated data directory.")
    data.mkdir(parents=True, exist_ok=True)
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        # A newly mounted disk can be root-owned. Do not follow links out of it.
        os.chown(data, 10001, 10001, follow_symlinks=False)
        for directory, dirs, files in os.walk(data, followlinks=False):
            for name in dirs + files:
                os.chown(Path(directory) / name, 10001, 10001, follow_symlinks=False)
        os.setgroups([])
        os.setgid(10001)
        os.setuid(10001)
    port = int(os.getenv("PORT", "8000"))
    if not 1024 <= port <= 65535:
        raise SystemExit("PORT must be between 1024 and 65535.")
    os.execv(sys.executable, [sys.executable, "-m", "uvicorn", "app.main:app",
                            "--host", "0.0.0.0", "--port", str(port), "--workers", "1"])


if __name__ == "__main__":
    main()
