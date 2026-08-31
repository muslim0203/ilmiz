"""Conservative pre-push guard; report paths/reasons, never secret values.

This is not a substitute for GitHub secret scanning or a human review.
Default checks the Git index; --history also checks blobs reachable from HEAD.
It never reads ignored databases, local environment files or SSH keys.
"""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import PurePosixPath


MAX_FILE_SIZE = 10 * 1024 * 1024
LOCAL_OPERATOR_FILES = {
    'deploy/readme.md', 'deploy/ilmiz-staging.service',
    'deploy/install_staging.sh', 'deploy/update_seo_staging.sh',
    'deploy/staging.env.example', 'docs/seo-audit-2026-08-31.md',
}
SECRET_PATTERNS = (
    ("private key", re.compile(rb"-----BEGIN (?:OPENSSH |RSA |EC |DSA |ENCRYPTED )?PRIVATE KEY-----")),
    ("GitHub credential", re.compile(rb"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})\b")),
    ("AWS access key", re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("credential in URL", re.compile(rb"https?://[^\s/:\"'<>]+:[^\s/@\"'<>]{12,}@", re.I)),
)


def path_reason(name: str) -> str | None:
    path = PurePosixPath(name.lower())
    if str(path) in LOCAL_OPERATOR_FILES:
        return "local-only server operations file"
    if any(part in {".ssh", ".secrets", ".deploy-artifacts", "node_modules", ".venv", "backups"} for part in path.parts):
        return "private/generated directory"
    if (path.name == ".env" or path.name.startswith(".env.")) and not path.name.endswith(".example"):
        return "environment file"
    if re.search(r"\.(?:db|sqlite3?)(?:-|$)", path.name):
        return "database/sidecar"
    if path.suffix in {".pem", ".key", ".p12", ".pfx", ".zip", ".gz", ".7z"}:
        return "credential/archive file"
    return None


def content_reasons(data: bytes) -> list[str]:
    reasons = []
    if data.startswith(b"SQLite format 3\x00"):
        reasons.append("SQLite database content")
    reasons.extend(label for label, pattern in SECRET_PATTERNS if pattern.search(data))
    return reasons


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args])


def check(history: bool = False) -> list[str]:
    issues: list[str] = []
    objects: dict[str, str] = {}
    for entry in git("ls-files", "--stage", "-z").split(b"\0"):
        if not entry:
            continue
        info, raw_path = entry.split(b"\t", 1)
        mode, oid, stage = info.decode().split()
        name = raw_path.decode("utf-8")
        if mode not in {"100644", "100755"} or stage != "0":
            issues.append(f"{name}: symlink/submodule/unmerged entry")
        reason = path_reason(name)
        if reason:
            issues.append(f"{name}: {reason}")
        objects[oid] = name
    if history:
        for entry in git("rev-list", "--objects", "HEAD").decode("utf-8").splitlines():
            oid, _, name = entry.partition(" ")
            if name:
                reason = path_reason(name)
                if reason:
                    issues.append(f"history:{name}: {reason}")
                objects.setdefault(oid, f"history:{name}")
    for oid, name in objects.items():
        # Query metadata before content: never dump or load large database blobs.
        kind = git("cat-file", "-t", oid).strip()
        if kind != b"blob":
            continue
        size = int(git("cat-file", "-s", oid))
        if size > MAX_FILE_SIZE:
            issues.append(f"{name}: file exceeds 10 MiB, manual review required")
            continue
        for reason in content_reasons(git("cat-file", "blob", oid)):
            issues.append(f"{name}: {reason}")
    return sorted(set(issues))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args()
    issues = check(args.history)
    if issues:
        print("Repository guard blocked publication (values are not displayed):")
        print("\n".join(issues))
        raise SystemExit(1)
    print("Repository guard passed. No flagged database/key/archive paths or known credential patterns.")


if __name__ == "__main__":
    main()
