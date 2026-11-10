from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import delete, func, select
from app.models import Message, Recipient
from app.schemas import MessageInput
from conftest import send


def test_contact_direction(actor):
    alice, bob = actor("alice"), actor("bob")
    assert alice.post("/api/contacts", json={"username": "bob"}).status_code == 201
    assert len(alice.get("/api/contacts").json()) == 1
    assert bob.get("/api/contacts").json() == []
    alice.post("/api/contacts", json={"username": "bob"})
    assert len(alice.get("/api/contacts").json()) == 1


def test_contact_validation(actor):
    alice = actor("alice")
    assert alice.post("/api/contacts", json={"username": "alice"}).status_code == 400
    assert alice.post("/api/contacts", json={"username": "missing"}).status_code == 404


def test_search_escapes_wildcards(actor):
    alice, _ = actor("alice"), actor("bob")
    assert alice.get("/api/users?q=bo").json()[0]["username"] == "bob"
    assert alice.get("/api/users?q=%25%25").json() == []


def test_direct_pair_unique(pair):
    alice, bob, cid = pair
    assert bob.post("/api/conversations/direct", json={"user_id": alice.user["id"]}).json()["id"] == cid


def test_concurrent_direct_creation(actor, app):
    alice, bob = actor("alice"), actor("bob")
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: app.state.services.direct(alice.user["id"], bob.user["id"])[0]["id"], range(20)))
    assert len(set(results)) == 1


def test_cannot_start_self_chat(actor):
    person = actor("alice")
    assert person.post("/api/conversations/direct", json={"user_id": person.user["id"]}).status_code == 400


def test_send_and_history(pair):
    alice, bob, cid = pair
    response = send(alice, cid)
    assert response.status_code == 201
    message = response.json()
    assert message["status"] == "sent"
    assert bob.get(f"/api/conversations/{cid}/messages").json()["messages"][0]["body"] == "Hello"
    assert bob.get("/api/conversations").json()[0]["unread_count"] == 1
    assert alice.get("/api/conversations").json()[0]["unread_count"] == 0


def test_sender_id_cannot_be_spoofed(pair):
    alice, bob, cid = pair
    result = alice.post(f"/api/conversations/{cid}/messages", json={"body": "spoof", "client_message_id": "spoof-id-001", "sender_id": bob.user["id"]})
    assert result.status_code == 422


def test_retry_idempotent(pair):
    alice, bob, cid = pair
    first, retry = send(alice, cid), send(alice, cid)
    assert first.status_code == 201 and retry.status_code == 200
    assert first.json()["id"] == retry.json()["id"]
    assert len(bob.get(f"/api/conversations/{cid}/messages").json()["messages"]) == 1


def test_concurrent_retry(pair, app):
    alice, _, cid = pair
    payload = MessageInput(body="same send", client_message_id="concurrent-retry-id")
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: app.state.services.send(alice.user["id"], cid, payload), range(20)))
    assert len({r[0]["id"] for r in results}) == 1
    assert sum(r[2] for r in results) == 1


def test_retry_conflict(pair):
    alice, _, cid = pair
    send(alice, cid)
    assert send(alice, cid, body="Changed").status_code == 409


def test_empty_and_long_message(pair):
    alice, _, cid = pair
    assert send(alice, cid, body="   ").status_code == 422
    assert send(alice, cid, body="a" * 4001).status_code == 422


def test_non_member_forbidden(pair, actor):
    alice, bob, cid = pair
    other = actor("charlie")
    assert other.get(f"/api/conversations/{cid}/messages").status_code == 403
    assert send(other, cid).status_code == 403
    assert other.get(f"/api/conversations/{cid}").status_code == 403


def test_delivery_and_read_are_separate(pair):
    alice, bob, cid = pair
    mid = send(alice, cid).json()["id"]
    assert len(bob.get("/api/deliveries").json()) == 1
    bob.post("/api/receipts", json={"message_ids": [mid], "state": "delivered"})
    message = alice.get(f"/api/conversations/{cid}/messages").json()["messages"][0]
    assert message["status"] == "delivered"
    assert bob.get("/api/conversations").json()[0]["unread_count"] == 1
    assert bob.get("/api/deliveries").json() == []
    bob.post("/api/receipts", json={"message_ids": [mid], "state": "read"})
    assert alice.get(f"/api/conversations/{cid}/messages").json()["messages"][0]["status"] == "read"
    assert bob.get("/api/conversations").json()[0]["unread_count"] == 0


