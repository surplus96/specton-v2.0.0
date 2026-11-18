"""Real session auth and browser submission against an installed atomic-command package."""

import hashlib
import json
import os
import secrets
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import pytest

from specton.implementation.verify import docker, inspect_package

pytestmark = [
    pytest.mark.docker_browser,
    pytest.mark.skipif(
        os.environ.get("SPECTON_TEST_COMMAND_UI") != "1",
        reason="explicit installed UI run required",
    ),
]


def test_delivered_command_ui_rollback_and_retry():
    image = os.environ["SPECTON_TEST_DELIVERY_IMAGE"]
    browser = os.environ["SPECTON_TEST_BROWSER_IMAGE"]
    postgres = os.environ["SPECTON_TEST_WORKER_POSTGRES"]
    domain = "inventory"
    root = Path(
        os.environ.get("SPECTON_TEST_DELIVERY_ROOT", "var/test-results/atomic-commands/20261116")
    ).resolve()
    source = (root / (domain + ".zip")).read_bytes()
    source_hash = hashlib.sha256(source).hexdigest()
    files, manifest = inspect_package(source, source_hash)
    config = json.loads(files["backend/contract.json"])
    parent, child = (t["physical_name"] for t in config["domain"]["tables"])
    output = root / (domain + "-browser")
    output.mkdir(exist_ok=True)
    output.chmod(0o777)
    for value in (image, browser, postgres):
        assert (
            value.startswith("sha256:")
            and docker(["image", "inspect", value, "--format", "{{.Id}}"]).decode().strip() == value
        )
    password, admin_password = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    user_password = "synthetic-delivery-browser-password"
    network = (
        docker(["network", "create", "--internal", "specton-delivery-" + uuid4().hex])
        .decode()
        .strip()
    )
    containers = []
    base = ["--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--cpus=1"]

    def run(args, env=None):
        cid = docker(["run", "-d", "--network", network, *args], env=env).decode().strip()
        containers.append(cid)
        return cid

    def sql(dbname, query):
        return docker(
            ["exec", "-i", db, "psql", "-U", "admin", "-d", dbname, "-v", "ON_ERROR_STOP=1", "-At"],
            data=query.encode(),
        )

    try:
        db = run(
            [
                *base,
                "--user",
                "999:999",
                "--network-alias",
                "database",
                "--memory=512m",
                "--pids-limit=128",
                "--tmpfs",
                "/var/lib/postgresql:rw,size=512m,uid=999,gid=999",
                "--tmpfs",
                "/var/run/postgresql:rw,size=16m,uid=999,gid=999",
                "--tmpfs",
                "/tmp:rw,size=32m",
                "-e",
                "POSTGRES_USER=admin",
                "-e",
                "POSTGRES_DB=generated",
                "-e",
                "POSTGRES_PASSWORD",
                postgres,
            ],
            {"POSTGRES_PASSWORD": admin_password},
        )
        for _ in range(60):
            try:
                docker(
                    ["exec", db, "pg_isready", "-h", "127.0.0.1", "-U", "admin", "-d", "generated"]
                )
                break
            except RuntimeError:
                time.sleep(0.25)
        else:
            pytest.fail("Disposable database did not become ready")
        sql(
            "generated",
            f"CREATE ROLE app LOGIN PASSWORD '{password}' NOSUPERUSER NOCREATEDB NOCREATEROLE;\n"
            "ALTER DATABASE generated OWNER TO app;\n",
        )
        env = {
            "APP_DATABASE_URL": f"postgresql://app:{password}@database:5432/generated",
            "APP_AUTH_MODE": "session",
            "APP_ORIGIN": "http://127.0.0.1:4173",
            "APP_COOKIE_SECURE": "false",
        }
        app_args = [
            *base,
            "--memory=256m",
            "--pids-limit=64",
            "--tmpfs",
            "/tmp:rw,size=16m",
            *[item for key in env for item in ("-e", key)],
            image,
            "sleep",
            "600",
        ]
        app = run(["--network-alias", "application", *app_args], env)
        expected = {
            n.removeprefix("backend/"): hashlib.sha256(v).hexdigest()
            for n, v in files.items()
            if n.startswith("backend/")
        }
        observed = json.loads(
            docker(
                [
                    "exec",
                    "-i",
                    app,
                    "python",
                    "-c",
                    "import json,hashlib,sys,pathlib; names=json.load(sys.stdin); "
                    "print(json.dumps({n:hashlib.sha256(pathlib.Path(n).read_bytes()).hexdigest() "
                    "for n in names}))",
                ],
                data=json.dumps(list(expected)).encode(),
            )
        )
        assert observed == expected  # image is bound to the inspected delivery source
        docker(["exec", app, "python", "manage.py", "init-db"])
        for username, role in (("operator", "ROLE-operator"), ("administrator", "ROLE-admin")):
            docker(
                ["exec", "-i", app, "python", "manage.py", "set-user", username, "--role", role],
                data=(user_password + "\n" + user_password + "\n").encode(),
            )
        docker(
            [
                "exec",
                "-d",
                app,
                "uvicorn",
                "serve:app",
                "--host",
                "0.0.0.0",
                "--port",
                "8080",
                "--no-access-log",
            ]
        )
        for _ in range(50):
            try:
                docker(
                    [
                        "exec",
                        app,
                        "python",
                        "-c",
                        "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=1)",
                    ]
                )
                break
            except RuntimeError:
                time.sleep(0.1)
        script = Path("tests/browser/atomic-commands.mjs").resolve()
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-i",
                "--network",
                network,
                *base,
                "--memory=1g",
                "--pids-limit=256",
                "--shm-size=256m",
                "--tmpfs",
                "/tmp:rw,size=256m",
                "-v",
                str(script) + ":/runner/atomic-commands.mjs:ro",
                "-v",
                str(output) + ":/out",
                browser,
                "node",
                "/runner/atomic-commands.mjs",
            ],
            input=json.dumps(
                {"config": config, "password": user_password, "parent": parent, "child": child}
            ).encode(),
            capture_output=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stderr.decode()[-6000:]
        report = json.loads((output / "report.json").read_text())
        assert report["status"] == "passed"
        assert sql("generated", "SELECT amount FROM balances").strip() == b"3.00"
        assert sql("generated", "SELECT count(*) FROM movements").strip() == b"1"
        assert (
            sql(
                "generated",
                "SELECT count(*) FROM _specton_commands WHERE scope LIKE '%:API-atomic:%'",
            ).strip()
            == b"1"
        )
        report.update(
            source_hash=source_hash,
            template_version=manifest["template_version"],
            image=image,
            browser_image=browser,
            postgres_image=postgres,
            cleanup_complete=False,
        )
    finally:
        for cid in reversed(containers):
            docker(["rm", "--force", "--volumes", cid])
        docker(["network", "rm", network])
    report["cleanup_complete"] = True
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
