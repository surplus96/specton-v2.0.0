"""Real generated customer API/DB, isolated credentials and disposable schemas."""

import hashlib
import importlib
import json
import subprocess
import sys
from uuid import uuid4

import psycopg
import pytest
from customer_support import customer
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import make_conninfo

from specton.implementation.package import generate
from specton.implementation.verify import inspect_package

pytestmark = pytest.mark.db
PASSWORD = "synthetic-customer-password-2026"
ORIGIN = "http://localhost:8080"


@pytest.fixture
def delivered(pool, tmp_path, monkeypatch):
    bundle, state, artifacts = customer()
    source = generate(bundle, state, artifacts)
    files, _ = inspect_package(source, hashlib.sha256(source).hexdigest())
    for name, data in files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    schema = "customer_test_" + uuid4().hex
    with psycopg.connect(pool.conninfo, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        dsn = make_conninfo(pool.conninfo, options="-csearch_path=" + schema)
        monkeypatch.setenv("APP_DATABASE_URL", dsn)
        monkeypatch.setenv("APP_AUTH_MODE", "session")
        monkeypatch.setenv("APP_ORIGIN", ORIGIN)
        monkeypatch.setenv("APP_COOKIE_SECURE", "false")
        monkeypatch.delenv("APP_TOKEN_HASHES", raising=False)
        monkeypatch.syspath_prepend(str(tmp_path / "backend"))
        modules = ("app", "auth", "domain", "inventory", "commerce", "serve")
        old = {name: sys.modules.pop(name) for name in modules if name in sys.modules}
        try:
            initialized = subprocess.run(
                [sys.executable, str(tmp_path / "backend/manage.py"), "init-db"],
                capture_output=True,
                timeout=30,
            )
            assert initialized.returncode == 0, initialized.stderr.decode()
            auth = importlib.import_module("auth")
            config = json.loads(files["backend/contract.json"])
            with psycopg.connect(dsn) as conn:
                auth.save_user(conn, config, "operator", PASSWORD, ["ROLE-user"])
                auth.save_user(conn, config, "reader", PASSWORD, ["ROLE-reader"])
            api = importlib.import_module("serve").app
            with TestClient(api, base_url=ORIGIN) as client:
                yield {
                    "client": client,
                    "auth": auth,
                    "config": config,
                    "dsn": dsn,
                    "root": tmp_path,
                    "schema": schema,
                    "source": source,
                    "files": files,
                }
        finally:
            for name in modules:
                sys.modules.pop(name, None)
            sys.modules.update(old)
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
            assert not admin.execute(
                "SELECT 1 FROM pg_namespace WHERE nspname=%s", (schema,)
            ).fetchone()


def login(delivered, username="operator"):
    client = delivered["client"]
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": PASSWORD},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 200, response.text
    return {
        "Origin": ORIGIN,
        "X-CSRF-Token": response.json()["user"]["csrf"],
        "Idempotency-Key": str(uuid4()),
    }


def operations(delivered):
    return {
        o["action"]: o
        for o in delivered["config"]["domain"]["operations"]
        if o["table"] == "devices"
    }


def test_login_csrf_roles_reload_logout_and_revocation(delivered):
    client, auth = delivered["client"], delivered["auth"]
    ops = operations(delivered)
    path = "/api" + ops["insert"]["path"]
    payload = {"id": "M1", "name": "설비 보존"}
    assert client.get("/api" + ops["list"]["path"]).status_code == 401
    assert (
        client.post(
            "/api/auth/login", json={"username": "operator", "password": PASSWORD}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/auth/login",
            json={"username": "operator", "password": "wrong"},
            headers={"Origin": ORIGIN},
        ).status_code
        == 401
    )
    headers = login(delivered)
    saved_cookie = client.cookies.get(auth.COOKIE)
    assert saved_cookie and len(saved_cookie) == 43
    assert client.get("/api/auth/session").json()["user"]["username"] == "operator"
    for bad in (
        {"Origin": ORIGIN},
        {**headers, "Origin": "http://evil.example"},
        {**headers, "X-CSRF-Token": "wrong"},
    ):
        assert (
            client.post(
                path, json=payload, headers={"Idempotency-Key": "blocked", **bad}
            ).status_code
            == 403
        )
    assert client.post(path, json=payload, headers=headers).status_code == 200
    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    client.cookies.set(auth.COOKIE, saved_cookie)
    assert client.get("/api" + ops["list"]["path"]).status_code == 401
    client.cookies.clear()
    reader = login(delivered, "reader")
    assert client.get("/api" + ops["list"]["path"]).json() == [payload]
    assert client.post(path, json={"id": "M2", "name": "거절"}, headers=reader).status_code == 403
    with psycopg.connect(delivered["dsn"]) as conn:
        auth.save_user(conn, delivered["config"], "reader", PASSWORD + "reset", ["ROLE-reader"])
    assert client.get("/api" + ops["list"]["path"]).status_code == 401
    login(delivered)
    with psycopg.connect(delivered["dsn"]) as conn:
        conn.execute("UPDATE _specton_sessions SET expires_at=now()-interval '1 second'")
    assert client.get("/api" + ops["list"]["path"]).status_code == 401


def test_search_paging_relations_failed_write_and_account_admin(delivered):
    client = delivered["client"]
    headers = login(delivered)
    ops = operations(delivered)
    for i in range(25):
        response = client.post(
            "/api" + ops["insert"]["path"],
            json={"id": f"M{i:02}", "name": "정밀%설비" if i == 0 else f"설비 {i:02}"},
            headers={**headers, "Idempotency-Key": str(i)},
        )
        assert response.status_code == 200
    query = "/api" + ops["list"]["path"]
    first = client.get(query + "?limit=20").json()
    second = client.get(query + "?limit=20&offset=20").json()
    assert len(first) == 20 and len(second) == 5
    assert len({r["id"] for r in first + second}) == 25
    assert client.get(query, params={"q": "%"}).json() == [first[0]]
    assert client.get(query, params={"q": "' OR 1=1 --"}).json() == []
    for params in ({"limit": 101}, {"offset": -1}, {"q": "x" * 101}):
        assert client.get(query, params=params).status_code == 422
    child = next(
        o
        for o in delivered["config"]["domain"]["operations"]
        if o["table"] == "inspections" and o["action"] == "insert"
    )
    record = {
        "parent_id": "missing",
        "sequence": 1,
        "scheduled": "2026-11-16",
        "status": "pending",
        "amount": "12.50",
    }
    headers["Idempotency-Key"] = "relation-retry"
    assert client.post("/api" + child["path"], json=record, headers=headers).status_code == 409
    record["parent_id"] = "M00"
    assert client.post("/api" + child["path"], json=record, headers=headers).json() == record
    result = subprocess.run(
        [sys.executable, str(delivered["root"] / "backend/manage.py"), "disable-user", "operator"],
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 0
    assert client.get(query).status_code == 401


def test_delivery_hash_init_rollback_password_storage_and_rate_limit(delivered):
    root, auth = delivered["root"], delivered["auth"]
    verify = [sys.executable, str(root / "verify_delivery.py")]
    assert subprocess.run(verify, capture_output=True).returncode == 0
    result = subprocess.run(
        [sys.executable, str(root / "backend/manage.py"), "init-db"],
        capture_output=True,
        timeout=30,
    )
    assert result.returncode != 0  # never overwrite an initialized customer DB
    with psycopg.connect(delivered["dsn"]) as conn:
        values = conn.execute(
            "SELECT password_hash FROM _specton_users ORDER BY username"
        ).fetchall()
        assert values[0][0] != values[1][0] and all(PASSWORD not in row[0] for row in values)
        with pytest.raises(ValueError):
            auth.save_user(conn, delivered["config"], "forged", PASSWORD, ["ROLE-unknown"])
    headers = login(delivered)
    assert delivered["client"].get("/api/auth/session").json()["user"]
    for _ in range(9):
        assert (
            delivered["client"]
            .post(
                "/api/auth/login",
                json={"username": "no-account", "password": "wrong"},
                headers={"Origin": ORIGIN},
            )
            .status_code
            == 401
        )
    assert (
        delivered["client"]
        .post(
            "/api/auth/login", json={"username": "operator", "password": PASSWORD}, headers=headers
        )
        .status_code
        == 429
    )
    (root / "backend/auth.py").write_text("modified")
    assert subprocess.run(verify, capture_output=True).returncode != 0


def test_persistent_session_new_server_and_secure_cookie_configuration(delivered, monkeypatch):
    login(delivered)
    auth, config, dsn = delivered["auth"], delivered["config"], delivered["dsn"]
    restarted = FastAPI()
    auth.install(restarted, config, dsn)
    with TestClient(restarted, base_url=ORIGIN) as client:
        client.cookies.update(delivered["client"].cookies)
        assert client.get("/auth/session").json()["user"]["username"] == "operator"
    for origin, secure in (
        ("http://public.example", "false"),
        ("https://app.example", "false"),
        ("https://app.example/path", "true"),
    ):
        monkeypatch.setenv("APP_ORIGIN", origin)
        monkeypatch.setenv("APP_COOKIE_SECURE", secure)
        with pytest.raises(ValueError):
            auth.install(FastAPI(), config, dsn)
    monkeypatch.setenv("APP_ORIGIN", "https://app.example")
    monkeypatch.setenv("APP_COOKIE_SECURE", "true")
    secure_app = FastAPI()
    auth.install(secure_app, config, dsn)
    with TestClient(secure_app, base_url="https://app.example") as client:
        response = client.post(
            "/auth/login",
            json={"username": "operator", "password": PASSWORD},
            headers={"Origin": "https://app.example"},
        )
        assert response.status_code == 200
        assert all(
            flag in response.headers["set-cookie"].lower()
            for flag in ("secure", "httponly", "samesite=strict")
        )
        assert response.headers["cache-control"] == "no-store"
