"""Transmit a tested code archive over a restricted, pinned-host SSH connection.

Credentials exist only in environment secrets and an ephemeral private directory.
Never print environment values or SSH stderr (which may contain host details).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path


def payload(archive: Path, release: str) -> bytes:
    if not re.fullmatch(r"[0-9a-f]{40}-[1-9][0-9]*-[1-9][0-9]*", release):
        raise ValueError("Invalid release identifier")
    content = archive.read_bytes()
    if not 1 <= len(content) <= 20 * 1024 * 1024:
        raise ValueError("Runtime archive size is outside the allowed range")
    expected = (archive.parent / "SHA256SUMS").read_text(encoding="ascii").split()
    digest = hashlib.sha256(content).hexdigest()
    if expected != [digest, "runtime.tar.gz"]:
        raise ValueError("Runtime checksum mismatch")
    header = {"release": release, "sha256": digest, "size": len(content)}
    return json.dumps(header, separators=(",", ":")).encode() + b"\n" + content


def send(content: bytes) -> int:
    required = ("OVH_DEPLOY_HOST", "OVH_DEPLOY_USER", "OVH_DEPLOY_KEY", "OVH_KNOWN_HOSTS")
    settings = {name: os.environ.get(name, "") for name in required}
    if any(not value.strip() for value in settings.values()):
        raise ValueError("Required deployment environment secret is missing")
    if not re.fullmatch(r"[a-zA-Z0-9.-]+", settings["OVH_DEPLOY_HOST"]):
        raise ValueError("Invalid host setting")
    if not re.fullmatch(r"[a-z_][a-z0-9_-]*", settings["OVH_DEPLOY_USER"]):
        raise ValueError("Invalid deployment user setting")
    with tempfile.TemporaryDirectory(prefix="ilmiz-ci-ssh-") as directory:
        root = Path(directory)
        key = root / "key"
        known = root / "known_hosts"
        key.write_text(settings["OVH_DEPLOY_KEY"].strip() + "\n", encoding="ascii")
        known.write_text(settings["OVH_KNOWN_HOSTS"].strip() + "\n", encoding="ascii")
        key.chmod(0o600)
        known.chmod(0o600)
        command = [
            "ssh", "-T", "-F", "none", "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={known}",
            "-o", "IdentitiesOnly=yes", "-o", "ConnectTimeout=15",
            "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=4",
            "-i", str(key), f"{settings['OVH_DEPLOY_USER']}@{settings['OVH_DEPLOY_HOST']}",
            "deploy",
        ]
        # Do not allow SSH to inherit the secret-bearing environment.
        environment = {k: v for k, v in os.environ.items() if k not in required}
        result = subprocess.run(command, input=content, capture_output=True, env=environment, timeout=1100)
        # The trusted receiver intentionally outputs only these non-sensitive lines.
        for line in result.stdout.decode("utf-8", errors="replace").splitlines():
            if line.startswith("DEPLOY: ") and len(line) <= 200:
                print(line, flush=True)
        if result.returncode:
            print("Deployment failed. Server operator logs have details; credentials and host are hidden.")
        return result.returncode


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("release")
    args = parser.parse_args()
    try:
        raise SystemExit(send(payload(args.archive, args.release)))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise SystemExit("Deployment could not complete; verify private settings and server logs.")


if __name__ == "__main__":
    main()
