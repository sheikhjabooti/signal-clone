# Architecture decisions and implementation order

The application keeps messages, permissions, and receipts in one database, with live updates layered on top. These decisions keep the messaging flows consistent without introducing separate services for a small demo.

## 1. The shape of the application

```text
Next.js browser interface
  ├─ HTTP: read data and request saved changes
  └─ WebSocket: learn about changes; exchange typing and presence events
                         │
                  One FastAPI process
                         │
            Services and short transactions
                         │
             SQLite + uploaded profile photos
                on persistent storage
```

The frontend is exported to static files. FastAPI serves those files after registering its API and WebSocket routes. There is one browser origin in the production build, which keeps cookies and deployment simpler.

The database is authoritative. A socket event is a hint to refresh data, not proof that a client has received or read a message.

## 2. Key decisions

### One backend application, not microservices

Authentication, contacts, group administration, and messaging are separate modules inside one application. They share a database and can update related records in one transaction.

Splitting them into services would require network authentication, distributed failure handling, and a way to coordinate changes that are currently local. Nothing in the brief calls for that.

**Tradeoff:** there is one deployment and one failure domain. That is acceptable for a small demo, not a claim of high availability.

### Next.js static export, with FastAPI serving it

Most useful content appears after login and changes through requests and live updates. Request-time HTML rendering would not simplify those flows. Next.js still provides routing, TypeScript integration, bundling, and a component structure.

The application uses fixed routes and a conversation query parameter, such as `/chat/?conversation=12`. The exported pages contain no private messages or session tokens. FastAPI decides whether each data request is allowed.

**Alternative considered:** a separate Next.js server and Python API. That works, but adds another service and cross-origin configuration without a clear benefit here.

**Limit:** runtime Server Actions and server-rendered authenticated pages are outside this export setup.

### HTTP for saved operations; WebSockets for live notifications

Sending a message is an HTTP POST. Creating groups, changing membership, and acknowledging receipts also use HTTP. Their success and error responses are easy to inspect and retry.

The socket carries small notifications such as `message.new`, `receipt.changed`, and `membership.changed`. These contain IDs rather than message bodies. Clients fetch the current, authorized records through the API. Typing is sent directly over the socket because it is temporary.

**HTTP rather than an all-WebSocket API:** saved operations need request/response matching, validation errors, and retry behaviour. HTTP already provides a straightforward place for those rules.

**Why not SSE?** SSE plus HTTP could work. WebSockets give typing and other two-way activity a single live channel. This is a choice, not a claim that SSE cannot support chat.

**Tradeoff:** a new-message notification causes an HTTP read. That costs an extra request but centralizes authorization and serialization. Notification bursts are debounced.

### SQLite with explicit, short write transactions

SQLite is required by the assignment. WAL mode allows readers to continue while a writer works, but it does not turn SQLite into a multi-writer database. The connection setup enables foreign keys, a five-second busy timeout, and `synchronous=FULL`.

Every mutation opens `BEGIN IMMEDIATE` **before** checking membership or other mutable permissions. That acquires the writer slot first. Authorization and the write therefore see a consistent order relative to another mutation.

Transactions end before publishing socket events. A slow recipient never holds the database writer slot.

**Synchronous SQLAlchemy:** short service operations run through FastAPI's threadpool. Sessions stay inside those operations. Socket handling remains asynchronous. This avoids carrying database sessions across awaits and makes transaction boundaries easier to follow. It does not remove SQLite's write limit.

### One process and one worker

The live connection registry is an ordinary in-memory object. Each user's socket can only be reached by the process that owns it. Starting multiple workers without a shared event channel would make some notifications miss their recipients.

The runtime deliberately uses one Uvicorn worker. It can still manage several concurrent connections asynchronously. Restarting discards sockets, typing, and approximate presence; persisted messages and sessions remain.

**What would change first at scale?** A shared event-routing layer is needed before adding workers. A database with more write concurrency would follow if the SQLite requirement no longer applied. No throughput number is claimed without a load test.

### Opaque cookie sessions rather than JWTs

Login creates a random token. Only its hash, user ID, expiry, and CSRF token are stored in SQLite. The raw token goes into an HTTP-only cookie with SameSite=Lax; Secure is enabled for HTTPS deployment. Sessions expire after seven days.

A database-backed session gives logout a direct revocation path. There is no token-refresh protocol to explain or maintain. The backend derives the actor from this session, never from a submitted sender ID.

Mutating API requests require an allowed Origin, and authenticated writes also require the session's CSRF token. The WebSocket handshake checks Origin and the session. Heartbeats and typing packets recheck session validity.

**Important boundary:** the shared demo OTP proves no real identity. Anyone who knows a username and the displayed code can enter that account. Session and membership enforcement are implemented, but this is not production authentication.

### Separate message recipients, not one status column

A message has one row in `messages` and a recipient row for every other active member at send time. Each recipient has their own delivered and read timestamps.

This models group receipts correctly and preserves the original audience. Adding someone later does not make them a recipient of earlier messages. Removing someone does not rewrite the historical audience either.

