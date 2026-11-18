"""Actual PostgreSQL and generated HTTP runtime; only disposable schemas and fixed data."""

import importlib.machinery
import importlib.util
import json
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import make_conninfo
from transfer_support import change

from specton.implementation.data_transfer import COMMANDS_DDL, transfer
from specton.implementation.domain import compile_domain

pytestmark = pytest.mark.db


@contextmanager
def pair(pool, artifacts):
    root = "specton_transfer_" + uuid4().hex
    schemas = [root + "_before", root + "_after"]
    with psycopg.connect(pool.conninfo, autocommit=True) as conn:
        try:
            for schema in schemas:
                conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
                conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
                with conn.transaction():
                    conn.execute(artifacts["ddl.sql"].decode(), prepare=False)
                    conn.execute(COMMANDS_DDL)
            yield conn, schemas
        finally:
            for schema in schemas:
                conn.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema))
                )
            assert not conn.execute(
                "SELECT 1 FROM pg_namespace WHERE nspname=ANY(%s)", (schemas,)
            ).fetchall()


def app(pool, schema, bundle, state):
    path = Path("specton/implementation/templates/runtime/domain.py.txt")
    loader = importlib.machinery.SourceFileLoader("transfer_runtime", str(path))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    config = compile_domain(bundle, state)["domain"]
    api = FastAPI()
    module.register(
        api,
        config,
        make_conninfo(pool.conninfo, options=f"-csearch_path={schema}"),
        lambda request, roles: "synthetic-transfer-user",
    )
    return TestClient(api), config


def post(client, op, payload, key):
    return client.post(op["path"], json=payload, headers={"Idempotency-Key": key})


def fill(client, config):
    parent = next(
        o for o in config["operations"] if o["action"] == "insert" and len(o["fields"]) == 2
    )
    child = next(
        o for o in config["operations"] if o["action"] == "insert" and len(o["fields"]) == 5
    )
    record = {
        "parent_id": "P1",
        "sequence": 1,
        "scheduled": "2026-11-16",
        "status": "pending",
        "amount": "12.50",
    }
    assert (
        post(client, parent, {"id": "P1", "name": "원본 고객 데이터"}, "parent").status_code == 200
    )
    assert post(client, child, record, "child").json() == record
    return child, record


@pytest.mark.parametrize("domain", ["booking", "maintenance"])
def test_preserves_values_relations_commands_and_applies_new_rules_to_future_writes(
    pool, domain, record_property
):
    before, after, state, artifacts, _, _, plan, _ = change(domain)
    with pair(pool, artifacts) as (conn, (source, target)):
        old, config = app(pool, source, before, state)
        child, record = fill(old, config)
        report = transfer(conn, plan, source, target)
        assert report["source_unchanged"] and report["cutover"] == "not_run"
        assert sum(t["rows"] for t in report["tables"].values()) == 4  # two rows + two commands
        new, newconfig = app(pool, target, after, state)
        read = next(
            o
            for o in newconfig["operations"]
            if o["action"] == "list" and o["table_id"] == child["table_id"]
        )
        update = next(
            o
            for o in newconfig["operations"]
            if o["action"] == "update" and o["table_id"] == child["table_id"]
        )
        assert new.get(read["path"]).json() == [record]
        # A completed command is replayed; a NEW write is checked against the new policy.
        assert post(new, child, record, "child").json() == record
        rejected = post(new, update, record, "change")
        assert rejected.status_code == 409 and rejected.json()["detail"] == "RULE_VIOLATION"
        assert new.get(read["path"]).json() == [record]
        corrected = {**record, "amount": "9.00"}
        assert post(new, update, corrected, "change").json() == corrected
        assert old.get(read["path"]).json() == [record]  # old version stays recoverable
        with pytest.raises(ValueError, match="비어 있지"):
            transfer(conn, plan, source, target)
    record_property("domain", domain)
    record_property("plan", json.dumps(plan, ensure_ascii=False, sort_keys=True))
    record_property("transfer", json.dumps(report, ensure_ascii=False, sort_keys=True))
    record_property("temporary_schemas_removed", True)


@pytest.mark.parametrize("fault", [1, 2, 3])
def test_mid_transfer_failure_rolls_back_all_rows_and_same_plan_can_retry(
    pool, fault, record_property
):
    before, _after, state, artifacts, _, _, plan, _ = change("maintenance")
    with pair(pool, artifacts) as (conn, (source, target)):
        old, config = app(pool, source, before, state)
        child, record = fill(old, config)
        with pytest.raises(RuntimeError, match="INJECTED_TRANSFER_FAILURE"):
            transfer(conn, plan, source, target, fault_after_tables=fault)
        for table in plan["tables"]:
            assert (
                conn.execute(
                    sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(target, table["name"]))
                ).fetchone()[0]
                == 0
            )
        read = next(
            o
            for o in config["operations"]
            if o["action"] == "list" and o["table_id"] == child["table_id"]
        )
        assert old.get(read["path"]).json() == [record]
        assert transfer(conn, plan, source, target)["status"] == "passed"
    record_property("fault_after_tables", fault)
    record_property("rollback_and_retry", "passed")
    record_property("temporary_schemas_removed", True)


def test_schema_drift_and_wrong_plan_fail_before_copy(pool):
    before, _, state, artifacts, _, _, plan, _ = change()
    with pair(pool, artifacts) as (conn, (source, target)):
        old, config = app(pool, source, before, state)
        fill(old, config)
        with pytest.raises(ValueError, match="고정 계획"):
            transfer(conn, {**plan, "source_hash": "0" * 64}, source, target)
        with pytest.raises(ValueError, match="고정 계획"):
            transfer(conn, plan, source, source)
        conn.execute(
            sql.SQL("ALTER TABLE {} ADD COLUMN unexpected text").format(
                sql.Identifier(target, plan["tables"][0]["name"])
            )
        )
        with pytest.raises(ValueError, match="구조"):
            transfer(conn, plan, source, target)


def test_writer_lock_timeout_rolls_back_and_allows_retry(pool):
    before, _, state, artifacts, _, _, plan, _ = change()
    with pair(pool, artifacts) as (conn, (source, target)):
        old, config = app(pool, source, before, state)
        fill(old, config)
        with psycopg.connect(pool.conninfo) as writer:
            writer.execute(
                sql.SQL("LOCK TABLE {} IN ROW EXCLUSIVE MODE").format(
                    sql.Identifier(source, plan["tables"][0]["name"])
                )
            )
            with pytest.raises(psycopg.errors.LockNotAvailable):
                transfer(conn, plan, source, target)
        assert transfer(conn, plan, source, target)["status"] == "passed"


def test_matching_unapproved_column_types_are_still_rejected(pool):
    _, _, _, artifacts, _, _, plan, _ = change()
    with pair(pool, artifacts) as (conn, (source, target)):
        for schema in (source, target):
            conn.execute(
                sql.SQL("ALTER TABLE {} ALTER COLUMN name TYPE varchar(40)").format(
                    sql.Identifier(schema, plan["tables"][0]["name"])
                )
            )
        with pytest.raises(ValueError, match="자료형"):
            transfer(conn, plan, source, target)
