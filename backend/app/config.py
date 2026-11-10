from dataclasses import dataclass, field
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", ROOT / "data")))
    frontend_dir: Path = field(default_factory=lambda: Path(os.getenv("FRONTEND_DIR", ROOT / "frontend" / "out")))
    origins: tuple[str, ...] = field(default_factory=lambda: tuple(
        x.strip().rstrip("/") for x in os.getenv(
            "ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000,http://localhost:3000"
        ).split(",") if x.strip()
    ))
    cookie_secure: bool = field(default_factory=lambda: os.getenv("COOKIE_SECURE", "false").lower() == "true")
    demo_otp: str = field(default_factory=lambda: os.getenv("DEMO_OTP", "123456"))
    seed_demo: bool = field(default_factory=lambda: os.getenv("SEED_DEMO", "true").lower() == "true")
    sqlite_journal_mode: str = field(default_factory=lambda: os.getenv("SQLITE_JOURNAL_MODE", "WAL").upper())
    session_days: int = 7
    max_group_size: int = 32
    max_avatar_bytes: int = 2 * 1024 * 1024
    cookie_name: str = "signal_session"

    def __post_init__(self):
        if self.sqlite_journal_mode not in {"WAL", "DELETE"}:
            raise ValueError("SQLITE_JOURNAL_MODE must be WAL or DELETE.")

    @property
    def database_url(self) -> str:
        return f"sqlite:///{(self.data_dir / 'signal.db').resolve()}"

    @property
    def avatars_dir(self) -> Path:
        return self.data_dir / "avatars"
