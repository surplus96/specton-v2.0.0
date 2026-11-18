import hashlib
import json
import os
from pathlib import Path

import pytest
from implementation_support import inventory_executable
from test_identity_projects import headers
from test_specifications import edit, expectation
from test_specifications import settings as settings
from test_specifications import workspace as workspace

from specton.contracts import DesignState

pytestmark = pytest.mark.db


def test_inventory_policy_requires_new_approval_and_generates_ledger(workspace, pool):
    client, initial, _, run = workspace
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT normalized_model FROM model_snapshot WHERE run_id=%s "
            "ORDER BY revision DESC LIMIT 1",
            (run,),
        ).fetchone()
    state = DesignState.model_validate({**row["normalized_model"], "run_id": run})
    proposal = inventory_executable(initial, state)
    result = edit(client, initial, proposal)
    assert result.status_code == 200, result.text
    spec = result.json()
    assert spec["bundle"]["schema_version"] == "spec-v0.3"
    url = "/api/v1/specs/" + spec["bundle"]["spec_id"]
    assert (
        client.post(
            url + "/implementations", json=expectation(spec), headers=headers(client)
        ).status_code
        == 422
    )
    assert (
        client.post(url + "/approve", json=expectation(spec), headers=headers(client)).status_code
        == 200
    )
    result = client.post(url + "/implementations", json=expectation(spec), headers=headers(client))
    assert result.status_code == 200, result.text
    generated = result.json()
    assert generated["validation_status"] == "not_run"
    archive = client.get("/api/v1/implementations/" + generated["id"] + "/source").content
    assert hashlib.sha256(archive).hexdigest() == generated["source_hash"]
    if os.environ.get("SPECTON_TEST_INVENTORY_OUTPUT"):
        Path(os.environ["SPECTON_TEST_INVENTORY_OUTPUT"]).write_bytes(archive)
    policy = spec["bundle"]["inventory"]
    policy["negative_stock"] = True
    assert edit(client, spec, spec["bundle"]).status_code == 422
    # 관찰용 API 계약도 일관된 형태로 생성되었는지 확인한다.
    assert json.loads(client.get(url).content)["status"] == "approved"
