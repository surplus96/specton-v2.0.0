"""Offline frontend build and fixed Chromium acceptance in the job network."""

import hashlib
import io
import json
import tarfile
from pathlib import Path
from typing import Any

from specton.implementation.verify import docker

BROWSER = Path(__file__).with_name("browser")


def suite_hash() -> str:
    return hashlib.sha256(
        b"".join(p.read_bytes() for p in sorted(BROWSER.glob("*.mjs")))
    ).hexdigest()


def run(
    files: dict[str, bytes],
    network: str,
    image: str,
    labels: list[str],
    token: str,
    non_cancel: str,
    preview: bool,
) -> tuple[dict[str, Any], str | None]:
    container = (
        docker(
            [
                "run",
                "-d",
                "--init",
                *labels,
                "--network",
                network,
                "--user",
                "1000:1000",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--cpus=1",
                "--memory=1g",
                "--pids-limit=256",
                "--shm-size=256m",
                "--tmpfs",
                "/workspace:rw,nosuid,size=128m,uid=1000,gid=1000",
                "--tmpfs",
                "/tmp:rw,nosuid,size=256m,uid=1000,gid=1000",
                image,
            ]
        )
        .decode()
        .strip()
    )
    try:
        for path in sorted(BROWSER.glob("*.mjs")):
            actual = (
                docker(["exec", container, "sha256sum", "/runner/" + path.name]).decode().split()[0]
            )
            if actual != hashlib.sha256(path.read_bytes()).hexdigest():
                raise ValueError("브라우저 이미지의 검증 코드가 다릅니다")
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as archive:
            for name, data in files.items():
                if not (name.startswith("frontend/") or name == "spec/approved-spec.json"):
                    continue
                entry = tarfile.TarInfo(name)
                entry.size = len(data)
                entry.mode = 0o600
                entry.uid = 1000
                entry.gid = 1000
                archive.addfile(entry, io.BytesIO(data))
        docker(
            ["exec", "-i", container, "tar", "xf", "-", "-C", "/workspace"], data=stream.getvalue()
        )
        docker(
            [
                "exec",
                container,
                "ln",
                "-s",
                "/opt/ui/node_modules",
                "/workspace/frontend/node_modules",
            ]
        )
        docker(
            [
                "exec",
                "-w",
                "/workspace/frontend",
                container,
                "node",
                "/opt/ui/node_modules/typescript/bin/tsc",
            ]
        )
        docker(
            [
                "exec",
                "-w",
                "/workspace/frontend",
                container,
                "node",
                "/opt/ui/node_modules/vite/bin/vite.js",
                "build",
                "--configLoader",
                "runner",
                "--base",
                "/",
            ]
        )
        docker(
            [
                "exec",
                "-e",
                "PROBE_TOKEN",
                "-e",
                "PROBE_NON_CANCEL_TOKEN",
                container,
                "node",
                "/runner/acceptance.mjs",
            ],
            env={"PROBE_TOKEN": token, "PROBE_NON_CANCEL_TOKEN": non_cancel},
        )
        report = json.loads(docker(["exec", container, "cat", "/workspace/browser-report.json"]))
        html = None
        if preview:
            docker(["exec", container, "node", "/runner/preview.mjs"])
            html = docker(["exec", container, "cat", "/workspace/preview.html"]).decode()
        return report, html
    finally:
        docker(["rm", "--force", "--volumes", container])
