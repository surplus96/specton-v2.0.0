"""운영 API와 분리해 실행하는 제한된 Docker DB/HTTP smoke 검증 CLI."""

import argparse
import hashlib
import io
import json
import os
import re
import secrets
import signal
import subprocess
import tarfile
import time
import zipfile
from contextlib import suppress
from pathlib import Path
from typing import Any
from uuid import uuid4

from specton.implementation.delivery import EXTRA_TEMPLATES
from specton.implementation.package import (
    CALCULATION_TEMPLATES,
    COMMAND_TEMPLATES,
    TEMPLATES,
    json_bytes,
)
from specton.implementation.runtime_suite import suite_files, suite_hash

LEGACY_ALLOWED = {
    "spec/approved-spec.json",
    "spec/design-state.json",
    "backend/app.py",
    "backend/inventory.py",
    "backend/contract.json",
    "backend/approved.sql",
    "backend/requirements.txt",
    "frontend/src/contract.json",
    "frontend/package.json",
    "frontend/package-lock.json",
    "frontend/tsconfig.json",
    "frontend/vite.config.ts",
    "frontend/index.html",
    "frontend/src/main.tsx",
    "design/functions.md",
    "design/erd.mmd",
    "design/ddl.sql",
    "design/rtm.csv",
    "design/manifest.json",
    "traceability.json",
    "README.md",
    "build-manifest.json",
}


ALLOWED = LEGACY_ALLOWED | {
    "design/revised/" + name
    for name in (
        "functions.md",
        "erd.mmd",
        "ddl.sql",
        "rtm.csv",
        "manifest.json",
        "executable-spec.json",
    )
}


V4_ALLOWED = ALLOWED | {"backend/commerce.py"}
CURRENT_ALLOWED = V4_ALLOWED | {"backend/domain.py"}


DELIVERY_ALLOWED = CURRENT_ALLOWED | set(EXTRA_TEMPLATES) | {"delivery.json"}
COMMAND_ALLOWED = DELIVERY_ALLOWED | set(COMMAND_TEMPLATES)
CALCULATION_ALLOWED = COMMAND_ALLOWED | set(CALCULATION_TEMPLATES)
SUPPORTED_FILE_SETS = (
    CALCULATION_ALLOWED,
    COMMAND_ALLOWED,
    DELIVERY_ALLOWED,
    CURRENT_ALLOWED,
    V4_ALLOWED,
    ALLOWED,
    LEGACY_ALLOWED,
)


