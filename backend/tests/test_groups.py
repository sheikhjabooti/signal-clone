from conftest import send


def group(alice, others):
    response = alice.post("/api/groups", json={"name": "Friends", "member_ids": [p.user["id"] for p in others]})
    assert response.status_code == 201
    return response.json()["id"]


def test_group_admin_controls(actor):
    alice, bob, charlie = actor("alice"), actor("bob"), actor("charlie")
    cid = group(alice, [bob])
    assert bob.post(f"/api/groups/{cid}/members", json={"user_id": charlie.user["id"]}).status_code == 403
    assert bob.patch(f"/api/groups/{cid}", json={"name": "Hacked"}).status_code == 403
    assert alice.post(f"/api/groups/{cid}/members", json={"user_id": charlie.user["id"]}).status_code == 200
    assert len(charlie.get(f"/api/conversations/{cid}").json()["members"]) == 3


def test_last_admin_protected(actor):
    alice, bob = actor("alice"), actor("bob")
    cid = group(alice, [bob])
    assert alice.delete(f"/api/groups/{cid}/members/{alice.user['id']}").status_code == 409
    assert alice.patch(f"/api/groups/{cid}/members/{alice.user['id']}", json={"role": "member"}).status_code == 409
    assert alice.patch(f"/api/groups/{cid}/members/{bob.user['id']}", json={"role": "admin"}).status_code == 200
    assert alice.delete(f"/api/groups/{cid}/members/{alice.user['id']}").status_code == 200


def test_removal_revokes_history_sends_and_receipts(actor):
    alice, bob = actor("alice"), actor("bob")
    cid = group(alice, [bob])
    mid = send(alice, cid).json()["id"]
    assert alice.delete(f"/api/groups/{cid}/members/{bob.user['id']}").status_code == 200
    assert bob.get(f"/api/conversations/{cid}/messages").status_code == 403
    assert send(bob, cid, key="removed-sender").status_code == 403
    assert bob.get("/api/deliveries").json() == []
    bob.post("/api/receipts", json={"message_ids": [mid], "state": "read"})
    assert alice.get(f"/api/conversations/{cid}/messages").json()["messages"][0]["status"] == "sent"


def test_join_and_rejoin_visibility(actor):
    alice, bob, charlie = actor("alice"), actor("bob"), actor("charlie")
    cid = group(alice, [bob])
    old = send(alice, cid, body="Before Charlie", key="before-join-id").json()
    alice.post(f"/api/groups/{cid}/members", json={"user_id": charlie.user["id"]})
    assert charlie.get(f"/api/conversations/{cid}/messages").json()["messages"] == []
    summary = charlie.get(f"/api/conversations/{cid}").json()
    assert summary["last_message"] is None and summary["unread_count"] == 0
    allowed = send(alice, cid, body="With Charlie", key="after-join-id", reply=old["id"]).json()
    visible = charlie.get(f"/api/conversations/{cid}/messages").json()["messages"]
    assert len(visible) == 1 and visible[0]["reply"] is None
    alice.delete(f"/api/groups/{cid}/members/{charlie.user['id']}")
    missed = send(alice, cid, body="While absent", key="during-absence-id").json()
    alice.post(f"/api/groups/{cid}/members", json={"user_id": charlie.user["id"]})
    newest = send(alice, cid, body="Welcome back", key="after-rejoin-id").json()
    visible = charlie.get(f"/api/conversations/{cid}/messages").json()["messages"]
    assert [m["id"] for m in visible] == [allowed["id"], newest["id"]]
    assert missed["id"] not in [m["id"] for m in visible]
    assert allowed["recipient_count"] == 2
    assert old["recipient_count"] == 1


def test_group_receipt_aggregation(actor):
    alice, bob, charlie = actor("alice"), actor("bob"), actor("charlie")
    cid = group(alice, [bob, charlie])
    mid = send(alice, cid).json()["id"]
    bob.post("/api/receipts", json={"message_ids": [mid], "state": "read"})
    partial = alice.get(f"/api/conversations/{cid}/messages").json()["messages"][0]
    assert partial["read_count"] == 1 and partial["status"] == "sent"
    charlie.post("/api/receipts", json={"message_ids": [mid], "state": "delivered"})
    assert alice.get(f"/api/conversations/{cid}/messages").json()["messages"][0]["status"] == "delivered"


def test_cannot_change_direct_chat_members(pair):
    alice, bob, cid = pair
    assert alice.delete(f"/api/groups/{cid}/members/{bob.user['id']}").status_code == 403


def test_group_deduplicates_members(actor):
    alice, bob = actor("alice"), actor("bob")
    result = alice.post("/api/groups", json={"name": "Friends", "member_ids": [bob.user["id"], bob.user["id"], alice.user["id"]]})
    assert result.status_code == 201
    assert len(result.json()["members"]) == 2
