# Testing

## Test suites

The backend suite contains 53 tests using temporary on-disk SQLite databases. Storage tests exercise both WAL and DELETE journaling. The deployment-helper suite contains 19 offline tests; it does not contact a hosting account.

The frontend has seven Playwright tests against the production-exported interface served by FastAPI. They cover independent browser sessions, messaging, receipts, groups, profiles, reactions, themes, and a mobile-sized viewport. TypeScript checking and the Next.js production build are separate checks.

GitHub Actions runs these suites before publishing a runtime release. The workflow result belongs to a particular commit and should be checked alongside that release.

## Backend coverage

- Registration, normalized usernames, invalid verification codes, persisted and expired sessions.
- Origin and CSRF checks, server-derived identity, avatar validation and authenticated retrieval.
- Concurrent direct-chat creation, concurrent message retries, and conflicting reuse of a client ID.
- Delivery/read receipts, unread state, pagination, fixed catch-up boundaries, and non-reused message IDs.
- Group roles, last-admin protection, joining/rejoining history, and quoted-message visibility.
- WebSocket authentication, notifications, typing, malformed packets, and logout revocation.
- Migrations, idempotent seeding, restart persistence, journal modes, and database integrity.

Regression coverage includes a burst of typing events that must not invalidate a session. Browser tests also exercise the login transition so clearing cached private data cannot leave the interface stuck on the login screen.

## Deployment-helper coverage

The offline helper tests cover host identity, token routing, missing credentials, current-commit release selection, archive traversal, symlinks, missing built files, existing-site protection, and single-worker launcher settings. They check the packaging and deployment safeguards without creating a website.

`scripts/smoke_hosted.py` exercises a running app through HTTP and WebSockets. It creates fictional accounts, sends direct and group messages, checks receipts and duplicate retries, and verifies group permissions. A saved probe can check that the same message remains after a restart or reload.

## Running the Python checks

From the repository root, with the virtual environment active and `backend/requirements-dev.txt` installed:

```sh
python -m unittest discover -s scripts/tests -v
cd backend
python -m pytest -q
```

## Running the browser checks

Build the frontend and install Chromium:

```sh
cd frontend
npm ci
npm run typecheck
npm run build
npx playwright install chromium
```

Start the backend in another terminal, from the repository root:

```sh
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --workers 1
```

Then run `npm run test:e2e` in `frontend/`. On Linux, `npx playwright install --with-deps chromium` also installs required browser libraries when the account has the necessary system permissions.

Browser tests run serially and use distinct contexts for separate accounts. They create fictional users, groups, and messages in the running app, so the server should use a development database. Rapid repeated runs can encounter the authentication throttle; use a dedicated test server and allow the throttle window to expire between runs.

Set `E2E_BASE_URL` to test another endpoint, with its origin allowed by the backend. Screenshots and traces are written to `test-results/`, which is excluded from Git.

## Integration scenarios

A two-session check should include messages in both directions, a recipient switching away from a chat, unread counts, receipt changes, group creation, member removal, and backend restart. The removed member must lose server access, and saved messages must survive the restart. These checks apply to the hosted app as well as the local server.

The visual capture test records login, desktop, dark-mode, and narrow-layout screenshots. A mobile-sized Chromium window checks layout but does not establish compatibility with an actual phone.

## Verification limits

No large-scale load benchmark, formal accessibility audit, penetration test, or Safari/Firefox certification is recorded. The Docker configuration is included, but a Docker image build has not been verified. Offline deployment-helper tests do not establish that a provider accepted an account or that a hosted deployment succeeded; those results come from the deployment run itself.

The shared demo code and mocked encryption are deliberate limitations. There is no durable browser offline outbox, background push delivery, or exactly-once WebSocket delivery guarantee.
