"""Install a checked GitHub release on a free PythonAnywhere account.

Authentication uses the provider-supplied API_TOKEN environment variable.
Credentials are not stored in the project or forwarded to the application.
No paid resources are requested; unrelated sites and directories are preserved.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen
import zipfile

PA_HOSTS = {"www.pythonanywhere.com", "eu.pythonanywhere.com"}
MAX_ARCHIVE = 50 * 1024 * 1024
MAX_UNPACKED = 100 * 1024 * 1024


def request_json(url: str, *, method="GET", data=None, token=None):
    if urlsplit(url).scheme != "https":
        raise ValueError("API requests must use HTTPS.")
    headers = {"User-Agent": "signal-assignment-deployer/1.0", "Accept": "application/json"}
    if token:
        if urlsplit(url).hostname not in PA_HOSTS:
            raise ValueError("Refusing to send the hosting token to another service.")
        headers["Authorization"] = "Token " + token
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = Request(url, method=method, headers=headers,
                  data=json.dumps(data).encode() if data is not None else None)
    with urlopen(req, timeout=40) as response:
        raw = response.read()
        return json.loads(raw) if raw else {}


def download(url: str, target: Path, limit=MAX_ARCHIVE):
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname != "github.com":
        raise ValueError("Expected an HTTPS GitHub release download URL.")
    req = Request(url, headers={"User-Agent": "signal-assignment-deployer/1.0"})
    with urlopen(req, timeout=90) as response, target.open("wb") as output:
        size = 0
        while chunk := response.read(64 * 1024):
            size += len(chunk)
            if size > limit:
                raise ValueError("Release download exceeds the size limit.")
            output.write(chunk)


def validate_archive(archive: Path):
    with zipfile.ZipFile(archive) as z:
        if sum(item.file_size for item in z.infolist()) > MAX_UNPACKED:
            raise ValueError("Archive is larger than the allowed unpacked size.")
        names = set()
        for item in z.infolist():
            name = PurePosixPath(item.filename)
            if (name.is_absolute() or ".." in name.parts or "\\" in item.filename
                    or not name.parts or name.parts[0] != "signal-clone"):
                raise ValueError("Archive contains an unsafe path.")
            if stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError("Archive contains a symbolic link.")
            if item.filename in names:
                raise ValueError("Archive contains duplicate file paths.")
            names.add(item.filename)
        required = {"signal-clone/backend/app/main.py", "signal-clone/frontend/out/index.html",
                    "signal-clone/scripts/run_pythonanywhere.py", "signal-clone/build-manifest.json"}
        if not required <= names:
            raise ValueError("Release is missing part of the runnable application.")
        return json.loads(z.read("signal-clone/build-manifest.json"))


def hosting_identity(env=None, username=None):
    env = os.environ if env is None else env
    token = env.get("API_TOKEN", "")
    if not token:
        raise RuntimeError("Open Account > API token > Create a new API token, then open a NEW Bash console and rerun this command. Do not paste the token here.")
    host = env.get("PYTHONANYWHERE_SITE", "www.pythonanywhere.com")
    if host not in PA_HOSTS:
        raise RuntimeError("Run this script inside PythonAnywhere's Bash console.")
    username = username or env.get("PYTHONANYWHERE_USERNAME") or getpass.getuser()
    if not re.fullmatch(r"[A-Za-z0-9-]+", username):
        raise ValueError("Unexpected PythonAnywhere account name.")
    suffix = "eu.pythonanywhere.com" if host.startswith("eu.") else "pythonanywhere.com"
    return host, username, f"{username}.{suffix}", token


def find_python():
    for name in ("python3.13", "python3.12", "python3.11", "python3"):
        path = shutil.which(name)
        if path and subprocess.run([path, "-c", "import sys; sys.exit(sys.version_info < (3, 11))"], capture_output=True).returncode == 0:
            return path
    raise RuntimeError("Python 3.11 or newer is needed on the hosting account.")


def wait_for_release(repo: str, attempts=40):
    # Pin this deployment to the current source rather than silently deploying
    # an older 'latest' release while a newer build is still running.
    metadata = request_json(f"https://api.github.com/repos/{repo}")
    branch = quote(metadata["default_branch"], safe="")
    head = request_json(f"https://api.github.com/repos/{repo}/commits/{branch}")["sha"]
    url = f"https://api.github.com/repos/{repo}/releases/tags/deploy-{head}"
    for attempt in range(attempts):
        try:
            release = request_json(url)
            assets = {a["name"]: a["browser_download_url"] for a in release.get("assets", [])}
            if {"signal-hosting.zip", "signal-hosting.sha256"} <= assets.keys():
                return head, assets
        except HTTPError as error:
            if error.code != 404:
                raise
        print("GitHub is building/testing the app; checking for its verified release...", flush=True)
        time.sleep(15)
    raise RuntimeError(f"The hosting build is not available. Open https://github.com/{repo}/actions and check the workflow. Rerun this command once it is green.")


def wait_for_site(origin: str):
    for attempt in range(60):
        try:
            if request_json(origin + "/api/health").get("status") == "ok":
                return
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
            pass
        time.sleep(3)
    raise RuntimeError("The service did not become healthy. Check the account's server/error logs; no paid fallback was created.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="Public GitHub owner/repository")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repo):
        raise ValueError("Use an owner/repository name, not a URL.")
    host, username, domain, token = hosting_identity()
    origin = f"https://{domain}"
    api = f"https://{host}/api/v1/user/{username}"
    home = Path.home()
    runtime = home / "signal-clone-runtime"
    marker = runtime / "deploy-state.json"
    if runtime.exists():
        if not marker.is_file() or json.loads(marker.read_text()).get("repository") != args.repo:
            raise RuntimeError("signal-clone-runtime already exists and is not owned by this deployment. Nothing was overwritten.")
    python = runtime / ".venv/bin/python"
    command = " ".join(shlex.quote(str(value)) for value in [python, runtime / "scripts/run_pythonanywhere.py", "--domain", domain])
    try:
        existing = request_json(f"{api}/websites/{domain}/", token=token)
    except HTTPError as error:
        if error.code != 404:
            raise
        existing = None
    if existing and existing.get("webapp", {}).get("command") != command:
        raise RuntimeError("This account already hosts a different app. The script will not replace it. Use an empty free account.")

    print("Preparing the free hosting deployment. No paid resources will be requested.", flush=True)
    commit, assets = wait_for_release(args.repo)
    with tempfile.TemporaryDirectory(prefix="signal-release-") as tmp:
        temp = Path(tmp)
        archive, checksums = temp / "runtime.zip", temp / "runtime.sha256"
        download(assets["signal-hosting.zip"], archive)
        download(assets["signal-hosting.sha256"], checksums, limit=1024)
        expected = checksums.read_text().split()[0]
        if not re.fullmatch(r"[a-f0-9]{64}", expected) or hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
            raise ValueError("Hosting archive checksum verification failed.")
        manifest = validate_archive(archive)
        if manifest.get("commit") != commit or manifest.get("repository") != args.repo:
            raise ValueError("The hosting build does not match this repository and commit.")
        with zipfile.ZipFile(archive) as z:
            z.extractall(temp / "unpacked")
        runtime.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({"repository": args.repo, "commit": commit, "domain": domain}))
        shutil.copytree(temp / "unpacked/signal-clone", runtime, dirs_exist_ok=True)

    if not python.is_file():
        subprocess.run([find_python(), "-m", "venv", str(runtime / ".venv")], check=True)
    subprocess.run([str(python), "-m", "pip", "install", "--no-cache-dir", "--disable-pip-version-check",
                    "-r", str(runtime / "backend/requirements.txt")], check=True)

    if existing:
        if not existing.get("enabled"):
            request_json(f"{api}/websites/{domain}/", method="PATCH", data={"enabled": True}, token=token)
        request_json(f"{api}/websites/{domain}/reload", method="POST", token=token)
    else:
        request_json(f"{api}/websites/", method="POST", token=token, data={
            "domain_name": domain, "enabled": True, "webapp": {"command": command},
        })
    wait_for_site(origin)
    # Do not pass the account-management token to application checks.
    clean_env = dict(os.environ)
    clean_env.pop("API_TOKEN", None)
    probe = runtime / "hosting-probe.json"
    subprocess.run([str(python), str(runtime / "scripts/smoke_hosted.py"), origin,
                    "--save-probe", str(probe)], check=True, env=clean_env)
    request_json(f"{api}/websites/{domain}/reload", method="POST", token=token)
    time.sleep(3)
    wait_for_site(origin)
    subprocess.run([str(python), str(runtime / "scripts/smoke_hosted.py"), origin,
                    "--verify-probe", str(probe)], check=True, env=clean_env)
    receipt = {"repository": f"https://github.com/{args.repo}", "live_url": origin,
               "source_commit": commit, "http_websocket_and_reload_checks": "passed"}
    (runtime / "deployment-status.json").write_text(json.dumps(receipt, indent=2))
    print("\nDEPLOYMENT VERIFIED")
    print("Repository: " + receipt["repository"])
    print("Application: " + origin)
    print("Demo: alex or maya / code 123456")
    print("Free-tier website expiry is managed by the hosting account.")


if __name__ == "__main__":
    try:
        main()
    except HTTPError as error:
        print(f"\nSTOPPED: hosting/download request returned HTTP {error.code}. No paid fallback was requested.", file=sys.stderr)
        if error.code in {400, 403, 409}:
            print("Check the account's free website allowance and whether another website already uses its domain.", file=sys.stderr)
        sys.exit(1)
    except (RuntimeError, ValueError, URLError, subprocess.CalledProcessError) as error:
        print(f"\nSTOPPED: {error}\nNo paid fallback was requested.", file=sys.stderr)
        sys.exit(1)
