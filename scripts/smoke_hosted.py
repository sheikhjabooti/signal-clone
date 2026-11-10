"""Check a deployed demo with two independent accounts, without a browser.

The test creates fictional accounts and messages. It never prints cookies.
Run only against the assignment instance you own.
"""
from __future__ import annotations

import argparse
from contextlib import suppress
from http.cookiejar import CookieJar
import json
from pathlib import Path
import secrets
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener


class Account:
    def __init__(self, origin: str):
        self.origin = origin.rstrip("/")
        self.cookies = CookieJar()
        self.http = build_opener(HTTPCookieProcessor(self.cookies))
        self.csrf = ""
        self.user: dict = {}

    def call(self, method: str, path: str, data=None, expected=(200, 201)):
        headers = {"Origin": self.origin, "Content-Type": "application/json"}
        if self.csrf:
            headers["X-CSRF-Token"] = self.csrf
        request = Request(self.origin + path, method=method, headers=headers,
                          data=json.dumps(data).encode() if data is not None else None)
        try:
            with self.http.open(request, timeout=30) as response:
                status, raw = response.status, response.read()
        except HTTPError as error:
            status, raw = error.code, error.read()
        if status not in expected:
            raise RuntimeError(f"{method} {path}: HTTP {status}, expected {expected}")
        return json.loads(raw)

    def authenticate(self, username: str, register: bool = True):
        result = self.call("POST", "/api/auth/" + ("register" if register else "login"), {
            "username": username, "display_name": "Deployment Check", "otp": "123456",
        })
        self.user, self.csrf = result["user"], result["csrf_token"]

    def cookie_header(self) -> str:
        return "; ".join(f"{cookie.name}={cookie.value}" for cookie in self.cookies)


def receive_until(ws, event_type: str, *, message_id=None, timeout=20):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        event = json.loads(ws.recv(timeout=max(0.1, end - time.monotonic())))
        if event.get("type") == event_type and (message_id is None or event.get("message_id") == message_id):
            return event
    raise RuntimeError(f"No {event_type} event arrived.")


def validate_origin(url: str, allow_local: bool = False) -> str:
    parsed = urlsplit(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ValueError("Pass only the application origin, without credentials or a path.")
    local = parsed.hostname in {"localhost", "127.0.0.1"} and allow_local
    if parsed.scheme != "https" and not (local and parsed.scheme == "http"):
        raise ValueError("Use HTTPS for the hosted app. Local checks require --allow-local.")
    if not parsed.hostname:
        raise ValueError("Application hostname is missing.")
    return url.rstrip("/")


def check(origin: str, save_probe: Path | None = None, api_only: bool = False):
    from websockets.sync.client import connect
    a, b = Account(origin), Account(origin)
    assert a.call("GET", "/api/health")["status"] == "ok"
    if not api_only:
        with a.http.open(origin + "/", timeout=30) as response:
            if "text/html" not in response.headers.get("Content-Type", ""):
                raise RuntimeError("The backend is online, but the frontend is not built.")
    nonce = secrets.token_hex(6)
    a.authenticate("check_" + nonce + "a")
    b.authenticate("check_" + nonce + "b")
    try:
        cid = a.call("POST", "/api/conversations/direct", {"user_id": b.user["id"]})["id"]
        ws_origin = origin.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
        with connect(ws_origin + "/ws", origin=origin,
                     additional_headers={"Cookie": b.cookie_header()}, open_timeout=25) as ws:
            receive_until(ws, "ready")
            payload = {"body": "Hosting check " + nonce, "client_message_id": "hosting_" + nonce}
            message = a.call("POST", f"/api/conversations/{cid}/messages", payload)
            receive_until(ws, "message.new", message_id=message["id"])
            retried = a.call("POST", f"/api/conversations/{cid}/messages", payload)
            assert retried["id"] == message["id"], "Retry created another message."
            history = b.call("GET", f"/api/conversations/{cid}/messages")["messages"]
            assert sum(m["id"] == message["id"] for m in history) == 1
            b.call("POST", "/api/receipts", {"message_ids": [message["id"]], "state": "read"})
            sent = a.call("GET", f"/api/conversations/{cid}/messages")["messages"]
            assert next(m for m in sent if m["id"] == message["id"])["status"] == "read"
            group = a.call("POST", "/api/groups", {"name": "Hosting check " + nonce, "member_ids": [b.user["id"]]})
            gid = group["id"]
            b.call("DELETE", f"/api/groups/{gid}/members/{a.user['id']}", expected=(403,))
            gm = a.call("POST", f"/api/conversations/{gid}/messages", {
                "body": "Group delivery check", "client_message_id": "group_" + nonce,
            })
            receive_until(ws, "message.new", message_id=gm["id"])
            a.call("DELETE", f"/api/groups/{gid}/members/{b.user['id']}")
            b.call("GET", f"/api/conversations/{gid}/messages", expected=(403,))
        if save_probe:
            # Only fictional public demo identifiers are saved, never session tokens.
            save_probe.write_text(json.dumps({"origin": origin, "username": a.user["username"],
                "conversation_id": cid, "message_id": message["id"], "body": message["body"]}))
        print("PASS: login, direct/group messaging, WebSocket events, receipts, retry deduplication, and group permissions")
    finally:
        for account in (a, b):
            with suppress(Exception):
                account.call("POST", "/api/auth/logout", {})


def verify_probe(origin: str, path: Path):
    data = json.loads(path.read_text())
    if data["origin"] != origin:
        raise ValueError("The persistence probe belongs to another origin.")
    account = Account(origin)
    account.authenticate(data["username"], register=False)
    try:
        history = account.call("GET", f"/api/conversations/{data['conversation_id']}/messages")["messages"]
        assert any(m["id"] == data["message_id"] and m["body"] == data["body"] for m in history)
        print("PASS: account and saved message survived the requested service reload")
    finally:
        account.call("POST", "/api/auth/logout", {})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("origin")
    parser.add_argument("--allow-local", action="store_true")
    parser.add_argument("--api-only", action="store_true")
    parser.add_argument("--save-probe", type=Path)
    parser.add_argument("--verify-probe", type=Path)
    args = parser.parse_args()
    origin = validate_origin(args.origin, args.allow_local)
    if args.verify_probe:
        verify_probe(origin, args.verify_probe)
    else:
        check(origin, args.save_probe, args.api_only)


if __name__ == "__main__":
    main()
