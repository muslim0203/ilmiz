"""Build an allowlisted runtime archive and a WAL-safe SQLite snapshot.

Run from the project root after npm run build. No .env, SSH keys, git history,
local logs or old backups are packaged. Existing output is never overwritten.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import tarfile
import time
from datetime import datetime, timezone
from contextlib import closing
from pathlib import Path


def snapshot(source: Path, destination: Path) -> None:
    source = source.resolve(strict=True)
    # Reserve a new file; refuse to overwrite any existing backup/database.
    with destination.open("xb"):
        pass
    started = time.monotonic()

    def progress(status: int, remaining: int, total: int) -> None:
        if time.monotonic() - started > 300:
            raise TimeoutError("Backup exceeded five minutes; incomplete file retained.")

    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src:
        with closing(sqlite3.connect(destination)) as dst:
            src.backup(dst, pages=2048, progress=progress, sleep=0.1)
            check = dst.execute("PRAGMA quick_check").fetchall()
            if check != [("ok",)]:
                raise RuntimeError(f"Snapshot failed integrity check: {check}")
            dst.execute("PRAGMA journal_mode=DELETE")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if not (root / "dist/index.html").is_file():
        raise SystemExit("Run npm run build first.")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    database = output / "ilmiz.db"
    snapshot(root / "ilmiz.db", database)
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
        counts = {
            "journals": db.execute("SELECT count(*) FROM journals").fetchone()[0],
            "articles": db.execute("SELECT count(*) FROM articles WHERE is_deleted=0").fetchone()[0],
            "healthySources": db.execute("SELECT count(*) FROM harvest_sources WHERE status='healthy'").fetchone()[0],
        }
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "counts": counts,
        "database_bytes": database.stat().st_size,
        "database_sha256": sha256(database),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    runtime_files = list((root / "backend").rglob("*.py"))
    runtime_files += list((root / "harvester").rglob("*.py"))
    runtime_files += [root / "backend/requirements.txt"]
    runtime_files += [p for p in (root / "dist").rglob("*") if p.is_file()]
    runtime_files += [p for p in (root / "deploy").iterdir() if p.is_file()]
    runtime_archive = output / "runtime.tar.gz"
    with tarfile.open(runtime_archive, "x:gz", compresslevel=4) as archive:
        for path in sorted(runtime_files):
            if path.is_symlink() or any(part.startswith(".") for part in path.relative_to(root).parts):
                raise RuntimeError(f"Unexpected hidden file or symlink: {path}")
            archive.add(path, arcname=path.relative_to(root).as_posix(), recursive=False)
    data_archive = output / "database.tar.gz"
    with tarfile.open(data_archive, "x:gz", compresslevel=3) as archive:
        archive.add(database, arcname="ilmiz.db")
        archive.add(output / "manifest.json", arcname="manifest.json")
    checksums = "".join(f"{sha256(p)}  {p.name}\n" for p in (runtime_archive, data_archive))
    (output / "SHA256SUMS").write_text(checksums, encoding="ascii")
    print(json.dumps(manifest, indent=2), flush=True)
    print(f"Runtime: {runtime_archive.stat().st_size:,} bytes; database archive: {data_archive.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
