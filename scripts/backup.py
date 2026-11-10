"""Create a consistent SQLite snapshot, including transactions in the WAL."""
import argparse
from pathlib import Path
import sqlite3


def backup(source: Path, destination: Path) -> None:
    source, destination = source.resolve(), destination.resolve()
    if not source.is_file():
        raise ValueError(f"Database does not exist: {source}")
    if source == destination or destination.exists():
        raise ValueError("Choose a new destination; existing backups are not overwritten.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as src:
            with sqlite3.connect(destination) as dst:
                src.backup(dst)
                if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("Backup integrity check failed.")
    except Exception:
        destination.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        backup(args.source, args.destination)
    except (ValueError, OSError, sqlite3.Error, RuntimeError) as error:
        parser.exit(1, f"Backup failed: {error}\n")
    print(f"Saved {args.destination}. Copy avatars separately to back up profile photos.")