**Tradeoff:** storage grows with messages multiplied by recipient count. Groups are bounded at 32 members in this demo. A single message status would be smaller but could not represent different recipients accurately.

### Stable IDs for ordering and retries

SQLite's increasing message ID determines ordering and history cursors. Server timestamps are for display. Message IDs use AUTOINCREMENT so deletion cannot cause an old cursor value to be reused.

The browser also creates a `client_message_id` for each send attempt. A database uniqueness constraint covers `(sender_id, client_message_id)`. A retry with the same content returns the existing message. Reusing that ID for different content, a different conversation, or a different quote returns a conflict.

This guarantees one saved row per sender/client-ID pair. It does **not** guarantee exactly-once network delivery.

### Query cache for server data; local state for interface details

TanStack Query stores cached conversations, contacts, profiles, and messages. Draft text, open dialogs, temporary typing, and pending sends stay in React state. Query keys include the account and conversation IDs.

A login/logout transition cancels requests and clears private queries while preserving the observed session query. Removing that observed query would leave the login screen stale, so the transition is covered by browser tests.

Messages merge by stable server ID. Receipt progress never moves backwards when responses arrive out of order. The pending client ID lets an HTTP response and a socket-triggered fetch resolve to one visible bubble.

**Limit:** drafts and unconfirmed sends do not survive closing the page. This is not a durable offline outbox. Successfully saved messages still return from the server after a refresh.

### Small components and shared theme variables

The interface uses scoped class names in a shared stylesheet. Shared variables control colours, borders, spacing, and light/dark themes. This keeps the two-pane layout and modal styling consistent without a UI library imposing a different visual language.

Components separate onboarding, conversation navigation, message rendering, and dialogs. Native dialogs provide focus trapping and Escape handling. Keyboard shortcuts cover search and composing.

**Limit:** the interface is a Signal-style recreation, not the official client or a pixel-for-pixel match to every Signal release.

## 3. Message lifecycle

1. The browser creates a client ID and shows a pending bubble.
2. It posts the body, client ID, and optional quoted-message ID.
3. The backend identifies the sender from the session.
4. A write transaction checks active membership, validates the quote, and checks for an existing retry ID.
5. It saves the message and the original recipient rows, then commits.
6. Only after commit does it publish an ID-only change event.
7. The sender gets the saved message in the HTTP response. Connected recipients fetch authorized message payloads.
8. Recipients acknowledge delivery. A visible, focused conversation acknowledges the specific messages displayed in its viewport as read.

A socket notification by itself does not establish delivery. A background history request does not establish reading. “Read” describes what the interface displayed; it cannot prove someone mentally processed the text.

The sender might receive a refreshed message through the socket path before their POST finishes. Stable IDs handle either ordering. If the POST commits but its response is lost, retrying the same client ID cannot create a second row.

## 4. Recovery when live delivery fails

The client connects, waits for `ready`, and synchronizes. Change events schedule another refresh, and events arriving during a refresh mark it dirty so another pass runs.

For a loaded conversation, reconciliation starts just before the earliest loaded message and fetches forward in pages. The first page establishes a fixed `through_id`; later pages use that boundary. New messages arriving during the pass cannot make pagination run forever or silently skip a range. Older history uses a separate `before_id` cursor.

This deliberately refreshes the loaded suffix, including receipts and reactions, instead of trusting the highest live ID as proof that earlier messages arrived. Stable IDs make repeated rows harmless.

Pending undelivered payloads are fetched in bounded batches. The client acknowledges only those it actually receives. A sidebar preview never counts as delivery of the whole conversation.

Reconnect, window focus, and a roughly 30-second foreground check repair missed notifications. If a process dies after commit but before publishing, the message remains in SQLite and reappears during recovery.

**Accepted limit:** there is no durable event log or transactional outbox. A missed notification can leave the UI stale until reconciliation. The tradeoff is a small recovery delay in exchange for less infrastructure.

## 5. Group rules and races

The creator is an admin. Admins can rename the group, add/remove members, and change roles. The last active admin cannot be removed or demoted.

A member can access messages they authored or were originally sent. Joining starts access to new messages; rejoining restores earlier participation, but not messages sent during the absence. The same visibility rule applies to history, previews, unread counts, and quoted-message contents.

Removal ends current server access. The removed user's connected interface clears the active conversation and disables further interaction. The server still checks permissions even if a modified browser ignores that update.

When removal and sending race, the write transaction order decides the audience. If send commits first, the person was a recipient. If removal commits first, later sends exclude them. Data already received before removal cannot be recalled.

## 6. Database map

| Table | What it records | Important rule |
| --- | --- | --- |
| users | Username, display name, avatar reference, last seen | Normalized username is unique |
| sessions | Token hash, user, expiry, CSRF token | Logout revokes a persisted session |
| contacts | One user's saved contacts | Directed relation; no self-contact |
| conversations | Direct/group metadata | One canonical direct pair |
| conversation_members | Active membership and admin role | One row per user/conversation |
| messages | Saved text, ordering ID, client ID, optional quote | Unique sender/client ID |
| message_recipients | Original audience and receipts | Read implies delivered |
| reactions | One user's reaction to a message | One reaction per user/message |

