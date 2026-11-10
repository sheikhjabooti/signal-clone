"""Build a small hosting ZIP from an already-built Next.js export.

Run by GitHub Actions. No runtime database, credentials, or node_modules are
included. The public source stays in the repository; the release is a runtime.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def package(root: Path = ROOT, commit: str | None = None) -> Path:
    export = root / "frontend/out"
    if not (export / "index.html").is_file():
        raise SystemExit("Build the frontend before packaging: cd frontend && npm ci && npm run build")
    target = root / "release"
    target.mkdir(exist_ok=True)
    archive = target / "signal-hosting.zip"
    selected = [root / "backend/app", root / "backend/migrations", export]
    files = [root / "backend/requirements.txt", root / "backend/alembic.ini",
             root / "scripts/run_pythonanywhere.py", root / "scripts/smoke_hosted.py",
             root / "README.md", root / "ARCHITECTURE_AND_IMPLEMENTATION.md"]
    for folder in selected:
        files += [p for p in folder.rglob("*") if p.is_file()
                  and "__pycache__" not in p.parts and p.suffix != ".pyc"]
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted(files):
            z.write(p, "signal-clone/" + p.relative_to(root).as_posix())
        z.writestr("signal-clone/build-manifest.json", json.dumps({
            "commit": commit or os.getenv("GITHUB_SHA", "local"),
            "repository": os.getenv("GITHUB_REPOSITORY", "local"),
            "format": 1,
        }, indent=2))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (target / "signal-hosting.sha256").write_text(f"{digest}  signal-hosting.zip\n")
    print(f"Packaged {len(files)} files: {archive.name} ({archive.stat().st_size:,} bytes)")
    return archive


if __name__ == "__main__":
    package()