def inspect_package(content: bytes, expected_hash: str) -> tuple[dict[str, bytes], dict[str, Any]]:
    if len(content) > 10 * 1024 * 1024 or hashlib.sha256(content).hexdigest() != expected_hash:
        raise ValueError("소스 크기 또는 신뢰한 소스 해시가 다릅니다")
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        entries = archive.infolist()
        if (
            len(entries) != len({e.filename for e in entries})
            or {e.filename for e in entries} not in SUPPORTED_FILE_SETS
            or sum(e.file_size for e in entries) > 10 * 1024 * 1024
            or any((e.external_attr >> 16) & 0o170000 != 0o100000 for e in entries)
        ):
            raise ValueError("허용되지 않는 ZIP 경로·중복·링크·크기")
        files = {e.filename: archive.read(e) for e in entries}
    manifest = json.loads(files["build-manifest.json"])
    hashes = {
        k: hashlib.sha256(v).hexdigest() for k, v in files.items() if k != "build-manifest.json"
    }
    if manifest.get("files") != hashes:
        raise ValueError("생성 파일 manifest 불일치")
    version = manifest.get("template_version")
    if version not in {
        "browser-preview-v1",
        "executable-design-v2",
        "executable-design-v3",
        "executable-design-v4",
        "executable-design-v5",
        "executable-design-v6",
        "executable-design-v7",
        "executable-design-v8",
        "executable-design-v9",
        "executable-design-v10",
        "executable-design-v11",
    }:
        raise ValueError("지원하지 않는 생성 템플릿 버전입니다")
    legacy = version == "browser-preview-v1"
    if set(files) != (
        CALCULATION_ALLOWED
        if version == "executable-design-v11"
        else COMMAND_ALLOWED
        if version == "executable-design-v10"
        else DELIVERY_ALLOWED
        if version == "executable-design-v9"
        else LEGACY_ALLOWED
        if legacy
        else CURRENT_ALLOWED
        if version
        in {
            "executable-design-v5",
            "executable-design-v6",
            "executable-design-v7",
            "executable-design-v8",
            "executable-design-v9",
            "executable-design-v10",
            "executable-design-v11",
        }
        else V4_ALLOWED
        if version == "executable-design-v4"
        else ALLOWED
    ):
        raise ValueError("템플릿 버전과 파일 목록이 다릅니다")
    runtime = TEMPLATES / (
        "legacy/browser-preview-v1/app.py.txt" if legacy else "runtime/app.py.txt"
    )
    if version in {
        "executable-design-v2",
        "executable-design-v3",
        "executable-design-v4",
        "executable-design-v5",
        "executable-design-v6",
        "executable-design-v7",
        "executable-design-v8",
        "executable-design-v9",
        "executable-design-v10",
    }:
        runtime = TEMPLATES / "legacy" / version / "app.py.txt"
    if (
        version
        in {
            "executable-design-v4",
            "executable-design-v5",
            "executable-design-v6",
            "executable-design-v7",
            "executable-design-v8",
            "executable-design-v9",
            "executable-design-v10",
            "executable-design-v11",
        }
        and files["backend/commerce.py"] != (TEMPLATES / "runtime/commerce.py.txt").read_bytes()
    ):
        raise ValueError("지원하는 업무 런타임 템플릿과 다릅니다")
    if version in {
        "executable-design-v5",
        "executable-design-v6",
        "executable-design-v7",
        "executable-design-v8",
        "executable-design-v9",
        "executable-design-v10",
        "executable-design-v11",
    }:
        domain_runtime = TEMPLATES / (
            f"legacy/{version}/domain.py.txt"
            if version
            in {
                "executable-design-v5",
                "executable-design-v6",
                "executable-design-v7",
                "executable-design-v8",
                "executable-design-v9",
                "executable-design-v10",
            }
            else "runtime/domain.py.txt"
        )
        if files["backend/domain.py"] != domain_runtime.read_bytes():
            raise ValueError("도메인 런타임 템플릿이 다릅니다")
    # 검증 실행은 신뢰한 고정 템플릿에 한정한다. 사용자 임의 Python 코드를 실행하지 않는다.
    if files["backend/app.py"] != runtime.read_bytes():
        raise ValueError("지원하는 런타임 템플릿과 다릅니다")
    if files["backend/inventory.py"] != (TEMPLATES / "runtime/inventory.py.txt").read_bytes():
        raise ValueError("지원하는 재고 런타임 템플릿과 다릅니다")
    for name in (
        "package.json",
        "package-lock.json",
        "tsconfig.json",
        "vite.config.ts",
        "index.html",
        "src/main.tsx",
    ):
        path = TEMPLATES / "frontend" / name
        if version != "executable-design-v11" and name == "src/main.tsx":
            path = TEMPLATES / "legacy" / version / "main.tsx"
        if files["frontend/" + name] != path.read_bytes():
            raise ValueError("지원하는 프런트엔드 템플릿과 다릅니다")
    if version in {
        "executable-design-v7",
        "executable-design-v8",
        "executable-design-v9",
        "executable-design-v10",
        "executable-design-v11",
    }:
        from specton.contracts.specification import SpecBundle
        from specton.specification.readiness import spec_hash

        spec = SpecBundle.model_validate_json(files["spec/approved-spec.json"])
        expected = [
            {"id": t.id, "req_ids": list(t.req_ids), **t.execution.model_dump(mode="json")}
            for t in spec.acceptance_cases
            if t.execution
        ]
        config = json.loads(files["backend/contract.json"])
        if (
            manifest["spec_hash"] != spec_hash(spec)
            or config.get("executable_cases", []) != expected
        ):
            raise ValueError("실행 인수 계약이 승인 명세·해시와 다릅니다")
    if version in {
        "executable-design-v8",
        "executable-design-v9",
        "executable-design-v10",
        "executable-design-v11",
    }:
        from specton.implementation.consistency import check

        check(files)
    if version in {"executable-design-v9", "executable-design-v10", "executable-design-v11"}:
        from specton.implementation.delivery import manifest as delivery_manifest

        for name, template in EXTRA_TEMPLATES.items():
            if files[name] != (TEMPLATES / template).read_bytes():
                raise ValueError("납품·인증 템플릿이 다릅니다")
        if json.loads(files["delivery.json"]) != delivery_manifest(spec):
            raise ValueError("납품 범위가 승인 명세와 다릅니다")
    if version in {"executable-design-v10", "executable-design-v11"}:
        for name, template in COMMAND_TEMPLATES.items():
            if version == "executable-design-v10" and name in {
                "backend/commands.py",
                "frontend/src/commands.tsx",
            }:
                template = "legacy/executable-design-v10/" + (
                    "commands.py.txt" if name.endswith(".py") else "commands.tsx"
                )
            if files[name] != (TEMPLATES / template).read_bytes():
                raise ValueError("명령 실행·화면 템플릿이 다릅니다")
    if version == "executable-design-v11":
        for name, template in CALCULATION_TEMPLATES.items():
            if files[name] != (TEMPLATES / template).read_bytes():
                raise ValueError("계산·집계 실행 템플릿이 다릅니다")
    return files, manifest


