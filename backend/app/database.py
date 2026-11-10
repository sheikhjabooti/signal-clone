from contextlib import contextmanager
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from .config import Settings


class Database:
    def __init__(self, settings: Settings):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        settings.avatars_dir.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(settings.database_url, connect_args={"check_same_thread": False, "timeout": 5})

        @event.listens_for(self.engine, "connect")
        def pragmas(connection, _record):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA synchronous=FULL")
            cursor.close()

        with self.engine.connect() as connection:
            # WAL is for local disks. PythonAnywhere uses a network-backed home
            # directory, so its launcher selects the rollback journal instead.
            connection.exec_driver_sql(f"PRAGMA journal_mode={settings.sqlite_journal_mode}")
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    @contextmanager
    def read(self):
        with self.sessions() as session:
            # A consistent snapshot across the SELECTs in this operation.
            session.execute(text("BEGIN"))
            yield session

    @contextmanager
    def write(self):
        with self.sessions() as session:
            try:
                # Obtain the writer slot before checking permissions. Membership
                # cannot change between that check and the eventual insert.
                session.execute(text("BEGIN IMMEDIATE"))
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    def close(self):
        self.engine.dispose()