Unread counts and permitted last-message previews are derived rather than maintained as separate counters. This avoids another mutable value that could drift. The initial Alembic migration contains explicit versioned DDL, not a call to whatever today's model metadata happens to contain.

## 7. Implementation order

The main pieces were implemented in dependency order: storage and access rules first, then live updates, the interface, and deployment.

| Step | Work | Reason for the order |
| --- | --- | --- |
| 1 | Models, migration, settings, transaction helpers | Permissions and messaging depend on a clear schema |
| 2 | Demo authentication, cookie sessions, profiles, contacts | Establish the actor and usable accounts |
| 3 | Direct/group services and history visibility | Keep shared access rules in one place |
| 4 | Idempotent sends, receipts, reactions, replies | Define saved behaviour independently of transport |
| 5 | Socket registry, notifications, typing, presence | Add live updates after persistence works |
| 6 | Seed data and backend tests | Make the demo usable and exercise edge cases |
| 7 | Next.js shell, onboarding, conversation list, chat | Build the interface against the API |
| 8 | Optimistic sends, reconciliation, read observation | Keep browser state consistent with saved records |
| 9 | Group/profile/settings dialogs, themes, mobile layout | Complete the remaining workflows |
| 10 | Production build and independent browser sessions | Check integration beyond the API suite |
| 11 | Runtime packaging, launcher, backup utility, documentation | Make setup and deployment reproducible |
| 12 | Hosted journal-mode support, release workflow, deployment checks | Exercise the storage mode and runtime used by the host |

The login transition and typing throttle both needed integration fixes. Clearing the observed session query could leave the login screen stale; treating a typing rate-limit error as an expired session could log out a valid user. The implementation preserves the session query and drops excess typing events instead. The test suites cover those paths.

## 8. Deployment design

### Build on GitHub, run Python on the host

The release workflow builds the Next.js static export and runs backend, helper, TypeScript, and browser checks. It packages the exported interface with the Python backend, then publishes a release tied to the source commit. Only the release job has repository write permission.

This keeps Node and frontend build caches off the hosting account. The source repository still contains both frontend and backend code; the smaller release archive is for runtime use.

### Separate code from persistent data

PythonAnywhere runtime files live in `~/signal-clone-runtime`. SQLite and uploaded avatars live in `~/signal-clone-data`, outside the replaceable release directory. Startup applies migrations and idempotent seed data rather than recreating the database on each deploy.

The host launcher runs one Uvicorn worker on the managed Unix socket. It supplies the exact HTTPS origin, enables Secure cookies, and removes the account-management API token before starting the application.

### Journal mode follows the storage

Local disks use WAL. The PythonAnywhere launcher selects DELETE journaling for network-backed account storage, because WAL is not suitable for that filesystem arrangement. The configuration accepts only WAL or DELETE.

Both modes retain `BEGIN IMMEDIATE`, foreign keys, the busy timeout, and `synchronous=FULL`. Persistence and seed idempotency are tested in both modes. The tradeoff is reduced reader/writer concurrency on the host, without changing message visibility or permission checks.

### Validate the release and the running app

The deployment script resolves the current source commit and downloads that commit's release rather than an older latest build. It verifies the checksum and build metadata, rejects unsafe archive paths, and refuses to replace an unrelated website or runtime directory.

After provisioning, it checks two accounts, direct/group messages, live notifications, receipts, duplicate retries, and group permissions. It then requests a service reload and verifies the saved message. A deployment result is recorded only after those checks finish. The script has no paid fallback.

### Hosting boundary

PythonAnywhere's ASGI interface is beta and provisioning depends on the account's allowance. The free account has a small storage quota and a one-month website expiry. The helper tests exercise local logic, not provider acceptance or long-term availability. Account-specific results belong to the actual deployment run.

## 9. Deliberate limits

The application does not implement end-to-end encryption, real identity verification, background push delivery, a durable offline outbox, multi-process event routing, or a high-availability database. Attachments and disappearing messages are not implemented. Presence is approximate, and the process-local rate limiter resets on restart.

This is a single-instance demo. Increasing traffic or stronger availability requirements would call for shared event routing, a database with more write concurrency, and durable event publication. No throughput or availability target is claimed without measurement.

## 10. References

- Next.js static export: https://nextjs.org/docs/app/guides/static-exports
- FastAPI WebSockets: https://fastapi.tiangolo.com/advanced/websockets/
- SQLite WAL: https://sqlite.org/wal.html
- SQLite AUTOINCREMENT: https://sqlite.org/autoinc.html
- SQLAlchemy sessions: https://docs.sqlalchemy.org/en/20/orm/session_basics.html
- PythonAnywhere ASGI API: https://help.pythonanywhere.com/pages/ASGIAPI/
- PythonAnywhere free-account limits: https://help.pythonanywhere.com/pages/FreeAccountsFeatures/
