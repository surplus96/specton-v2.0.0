import importlib.machinery
import importlib.util
from pathlib import Path

import pytest
from domain_support import case, reviewed, with_transition
from fastapi import FastAPI
from fastapi.testclient import TestClient
from invariant_support import quantity_bounds
from psycopg.conninfo import make_conninfo

from specton.contracts.specification import SpecBundle
from specton.implementation.domain import compile_domain

pytestmark = pytest.mark.db


def setup_runtime(pool, bundle, state, artifacts):
    config = compile_domain(bundle, state)["domain"]
    with pool.connection() as conn:
        assert conn.execute("SELECT current_schema() AS s").fetchone()["s"].startswith("test_")
        dsn = make_conninfo(pool.conninfo, options=conn.info.options)
        conn.execute(artifacts["ddl.sql"].decode(), prepare=False)
        conn.execute(
            "CREATE TABLE _specton_commands(scope text, key text, request_hash text, "
            "result jsonb, PRIMARY KEY(scope,key))"
        )
        conn.commit()
    path = Path("specton/implementation/templates/runtime/domain.py.txt")
    loader = importlib.machinery.SourceFileLoader("runtime_domain_test", str(path))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    app = FastAPI()
    module.register(app, config, dsn, lambda request, roles: "synthetic-actor")
    return TestClient(app), config


def post(client, op, body, key):
    return client.post(op["path"], json=body, headers={"Idempotency-Key": key})


def test_real_db_rejects_invalid_insert_and_update_without_partial_save(pool):
    draft, state, artifacts = case()
    client, config = setup_runtime(pool, quantity_bounds(reviewed(draft)), state, artifacts)
    ops = {o["id"]: o for o in config["operations"]}
    parent, child = config["fixtures"]
    assert post(client, ops[parent["api_id"]], parent["values"], "parent").status_code == 200
    insert = ops[child["api_id"]]
    update = next(
        o for o in ops.values() if o["table_id"] == insert["table_id"] and o["action"] == "update"
    )
    read = next(
        o for o in ops.values() if o["table_id"] == insert["table_id"] and o["action"] == "list"
    )
    payload = {**child["values"], "sequence": 1, "amount": "2"}
    failed = post(client, insert, payload, "child")
    assert failed.status_code == 409 and failed.json()["detail"] == "RULE_VIOLATION"
    assert client.get(read["path"]).json() == []
    good = {**payload, "amount": "0.50"}
    saved = post(client, insert, good, "child")
    assert saved.status_code == 200
    assert post(client, insert, good, "child").json() == saved.json()
    assert post(client, update, {**good, "amount": "1.01"}, "update").status_code == 409
    assert client.get(read["path"]).json()[0]["amount"] == "0.50"
    assert post(client, update, {**good, "amount": "1"}, "update").status_code == 200
    with pool.connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM _specton_commands").fetchone()["n"] == 3


def test_state_transition_checks_final_values_and_rolls_back(pool):
    draft, state, artifacts = case("maintenance")
    data = with_transition(draft).model_dump(mode="json")
    entity = next(e for e in data["entities"] if any(f["name"] == "status" for f in e["fields"]))
    status = next(f for f in entity["fields"] if f["name"] == "status")
    data["invariants"] = [
        {
            "id": "INV-no-approved",
            "req_ids": [data["requirements"][0]["id"]],
            "description": "합성 거절 사례",
            "match": "all",
            "layers": ["api"],
            "comparisons": [
                {
                    "operator": "ne",
                    "left": {"kind": "field", "entity_id": entity["id"], "field_id": status["id"]},
                    "right": {"kind": "text", "value": "approved"},
                },
            ],
        }
    ]
    client, config = setup_runtime(pool, SpecBundle.model_validate(data), state, artifacts)
    ops = {o["id"]: o for o in config["operations"]}
    for fixture in config["fixtures"]:
        assert (
            post(client, ops[fixture["api_id"]], fixture["values"], fixture["api_id"]).status_code
            == 200
        )
    transition = next(o for o in ops.values() if o["action"] == "transition")
    payload = config["fixtures"][-1]["values"]
    keys = {f["name"]: payload[f["name"]] for f in transition["keys"]}
    assert post(client, transition, keys, "transition").status_code == 409
    read = next(
        o for o in ops.values() if o["table_id"] == transition["table_id"] and o["action"] == "list"
    )
    assert client.get(read["path"]).json()[0]["status"] == "pending"
