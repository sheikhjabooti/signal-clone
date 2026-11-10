from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.config import Settings
from app.main import create_app
from app.models import Message, User


@pytest.mark.parametrize("journal_mode", ["WAL", "DELETE"])
def test_migrations_and_seed_survive_restart(tmp_path, journal_mode):
    settings = Settings(data_dir=tmp_path, frontend_dir=tmp_path / "nothing", origins=("http://testserver",), sqlite_journal_mode=journal_mode)
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.post("/api/auth/login", json={"username": "alex", "otp": "123456"}, headers={"Origin": "http://testserver"})
        cookie = f"signal_session={response.cookies['signal_session']}"
        headers = {"Origin": "http://testserver", "Cookie": cookie, "X-CSRF-Token": response.json()["csrf_token"]}
        cid = client.get("/api/conversations").json()[0]["id"]
        response = client.post(f"/api/conversations/{cid}/messages", json={"body": "Survives a restart", "client_message_id": "restart-persistence"}, headers=headers)
        assert response.status_code == 201
        mid = response.json()["id"]
        with app.state.db.read() as session:
            users_before = len(list(session.scalars(select(User))))
            messages_before = len(list(session.scalars(select(Message))))
    app2 = create_app(settings)
    with TestClient(app2) as client:
        assert client.get("/api/me", headers={"Cookie": cookie}).status_code == 200
        history = client.get(f"/api/conversations/{cid}/messages", headers={"Cookie": cookie}).json()["messages"]
        assert any(m["id"] == mid for m in history)
        with app2.state.db.read() as session:
            assert len(list(session.scalars(select(User)))) == users_before
            assert len(list(session.scalars(select(Message)))) == messages_before
        with app2.state.db.engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == journal_mode.lower()
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
            assert connection.exec_driver_sql("PRAGMA integrity_check").scalar() == "ok"
            assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar() == "0001"


def test_invalid_journal_mode_is_rejected():
    with pytest.raises(ValueError, match="SQLITE_JOURNAL_MODE"):
        Settings(sqlite_journal_mode="OFF")
