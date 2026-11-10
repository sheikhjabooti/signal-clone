# API notes

All HTTP routes below have the `/api` prefix. Request and response schemas are also available at `/docs` and `/openapi.json` while the server runs.

## Sessions

`POST /auth/register` takes `username`, `display_name`, and `otp`. `POST /auth/login` takes `username` and `otp`. Both set an HTTP-only session cookie and return `{user, csrf_token}`. `GET /me` restores that client state; `POST /auth/logout` revokes the session and its sockets.

Mutating requests need an allowed `Origin`. Authenticated mutations also need `X-CSRF-Token`. Use browser credentials on requests. The shared OTP is demo verification, not a password.

## Routes

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health`, `/config` | Readiness and public demo configuration |
| GET/PATCH | `/me` | Current user; change display name |
| POST | `/me/avatar` | Multipart profile image, field `file`, at most 2 MB |
| GET | `/avatars/{filename}` | Authenticated profile image retrieval |
| GET | `/users?q=maya` | Search registered users |
| GET/POST | `/contacts` | List contacts; add `{username}` |
| GET | `/conversations` | Permitted summaries, members, previews, unread counts |
| POST | `/conversations/direct` | Get/create a conversation with `{user_id}` |
| GET | `/conversations/{id}` | Authorized conversation details |
| POST | `/groups` | Create with `{name, member_ids}` |
| PATCH | `/groups/{id}` | Admin rename with `{name}` |
| POST | `/groups/{id}/members` | Admin add with `{user_id}` |
| DELETE | `/groups/{id}/members/{user_id}` | Admin remove |
| PATCH | `/groups/{id}/members/{user_id}` | Admin change `{role: "admin" or "member"}` |
| GET/POST | `/conversations/{id}/messages` | Authorized history / idempotent send |
| GET | `/deliveries` | Up to 100 pending undelivered message payloads |
| POST | `/receipts` | Acknowledge `{message_ids, state}`; state is delivered/read |
| POST | `/messages/{id}/reactions` | Toggle or replace `{emoji}` |

## Sending and retries

```json
{
  "client_message_id": "a-stable-browser-generated-uuid",
  "body": "Coffee at 10:30?",
  "reply_to_id": null
}
```

A new insert returns 201. An identical retry returns the existing record with 200. Reusing a sender/client-ID pair with different content returns 409. Bodies contain 1–4000 non-whitespace characters after trimming.

A saved message includes its server ID, conversation, sender, timestamp, status, receipt counts, optional authorized quote, and reactions. Status is sent, delivered, or read; the browser's sending state is local and precedes this response.

## History

Normal history returns a bounded recent page in ascending display order. `before_id` fetches older history. `after_id` fetches forward; `through_id` fixes a synchronization boundary. `limit` is capped at 100.

The response contains `messages`, `through_id`, `has_more`, `next_before_id`, and `next_after_id`. Use returned cursors rather than timestamp arithmetic. A maximum message ID does not prove all earlier visible messages have been fetched.

Group access requires active membership. Within that group, only messages authored by the user or originally addressed to them are visible. This also applies to quote contents.

## WebSocket `/ws`

The cookie authenticates the handshake. Origin is checked. The first server event is `ready`. A client sends `{"type":"ping"}` about every 20 seconds and receives `pong`.

Client typing packet:

```json
{"type":"typing","conversation_id":12,"active":true}
```

Server change types include `message.new`, `receipt.changed`, `reaction.changed`, `conversation.changed`, `membership.changed`, and `presence.changed`. Message events carry IDs, not message bodies. Typing expires locally and is not saved.

Reconnect with backoff, then fetch fresh summaries/history and pending deliveries. Close 4401 means an invalid or revoked session. Other connection failures trigger recovery rather than logging out. Excess typing events are dropped without invalidating the session.

## Errors

```json
{"error":{"code":"not_member","message":"A useful explanation."}}
```

The exact code depends on the service rule. Expect 401 for a missing/expired session, 403 for permission or request-protection failures, 404 for unavailable resources, 409 for conflicts, 413 for oversized requests, 422 for invalid fields, 429 for throttling, and 503 for a database operation that cannot complete. A transport timeout is an unconfirmed result, not proof that a message was never saved.
