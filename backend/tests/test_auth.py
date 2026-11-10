import io
from PIL import Image
from sqlalchemy import select
from app.models import SessionToken


def test_signup_and_normalization(client):
    response = client.post("/api/auth/register", json={"username": "Alice_42", "display_name": "Alice", "otp": "123456"}, headers={"Origin": "http://testserver"})
    assert response.status_code == 201
    assert response.json()["user"]["username"] == "alice_42"
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert client.get("/api/me").status_code == 200


def test_duplicate_username(actor):
    first = actor("alice")
    response = first.post("/api/auth/register", json={"username": "alice", "otp": "123456"})
    assert response.status_code == 409


def test_wrong_code(client):
    response = client.post("/api/auth/register", json={"username": "alice", "otp": "secret-999"}, headers={"Origin": "http://testserver"})
    assert response.status_code == 401
    assert "secret-999" not in response.text


def test_invalid_username(client):
    response = client.post("/api/auth/register", json={"username": "a<script>", "otp": "123456"}, headers={"Origin": "http://testserver"})
    assert response.status_code == 422


def test_unknown_login(client):
    response = client.post("/api/auth/login", json={"username": "unknown", "otp": "123456"}, headers={"Origin": "http://testserver"})
    assert response.status_code == 404


def test_no_session(client):
    assert client.get("/api/conversations").status_code == 401


def test_csrf_required(actor):
    person = actor("alice")
    assert person.patch("/api/me", json={"display_name": "Other"}, headers={"X-CSRF-Token": ""}).status_code == 403


def test_origin_required(actor):
    person = actor("alice")
    assert person.patch("/api/me", json={"display_name": "Other"}, headers={"Origin": "https://evil.example"}).status_code == 403


def test_logout_revokes(actor):
    person = actor("alice")
    assert person.post("/api/auth/logout").status_code == 200
    assert person.get("/api/me").status_code == 401


def test_expired_session(actor, app):
    person = actor("alice")
    with app.state.db.write() as session:
        session.scalar(select(SessionToken).where(SessionToken.user_id == person.user["id"])).expires_at = "2000-01-01T00:00:00.000+00:00"
    assert person.get("/api/me").status_code == 401


def test_profile_update(actor):
    person = actor("alice")
    assert person.patch("/api/me", json={"display_name": "Alice Example"}).status_code == 200
    assert person.get("/api/me").json()["user"]["display_name"] == "Alice Example"


def test_avatar_reencoded(actor):
    person = actor("alice")
    image = io.BytesIO()
    Image.new("RGB", (60, 40), "white").save(image, "PNG")
    response = person.post("/api/me/avatar", files={"file": ("../../bad.png", image.getvalue(), "image/png")})
    assert response.status_code == 200
    url = response.json()["avatar_url"]
    assert url.endswith(".jpg") and "bad" not in url
    downloaded = person.get(url)
    assert downloaded.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(downloaded.content)).size == (256, 256)


def test_svg_avatar_rejected(actor):
    person = actor("alice")
    response = person.post("/api/me/avatar", files={"file": ("x.svg", b'<svg onload="alert(1)"></svg>', "image/svg+xml")})
    assert response.status_code == 400


def test_avatar_requires_session(client):
    assert client.get("/api/avatars/" + "a" * 32 + ".jpg").status_code == 401


def test_request_size_limit(actor):
    person = actor("alice")
    assert person.patch("/api/me", content=b"a" * 70000, headers={"content-type": "application/json"}).status_code == 413


def test_response_headers(actor):
    person = actor("alice")
    response = person.get("/api/me")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