def test_read_implies_delivery_and_does_not_regress(pair):
    alice, bob, cid = pair
    mid = send(alice, cid).json()["id"]
    bob.post("/api/receipts", json={"message_ids": [mid], "state": "read"})
    bob.post("/api/receipts", json={"message_ids": [mid], "state": "delivered"})
    message = bob.get(f"/api/conversations/{cid}/messages").json()["messages"][0]
    assert message["status"] == "read"
    assert message["read_at"] and message["delivered_at"]


def test_receipt_cannot_be_spoofed(pair, actor):
    alice, bob, cid = pair
    other = actor("charlie")
    mid = send(alice, cid).json()["id"]
    other.post("/api/receipts", json={"message_ids": [mid], "state": "read"})
    alice.post("/api/receipts", json={"message_ids": [mid], "state": "read"})
    assert alice.get(f"/api/conversations/{cid}/messages").json()["messages"][0]["status"] == "sent"


def test_keyset_pagination_and_fixed_boundary(pair, app):
    alice, bob, cid = pair
    for i in range(130):
        app.state.services.send(alice.user["id"], cid, MessageInput(body=str(i), client_message_id=f"pagination-{i:04}"))
    latest = bob.get(f"/api/conversations/{cid}/messages?limit=50").json()
    assert len(latest["messages"]) == 50 and latest["has_more"]
    older = bob.get(f"/api/conversations/{cid}/messages?limit=50&before_id={latest['next_before_id']}").json()
    assert older["messages"][-1]["id"] < latest["messages"][0]["id"]
    first = bob.get(f"/api/conversations/{cid}/messages?after_id=0&limit=100").json()
    added = send(alice, cid, key="new-after-boundary").json()
    second = bob.get(f"/api/conversations/{cid}/messages?after_id={first['next_after_id']}&through_id={first['through_id']}&limit=100").json()
    assert len(first["messages"]) + len(second["messages"]) == 130
    assert second["has_more"] is False
    assert added["id"] not in [m["id"] for m in second["messages"]]


def test_cursor_validation(pair):
    alice, _, cid = pair
    assert alice.get(f"/api/conversations/{cid}/messages?before_id=5&after_id=1").status_code == 400
    assert alice.get(f"/api/conversations/{cid}/messages?limit=1000").status_code == 422


def test_message_ids_not_reused(pair, app):
    alice, _, cid = pair
    old = send(alice, cid).json()["id"]
    with app.state.db.write() as session:
        session.execute(delete(Message).where(Message.id == old))
    new = send(alice, cid, key="second-message-id").json()["id"]
    assert new > old


def test_replies_and_reactions(pair):
    alice, bob, cid = pair
    mid = send(alice, cid).json()["id"]
    reply = send(bob, cid, key="reply-message-id", reply=mid).json()
    assert reply["reply"]["body"] == "Hello"
    assert bob.post(f"/api/messages/{mid}/reactions", json={"emoji": "❤️"}).status_code == 200
    result = bob.get(f"/api/conversations/{cid}/messages").json()["messages"][0]
    assert result["reactions"] == [{"emoji": "❤️", "count": 1, "mine": True}]
    bob.post(f"/api/messages/{mid}/reactions", json={"emoji": "❤️"})
    assert bob.get(f"/api/conversations/{cid}/messages").json()["messages"][0]["reactions"] == []


def test_invalid_cross_chat_reply(pair, actor):
    alice, bob, cid = pair
    charlie = actor("charlie")
    mid = send(alice, cid).json()["id"]
    other = alice.post("/api/conversations/direct", json={"user_id": charlie.user["id"]}).json()["id"]
    assert send(alice, other, key="wrong-reply-id", reply=mid).status_code == 400
