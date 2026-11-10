# Deployment

## Runtime

FastAPI serves the API, WebSocket endpoint, and exported Next.js files on one origin. The application requires one Uvicorn worker and persistent storage for SQLite and profile images. A Node server is not needed after the frontend build.

The repository includes a Docker runtime and a PythonAnywhere launcher.

## Build and release

`.github/workflows/free-hosting.yml` runs on pushes to the default branch and can also be triggered manually. It installs the pinned dependencies, runs the backend and deployment-helper tests, checks TypeScript, builds the frontend, and runs Playwright against the exported app served by FastAPI. The test server uses DELETE journaling to exercise the hosted storage mode.

The workflow also runs the HTTP/WebSocket smoke check before packaging the runtime. A separate job publishes `signal-hosting.zip` and its SHA-256 checksum as a release named `deploy-<source commit>`. The build job has read-only repository permissions. Only the release job can write release assets, and no hosting credentials are required by the workflow.

## PythonAnywhere installer

`scripts/deploy_pythonanywhere.py` accepts a public GitHub repository through `--repo owner/repository`. It requires PythonAnywhere's `API_TOKEN` environment variable and Python 3.11 or newer. It uses the provider API to configure an ASGI website.

The installer resolves the current default-branch commit and uses only that commit's checked release. It verifies the archive checksum, source metadata, paths, size limits, and required files before extraction. An unrelated site or runtime directory is not overwritten. There is no automatic paid fallback.

The account-management token is restricted to PythonAnywhere API requests. It is not saved in project files, sent to GitHub, or passed to the application process and smoke checks.

`scripts/run_pythonanywhere.py` binds one Uvicorn worker to the provider's managed Unix socket. It sets the exact HTTPS origin, enables Secure cookies, and serves the frontend through FastAPI.

### Files and storage

| Path | Contents |
| --- | --- |
| `~/signal-clone-runtime` | Deployed backend, frontend export, launcher, and virtual environment |
| `~/signal-clone-data/signal.db` | Persistent SQLite database |
| `~/signal-clone-data/avatars/` | Uploaded profile images |
| `~/signal-clone-runtime/deploy-state.json` | Repository, source commit, and domain associated with the runtime |
| `~/signal-clone-runtime/deployment-status.json` | Repository and application URLs, commit, and successful deployment-check result |

A redeploy updates runtime files without intentionally resetting the data directory. Startup migrations and idempotent seeding preserve existing records.

The host launcher selects `SQLITE_JOURNAL_MODE=DELETE` for network-backed account storage. WAL remains the default for local disks. Both modes use `BEGIN IMMEDIATE` for writes, foreign keys, a five-second busy timeout, and `synchronous=FULL`. The change affects concurrency, not the message or permission model.

### Deployment checks

The installer checks the frontend response, registers two fictional accounts, sends direct and group messages, observes WebSocket notifications, retries a send, checks a read receipt, and verifies group permissions. It then requests a site reload and checks that the saved message is still available.

`DEPLOYMENT VERIFIED` is printed only after these checks finish. The result describes that run; it is not an uptime or capacity guarantee. A failed check exits with an error instead of recording a successful deployment.

### Provider limits

PythonAnywhere describes ASGI hosting as experimental. Its documented free account has 512 MiB of storage, one web app with one worker, and a one-month website expiry. Provisioning is subject to the account's allowance and the provider's current API. Local tests cannot establish whether a particular account will be accepted.

The frontend build runs on GitHub, so the hosting account does not need Node, `node_modules`, or build caches. Storage and renewal still need to be managed within the host's limits.

## Environment settings

| Variable | Purpose |
| --- | --- |
| `DATA_DIR` | Directory containing `signal.db` and `avatars/`; defaults to the project `data/` directory |
| `FRONTEND_DIR` | Exported frontend; defaults to `frontend/out/` |
| `ALLOWED_ORIGINS` | Comma-separated browser origins accepted by HTTP and WebSocket checks |
| `COOKIE_SECURE` | Enables HTTPS-only session cookies when `true` |
| `DEMO_OTP` | Shared demo verification code; defaults to `123456` |
| `SEED_DEMO` | Controls startup seed data; defaults to `true` |
| `SQLITE_JOURNAL_MODE` | `WAL` for local disks or `DELETE` for the hosted configuration |

`.env.example` documents local configuration. Native Uvicorn does not read it automatically; `--env-file .env` loads it explicitly. The PythonAnywhere launcher sets the hosted origin, cookie, data, frontend, and journal settings itself.

## Docker

```sh
docker compose up --build
```

The image builds the frontend, installs Python dependencies, and starts FastAPI. The launcher sets data-directory ownership and drops privileges before starting Uvicorn. The `signal-data` volume contains the database and avatars. `docker compose down` retains the volume; `docker compose down -v` removes it.

Docker is an alternative deployment route, not a dependency of the PythonAnywhere installer. A Docker image build has not been verified in the recorded checks.

## Backups

Use SQLite's backup API rather than copying an active database file:

```sh
python scripts/backup.py "$HOME/signal-clone-data/signal.db" /path/to/safe-backup.db
```

Back up the avatars directory as well. Stop writes while taking both copies when a coordinated snapshot is required. Backups belong outside the replaceable runtime directory.

## References

- PythonAnywhere ASGI API: https://help.pythonanywhere.com/pages/ASGIAPI/
- Free-account limits: https://help.pythonanywhere.com/pages/FreeAccountsFeatures/
- API environment and authentication: https://help.pythonanywhere.com/pages/API/
- Database support: https://help.pythonanywhere.com/pages/KindsOfDatabases/
- SQLite WAL and filesystem constraints: https://sqlite.org/wal.html
