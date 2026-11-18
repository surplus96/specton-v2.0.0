"""Real delivered auth/API/PostgreSQL; every test owns a disposable schema."""

import hashlib
import importlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest
from command_support import atomic_case
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

from specton.implementation.package import generate
from specton.implementation.verify import inspect_package

pytestmark = pytest.mark.db
ORIGIN = "http://localhost:8080"
PASSWORD = "fixed-command-test-password-2030"


@pytest.fixture(params=["inventory", "maintenance"])
def application(request, pool, tmp_path, monkeypatch):
    domain = request.param
    factory = atomic_case
    if isinstance(domain, tuple):
        from calculation_support import calculated_command, calculation_case

        domain, kind = domain
        factory = calculation_case if kind == "query" else calculated_command
    bundle, state, artifacts = factory(domain)
    source = generate(bundle, state, artifacts)
    files, manifest = inspect_package(source, hashlib.sha256(source).hexdigest())
    for name, value in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
    schema = "command_test_" + uuid4().hex
    with psycopg.connect(pool.conninfo, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        dsn = make_conninfo(pool.conninfo, options="-csearch_path=" + schema)
        monkeypatch.setenv("APP_DATABASE_URL", dsn)
        monkeypatch.setenv("APP_AUTH_MODE", "session")
        monkeypatch.setenv("APP_ORIGIN", ORIGIN)
        monkeypatch.setenv("APP_COOKIE_SECURE", "false")
        monkeypatch.delenv("APP_TOKEN_HASHES", raising=False)
        monkeypatch.syspath_prepend(str(tmp_path / "backend"))
        names = (
            "app",
            "auth",
            "domain",
            "commands",
            "calculations",
            "inventory",
            "commerce",
            "serve",
        )
        old = {n: sys.modules.pop(n) for n in names if n in sys.modules}
        try:
            initialized = subprocess.run(
                [sys.executable, str(tmp_path / "backend/manage.py"), "init-db"],
                capture_output=True,
                timeout=30,
            )
            assert initialized.returncode == 0, initialized.stderr.decode()
            auth = importlib.import_module("auth")
            config = json.loads(files["backend/contract.json"])["domain"]
            with psycopg.connect(dsn) as conn:
                for username, roles in (
                    ("administrator", ["ROLE-admin"]),
                    ("operator", ["ROLE-operator"]),
                ):
                    auth.save_user(
                        conn, json.loads(files["backend/contract.json"]), username, PASSWORD, roles
                    )
            api = importlib.import_module("serve").app
            with TestClient(api, base_url=ORIGIN) as client:
                result = {
                    "client": client,
                    "dsn": dsn,
                    "config": config,
                    "domain": domain,
                    "manifest": manifest,
                    "spec": bundle,
                    "app": api,
                }
                result["admin_headers"] = login(client, "administrator")
                parent, child = config["tables"]
                parent_row = {"id": "one", "name": "fixture", "amount": "5.00"}
                child_row = {
                    "parent_id": "one",
                    "sequence": 1,
                    "scheduled": "2030-01-01",
                    "status": "open",
                    "amount": "0.00",
                }
                result.update(
                    parent=parent["physical_name"],
                    child=child["physical_name"],
                    original_parent=parent_row,
                    original_child=child_row,
                )
                for table, row in ((parent, parent_row), (child, child_row)):
                    if table == child and domain == "inventory":
                        continue
                    op = next(
                        o
                        for o in config["operations"]
                        if o["table_id"] == table["id"] and o["action"] == "insert"
                    )
                    seeded = client.post(
                        "/api" + op["path"],
                        json=row,
                        headers={**result["admin_headers"], "Idempotency-Key": op["id"]},
                    )
                    assert seeded.status_code == 200, seeded.text
                result["headers"] = login(client, "operator")
                yield result
        finally:
            for n in names:
                sys.modules.pop(n, None)
            sys.modules.update(old)
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def login(client, username):
    r = client.post(
        "/api/auth/login",
        json={"username": username, "password": PASSWORD},
        headers={"Origin": ORIGIN},
    )
    assert r.status_code == 200, r.text
    return {"Origin": ORIGIN, "X-CSRF-Token": r.json()["user"]["csrf"]}


def submit(a, *, amount="2.00", sequence=1, key="atomic", headers=None, **extra):
    return a["client"].post(
        "/api/commands/save",
        json={
            "id": "one",
            "sequence": sequence,
            "scheduled": "2030-01-01",
            "amount": amount,
            **extra,
        },
        headers={**(a["headers"] if headers is None else headers), "Idempotency-Key": key},
    )


def observed(a):
    with psycopg.connect(a["dsn"], row_factory=dict_row) as conn:
        parent = conn.execute(
            sql.SQL("SELECT * FROM {}").format(sql.Identifier(a["parent"]))
        ).fetchall()
        child = conn.execute(
            sql.SQL("SELECT * FROM {} ORDER BY sequence").format(sql.Identifier(a["child"]))
        ).fetchall()
        commands = conn.execute(
            "SELECT count(*) AS n FROM _specton_commands WHERE scope LIKE %s", ("%:API-atomic:%",)
        ).fetchone()["n"]
        return parent, child, commands


def test_normal_retry_conflict_and_real_role_csrf_guards(application):
    a = application
    assert submit(a, headers={}).status_code == 403
    record = next(o for o in a["config"]["operations"] if o["action"] == "update")
    assert (
        a["client"]
        .post(
            "/api" + record["path"],
            json=a["original_parent"],
            headers={**a["headers"], "Idempotency-Key": "bypass"},
        )
        .status_code
        == 403
    )
    result = submit(a)
    assert result.status_code == 200, result.text
    assert submit(a).json() == result.json()
    assert submit(a, amount="3.00").status_code == 409
    parent, child, count = observed(a)
    assert str(parent[0]["amount"]) == ("3.00" if a["domain"] == "inventory" else "2.00")
    assert len(child) == 1 and str(child[0]["amount"]) == "2.00" and count == 1
    login(a["client"], "administrator")
    assert submit(a, headers=login(a["client"], "administrator")).status_code == 403


def test_second_write_db_error_rolls_back_rows_and_idempotency_then_retry_succeeds(application):
    a = application
    before = observed(a)
    with psycopg.connect(a["dsn"]) as conn:
        conn.execute(
            "CREATE FUNCTION fail_second_write() RETURNS trigger LANGUAGE plpgsql AS $$ "
            "BEGIN RAISE EXCEPTION 'synthetic fault' USING ERRCODE='23514'; END $$"
        )
        conn.execute(
            sql.SQL(
                "CREATE TRIGGER injected_fault BEFORE INSERT OR UPDATE ON {} "
                "FOR EACH ROW EXECUTE FUNCTION fail_second_write()"
            ).format(sql.Identifier(a["child"]))
        )
    result = submit(a, key="retry-after-failure")
    assert result.status_code == 422 and result.json()["detail"] == "CONSTRAINT_VIOLATION"
    assert observed(a) == before
    with psycopg.connect(a["dsn"]) as conn:
        conn.execute(
            sql.SQL("DROP TRIGGER injected_fault ON {}").format(sql.Identifier(a["child"]))
        )
        conn.execute("DROP FUNCTION fail_second_write()")
    assert submit(a, key="retry-after-failure").status_code == 200
    assert observed(a)[2] == 1


def test_after_condition_failure_rolls_back_both_writes_and_failed_key_is_reusable(application):
    a = application
    before = observed(a)
    bad = submit(a, amount="6.00" if a["domain"] == "inventory" else "101.00")
    assert bad.status_code == 409 and bad.json()["detail"] == "RULE_VIOLATION"
    assert observed(a) == before
    assert submit(a).status_code == 200
    assert observed(a)[2] == 1


def test_concurrent_commands_do_not_lose_updates_or_double_apply(application):
    a = application
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda n: submit(
                    a,
                    amount="3.00",
                    sequence=n + 1 if a["domain"] == "inventory" else 1,
                    key=f"parallel-{n}",
                ),
                range(2),
            )
        )
    assert sorted(r.status_code for r in results) == [200, 409], [r.text for r in results]
    parent, child, count = observed(a)
    assert str(parent[0]["amount"]) == ("2.00" if a["domain"] == "inventory" else "3.00")
    assert len(child) == 1 and count == 1


def test_concurrent_same_key_replays_one_committed_result(application):
    a = application
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(lambda _: submit(a, key="same"), range(3)))
    assert all(r.status_code == 200 for r in results), [r.text for r in results]
    assert all(r.json() == results[0].json() for r in results)
    assert observed(a)[2] == 1


def test_locked_record_times_out_without_effect_and_retry_uses_same_key(application):
    a = application
    before = observed(a)
    with psycopg.connect(a["dsn"]) as blocker:
        blocker.execute(sql.SQL("SELECT * FROM {} FOR UPDATE").format(sql.Identifier(a["parent"])))
        result = submit(a, key="locked")
        assert result.status_code == 409 and result.json()["detail"] == "COMMAND_TIMEOUT"
    assert observed(a) == before
    assert submit(a, key="locked").status_code == 200
