# Signal Clone

**Rohan Pandey** · Scaler SDE Fullstack Assignment  
**GitHub:** `sheikhjabooti`

A web messaging app built with Next.js, FastAPI, and SQLite. The interface follows Signal Desktop's conversation list and chat pane, with direct messages, groups, receipts, and typing indicators.

This is a demo, not the official Signal app. Login uses a shared verification code, and messages are stored without end-to-end encryption. Only fictional data should be used.

## Stack

| Layer | Implementation |
| --- | --- |
| Frontend | Next.js, TypeScript, React, TanStack Query |
| Backend | Python, FastAPI, SQLAlchemy, Alembic |
| Storage | SQLite; profile images stored alongside the database |
| Live updates | WebSockets for change notifications, typing, and presence |
| Tests | pytest, unittest, and Playwright |

The Next.js frontend is exported to static files and served by FastAPI. There is no separate Node server in the deployed app.

## Local setup

### Python and Node

Use Python 3.13 and Node.js 22. From the project root:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements-dev.txt
cd frontend
npm ci
npm run build
cd ..
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --workers 1
```

On Windows, activate the environment with `.venv\Scripts\Activate.ps1` instead. The remaining commands work in PowerShell.

Open `http://127.0.0.1:8000`. Startup applies the database migration and seeds demo users, conversations, and messages. Data is stored in `data/` at the project root. The frontend must be built before starting the backend so that `frontend/out/` exists.

### Docker

Docker is an alternative to the native setup:

```sh
docker compose up --build
```

Open `http://localhost:8000`. The named `signal-data` volume holds the database and profile photos. Stopping or restarting the container preserves it; `docker compose down -v` deletes it.

### Frontend development

Run the backend, copy `frontend/.env.local.example` to `frontend/.env.local`, and run `npm run dev` inside `frontend/`. Use `http://localhost:3000` for the interface and `http://localhost:8000` for the API. Mixing `localhost` and `127.0.0.1` creates different cookie hosts.

Remove `frontend/.env.local` before a deployment build. The deployed app uses relative URLs on one origin.

## Demo accounts

The verification code is **123456**. The login screen includes shortcuts for `alex`, `maya`, and `sam`. Other seeded accounts are `priya`, `leo`, and `nina`.

To test a conversation, sign in as Alex in one browser session and Maya in an incognito window or another browser. Normal tabs share the same login cookie. Select each other's conversation and exchange messages. Switching the recipient to another chat leaves incoming messages unread; opening the chat updates receipts. Refreshing either session reloads the saved history.

Alex is an admin of the seeded groups. The creator of a new group becomes its admin. Profile settings support display-name changes, avatar uploads, and light, dark, or system appearance.

## Features

| Area | Behaviour |
| --- | --- |
| Accounts | Registration, demo verification, login/logout, persistent cookie sessions, editable profiles and avatars |
| Contacts | Add registered users; search people, contacts, and conversations |
| Direct chats | Persisted messages, optimistic sending, retry deduplication, timestamps, delivery/read receipts, typing |
| Groups | Create and rename groups, list/add/remove members, change admin roles, protect the last admin |
| Conversation list | Recent activity, last-message previews, unread counts, filters, approximate presence |
| Recovery | Reconnection, bounded history synchronization, pending delivery catch-up, foreground refresh |
| Extras | Quoted replies, six emoji reactions, themes, responsive layout, keyboard shortcuts |
| Notifications | In-app notices and optional desktop notifications while the app is open |

Calls, stories, linked devices, file attachments, and disappearing messages are not implemented. Their relevant controls show a placeholder or explain the limitation. Chat search covers loaded messages, not the entire server history. There is no background push service.

## Architecture

```text
Browser: exported Next.js interface
    |
    +-- HTTP /api/* --> FastAPI services --> SQLite
    |                                      |
    +-- WebSocket /ws <-- notifications <-- commit succeeds
```

HTTP handles saved changes and data retrieval. WebSockets notify connected clients about changes and carry typing activity. After a notification, the client fetches the current authorized records. Messages are committed before notifications are sent.

The backend runs **one process with one worker** because the socket registry is in memory. Adding workers without shared event routing would leave some clients without live updates. The database remains authoritative when a connection drops.

### Database schema

| Table | Main fields and relationships |
| --- | --- |
| `users` | Unique normalized username, display name, avatar, last seen |
| `sessions` | Token hash, user reference, CSRF token, expiry |
| `contacts` | Composite key of owner and contact user; directed relationship |
| `conversations` | Type, group name, creator, unique canonical direct-chat pair |
| `conversation_members` | Conversation/user pair, role, active flag, membership timestamps |
| `messages` | Conversation, sender, client retry ID, body, timestamp, optional quoted-message reference |
| `message_recipients` | Message/user pair with delivered and read timestamps |
| `reactions` | Message/user pair with one emoji per user |

Foreign keys and uniqueness constraints enforce the relationships. Message recipients are captured at send time, so adding a group member does not expose older messages. Unread counts and permitted previews are derived from those records. The versioned schema is in `backend/migrations/`.

[Architecture decisions and implementation order](ARCHITECTURE_AND_IMPLEMENTATION.md) covers the tradeoffs, message flow, recovery, and group-access rules.

### API

The API covers authentication, profiles, contacts, conversations, groups, messages, receipts, and reactions. Details are in [docs/API.md](docs/API.md). OpenAPI is available at `/docs` while the backend is running.

## Repository layout

```text
frontend/           Next.js interface and browser tests
backend/app/        Routes, services, models, sessions, sockets, seed data
backend/migrations/ Versioned database schema
backend/tests/      API, storage, permission, and live-event tests
scripts/            Packaging, deployment, smoke checks, startup, backups
.github/workflows/  Build, test, and release workflow
docs/               API, deployment, and testing documentation
```

## Tests

With the Python environment active:

```sh
# From the project root
python -m unittest discover -s scripts/tests -v
cd backend
python -m pytest -q

cd ../frontend
npm run typecheck
npm run build
npx playwright install chromium
npm run test:e2e
```

Playwright expects the built app running at `http://127.0.0.1:8000`. Tests create fictional users and messages, so they should use a development database. [docs/TESTING.md](docs/TESTING.md) describes coverage, setup, and verification limits.

## Deployment

The repository includes a PythonAnywhere deployment script and a Docker configuration. GitHub Actions builds and tests the app before publishing a runtime archive tied to the source commit. The PythonAnywhere installer keeps the database and avatars outside the replaceable runtime directory and runs HTTP, WebSocket, and post-reload checks.

The PythonAnywhere launcher uses SQLite's DELETE journal mode; local runs default to WAL. Both configurations use a single worker and persistent storage. [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) documents the runtime, environment settings, storage, and backups.