def docker(
    args: list[str], *, data: bytes | None = None, env: dict[str, str] | None = None
) -> bytes:
    result = subprocess.run(
        ["docker", *args],
        input=data,
        capture_output=True,
        timeout=60,
        env=None if env is None else {**os.environ, **env},
    )
    if result.returncode:
        # 실행 인수·stderr에는 작업 전용 비밀값이 있을 수 있으므로 출력하지 않는다.
        raise RuntimeError("Docker 단계 실패: " + args[0])
    if len(result.stdout) > 1024 * 1024:
        raise RuntimeError("검증 출력 한도 초과")
    return result.stdout


def verify(
    source: bytes,
    expected_hash: str,
    runtime_image: str,
    postgres_image: str,
    *,
    resource_key: str | None = None,
    browser_image: str | None = None,
    preview_lifetime: int = 0,
) -> dict[str, Any]:
    files, manifest = inspect_package(source, expected_hash)
    if preview_lifetime and (
        not browser_image or not resource_key or not 60 <= preview_lifetime <= 900
    ):
        raise ValueError("미리보기에는 작업 키와 브라우저 이미지, 60~900초 수명이 필요합니다")
    for image in (runtime_image, postgres_image, *([browser_image] if browser_image else [])):
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
            raise ValueError("로컬에서 준비한 불변 image ID를 지정하세요")
        if docker(["image", "inspect", image, "--format", "{{.Id}}"]).decode().strip() != image:
            raise ValueError("이미지 ID 불일치")
    suffix = uuid4().hex
    if resource_key is not None:
        from uuid import UUID

        resource_key = str(UUID(resource_key))
    labels = ["--label", "specton.verification=" + resource_key] if resource_key else []
    network = ""
    ingress = ""
    containers: list[str] = []
    admin_password, password, token, denied, non_cancel = (
        secrets.token_urlsafe(32) for _ in range(5)
    )
    config = json.loads(files["backend/contract.json"])
    stock_ops = config["inventory"]["operations"] if config.get("inventory") else []
    commerce_ops = config["commerce"]["operations"] if config.get("commerce") else []
    roles = sorted(
        {
            r
            for op in [
                *config["operations"],
                *stock_ops,
                *commerce_ops,
                *(config.get("domain", {}).get("operations", [])),
            ]
            for r in op["actor_roles"]
        }
    )
    cancel_roles = {r for op in stock_ops if op["action"] == "cancel" for r in op["actor_roles"]}
    hashes = {
        hashlib.sha256(token.encode()).hexdigest(): roles,
        hashlib.sha256(denied.encode()).hexdigest(): [],
        hashlib.sha256(non_cancel.encode()).hexdigest(): sorted(set(roles) - cancel_roles),
    }
    base = ["--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--cpus=1"]
    started = time.monotonic()
    report: dict[str, Any] = {
        "status": "failed",
        "source_hash": expected_hash,
        "spec_hash": manifest["spec_hash"],
        "runtime_image": runtime_image,
        "postgres_image": postgres_image,
        "suite_hash": suite_hash(),
        "business_acceptance": "not_run",
        "browser_acceptance": "not_run",
    }
    if browser_image:
        from specton.implementation.browser_runner import suite_hash as browser_suite_hash

        report.update(browser_image=browser_image, browser_suite_hash=browser_suite_hash())
    keep = False
    try:
        network = (
            docker(["network", "create", "--internal", *labels, "specton-verify-" + suffix])
            .decode()
            .strip()
        )
        db = (
            docker(
                [
                    "run",
                    "-d",
                    *labels,
                    "--network",
                    network,
                    "--network-alias",
                    "database",
                    *base,
                    "--user",
                    "999:999",
                    "--memory=512m",
                    "--pids-limit=128",
                    "--tmpfs",
                    "/var/lib/postgresql:rw,noexec,nosuid,size=512m,uid=999,gid=999",
                    "--tmpfs",
                    "/var/run/postgresql:rw,noexec,nosuid,size=16m,uid=999,gid=999",
                    "--tmpfs",
                    "/tmp:rw,noexec,nosuid,size=16m",
                    "-e",
                    "POSTGRES_USER=admin",
                    "-e",
                    "POSTGRES_PASSWORD",
                    postgres_image,
                    "-c",
                    "max_wal_size=64MB",
                    "-c",
                    "min_wal_size=32MB",
                ],
                env={"POSTGRES_PASSWORD": admin_password},
            )
            .decode()
            .strip()
        )
        containers.append(db)
        for _ in range(100):
            result = subprocess.run(
                ["docker", "exec", db, "pg_isready", "-h", "127.0.0.1", "-U", "admin"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                break
            time.sleep(0.2)
        else:
            raise RuntimeError("DB 준비 시간 초과")
        docker(
            ["exec", "-i", db, "psql", "-U", "admin", "-d", "postgres", "-v", "ON_ERROR_STOP=1"],
            data=(
                f"CREATE ROLE app LOGIN PASSWORD '{password}'; CREATE DATABASE generated OWNER app;"
            ).encode(),
        )
        app = (
            docker(
                [
                    "run",
                    "-d",
                    *labels,
                    "--network",
                    network,
                    *base,
                    "--user",
                    "1000:1000",
                    "--memory=256m",
                    "--pids-limit=64",
                    "--tmpfs",
                    "/workspace:rw,noexec,nosuid,size=32m,uid=1000,gid=1000",
                    "--tmpfs",
                    "/tmp:rw,noexec,nosuid,size=16m",
                    "-e",
                    "APP_DATABASE_URL",
                    "--network-alias",
                    "application",
                    "-e",
                    "APP_TOKEN_HASHES",
                    runtime_image,
                    *(["sleep", str(preview_lifetime + 120)] if preview_lifetime else []),
                ],
                env={
                    "APP_DATABASE_URL": f"postgresql://app:{password}@database:5432/generated",
                    "APP_TOKEN_HASHES": json.dumps(hashes),
                },
            )
            .decode()
            .strip()
        )
        containers.append(app)
        for name, expected_digest in suite_files().items():
            actual = docker(["exec", app, "sha256sum", "/runner/" + name]).decode().split()[0]
            if actual != expected_digest:
                raise RuntimeError("검증 이미지의 테스트 버전이 다릅니다")
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as archive:
            for name, content in files.items():
                if not name.startswith("backend/"):
                    continue
                entry = tarfile.TarInfo(name)
                entry.size = len(content)
                entry.mode = 0o444
                entry.uid = 1000
                entry.gid = 1000
                archive.addfile(entry, io.BytesIO(content))
        docker(
            [
                "exec",
                "-i",
                app,
                "python",
                "-c",
                "import sys,tarfile,pathlib; "
                "archive=tarfile.open(fileobj=sys.stdin.buffer,mode='r|'); "
                "\nfor member in archive:\n"
                " path=pathlib.Path('/workspace')/member.name; "
                "path.parent.mkdir(parents=True,exist_ok=True); "
                "path.write_bytes(archive.extractfile(member).read())",
            ],
            data=stream.getvalue(),
        )
        docker(["exec", app, "python", "/workspace/backend/app.py"])
        docker(
            [
                "exec",
                "-d",
                app,
                "uvicorn",
                "app:app",
                "--app-dir",
                "/workspace/backend",
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
                "--no-access-log",
            ]
        )
        for _ in range(60):
            result = subprocess.run(
                [
                    "docker",
                    "exec",
                    app,
                    "python",
                    "-c",
                    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=1)",
                ],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                break
            time.sleep(0.2)
        else:
            raise RuntimeError("API 준비 시간 초과")
        try:
            output = docker(
                [
                    "exec",
                    "-e",
                    "PROBE_TOKEN",
                    "-e",
                    "PROBE_DENIED_TOKEN",
                    "-e",
                    "PROBE_NON_CANCEL_TOKEN",
                    app,
                    "python",
                    "/runner/probe.py",
                ],
                env={
                    "PROBE_TOKEN": token,
                    "PROBE_DENIED_TOKEN": denied,
                    "PROBE_NON_CANCEL_TOKEN": non_cancel,
                },
            )
        except (RuntimeError, subprocess.TimeoutExpired):
            # Preserve completed cases if a later structural probe fails. Never mark the run passed.
            if config.get("executable_cases"):
                with suppress(RuntimeError, ValueError, subprocess.TimeoutExpired):
                    report["executable_acceptance"] = json.loads(
                        docker(["exec", app, "cat", "/workspace/scenario-report.json"])
                    )
            raise
        report.update(json.loads(output))
        if browser_image and report["status"] == "smoke_passed":
            from specton.implementation.browser_runner import run

            report["browser_acceptance"] = "failed"
            browser_report, html = run(
                files, network, browser_image, labels, token, non_cancel, bool(preview_lifetime)
            )
            report["browser"] = browser_report
            report["browser_acceptance"] = "passed"
            if preview_lifetime:
                ingress = (
                    docker(["network", "create", *labels, "specton-preview-ingress-" + suffix])
                    .decode()
                    .strip()
                )
                gateway = (
                    docker(
                        [
                            "run",
                            "-d",
                            *labels,
                            "--network",
                            ingress,
                            *base,
                            "--user",
                            "1000:1000",
                            "--memory=128m",
                            "--pids-limit=32",
                            "-p",
                            "127.0.0.1::8000",
                            "-e",
                            "PREVIEW_TOKEN",
                            browser_image,
                            "node",
                            "/runner/gateway.mjs",
                        ],
                        env={"PREVIEW_TOKEN": token},
                    )
                    .decode()
                    .strip()
                )
                containers.append(gateway)
                docker(["network", "connect", network, gateway])
                port = int(docker(["port", gateway, "8000/tcp"]).decode().strip().rsplit(":", 1)[1])
                report["_preview"] = {"port": port, "html": html, "access_token": token}
                keep = True
    except (RuntimeError, ValueError, subprocess.TimeoutExpired):
        report["status"] = "failed"
        report["error"] = (
            "격리 DB/API 검사 실패 또는 시간 초과. "
            "비밀값이 포함될 수 있는 내부 로그는 게시하지 않습니다."
        )
    finally:
        cleanup = True
        for container in reversed(containers if not keep else []):
            try:
                docker(["rm", "--force", "--volumes", container])
            except (RuntimeError, subprocess.TimeoutExpired):
                cleanup = False
        for target_network in [ingress, network] if not keep else []:
            if target_network:
                try:
                    docker(["network", "rm", target_network])
                except (RuntimeError, subprocess.TimeoutExpired):
                    cleanup = False
        report["cleanup_complete"] = cleanup and not keep
        if not cleanup:
            report["status"] = "failed"
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    from specton.contracts.specification import SpecBundle
    from specton.implementation.requirement_results import requirement_results

    report["requirements"] = requirement_results(
        SpecBundle.model_validate_json(files["spec/approved-spec.json"]),
        report.get("checks", []),
        report.get("executable_acceptance"),
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--expected-source-hash", required=True)
    parser.add_argument("--runtime-image", required=True)
    parser.add_argument("--postgres-image", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--resource-key")
    parser.add_argument("--browser-image")
    parser.add_argument("--preview-lifetime", type=int, default=0)
    args = parser.parse_args()
    if args.resource_key:

        def timeout(signum: int, frame: Any) -> None:
            raise TimeoutError("검증 실행 제한 시간 초과")

        signal.signal(signal.SIGALRM, timeout)
        signal.alarm(360)
    report = verify(
        args.archive.read_bytes(),
        args.expected_source_hash,
        args.runtime_image,
        args.postgres_image,
        resource_key=args.resource_key,
        browser_image=args.browser_image,
        preview_lifetime=args.preview_lifetime,
    )
    args.report.write_bytes(json_bytes(report))
    print(json.dumps({"status": report["status"], "cleanup_complete": report["cleanup_complete"]}))
    raise SystemExit(0 if report["status"] == "smoke_passed" else 1)


if __name__ == "__main__":
    main()
