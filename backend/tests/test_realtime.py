import pytest
from starlette.websockets import WebSocketDisconnect
from conftest import send


def receive_type(socket, kind):
    for _ in range(15):
        event = socket.receive_json()
        if event["type"] == kind:
            return event
    raise AssertionError(f"Expected {kind}")


def test_socket_ready_live_message_and_typing(pair):
    alice, bob, cid = pair
    with alice.socket() as first, bob.socket() as second:
        assert receive_type(first, "ready")["user_id"] == alice.user["id"]
        assert receive_type(second, "ready")["user_id"] == bob.user["id"]
        sent = send(alice, cid).json()
        event = receive_type(second, "message.new")
        assert event["message_id"] == sent["id"] and "body" not in event
        first.send_json({"type": "typing", "conversation_id": cid, "active": True})
        assert receive_type(second, "typing")["user_id"] == alice.user["id"]
        second.send_json({"type": "ping"})
        assert receive_type(second, "pong")["type"] == "pong"


def test_socket_does_not_mark_delivered(pair):
    alice, bob, cid = pair
    with bob.socket() as socket:
        receive_type(socket, "ready")
        send(alice, cid)
        receive_type(socket, "message.new")
        assert alice.get(f"/api/conversations/{cid}/messages").json()["messages"][0]["status"] == "sent"


def test_bad_socket_origin(actor):
    alice = actor("alice")
    with pytest.raises(WebSocketDisconnect):
        with alice.socket(origin="https://evil.example"):
            pass


def test_socket_logout_revocation(actor):
    alice = actor("alice")
    with alice.socket() as socket:
        receive_type(socket, "ready")
        alice.post("/api/auth/logout")
        with pytest.raises(WebSocketDisconnect):
            for _ in range(10):
                socket.receive_json()


def test_invalid_socket_packet(actor):
    alice = actor("alice")
    with alice.socket() as socket:
        receive_type(socket, "ready")
        socket.send_text("not json")
        with pytest.raises(WebSocketDisconnect):
            for _ in range(10):
                socket.receive_json()


def test_typing_burst_does_not_end_session(pair):
    alice, bob, cid = pair
    with alice.socket() as socket:
        receive_type(socket, "ready")
        for _ in range(25):
            socket.send_json({"type": "typing", "conversation_id": cid, "active": False})
        socket.send_json({"type": "ping"})
        assert receive_type(socket, "pong")["type"] == "pong"
        assert alice.get("/api/me").status_code == 200
