from dataclasses import dataclass
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app


@dataclass
class Actor:
    client: TestClient
    user: dict
    cookie: str
    csrf: str

    def request(self, method, path, **kwargs):
        headers = {"Origin": "http://testserver", "Cookie": self.cookie, "X-CSRF-Token": self.csrf}
        headers.update(kwargs.pop("headers", {}))
        return self.client.request(method, path, headers=headers, **kwargs)

    def get(self, path, **kwargs): return self.request("GET", path, **kwargs)
    def post(self, path, **kwargs): return self.request("POST", path, **kwargs)
    def patch(self, path, **kwargs): return self.request("PATCH", path, **kwargs)
    def delete(self, path, **kwargs): return self.request("DELETE", path, **kwargs)
    def socket(self, origin="http://testserver"):
        return self.client.websocket_connect("/ws", headers={"Origin": origin, "Cookie": self.cookie})


@pytest.fixture
def app(tmp_path):
    return create_app(Settings(data_dir=tmp_path, frontend_dir=tmp_path / "no-frontend", origins=("http://testserver",), seed_demo=False))


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


@pytest.fixture
def actor(client):
    def create(username, register=True):
        # Independent browsers, rather than accidentally rotating the prior login.
        client.cookies.clear()
        response = client.post(f"/api/auth/{'register' if register else 'login'}", json={
            "username": username, "display_name": username.title(), "otp": "123456",
        }, headers={"Origin": "http://testserver"})
        assert response.status_code in {200, 201}, response.text
        data = response.json()
        return Actor(client, data["user"], f"signal_session={response.cookies['signal_session']}", data["csrf_token"])
    return create


@pytest.fixture
def pair(actor):
    alice, bob = actor("alice"), actor("bob")
    response = alice.post("/api/conversations/direct", json={"user_id": bob.user["id"]})
    assert response.status_code == 201
    return alice, bob, response.json()["id"]


def send(actor, cid, body="Hello", key="test-message-001", reply=None):
    return actor.post(f"/api/conversations/{cid}/messages", json={"body": body, "client_message_id": key, "reply_to_id": reply})
