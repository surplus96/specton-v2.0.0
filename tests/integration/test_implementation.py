import hashlib
import io
import json
import os
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from implementation_support import executable
from test_identity_projects import headers, login
from test_specifications import edit, expectation
from test_specifications import settings as settings
from test_specifications import workspace as workspace

from specton.api.main import create_app
from specton.contracts import DesignState

pytestmark = pytest.mark.db


def test_approved_spec_generates_deterministic_owned_source(workspace, pool, settings, monkeypatch):
    client, initial, _, run = workspace
    url = "/api/v1/specs/" + initial["bundle"]["spec_id"] + "/implementations"
    assert client.post(url, json=expectation(initial), headers=headers(client)).status_code == 422
    with pool.connection() as conn:
        snapshot = conn.execute(
            "SELECT normalized_model FROM model_snapshot WHERE run_id=%s "
            "ORDER BY revision DESC LIMIT 1",
            (run,),
        ).fetchone()
    state = DesignState.model_validate({**snapshot["normalized_model"], "run_id": run})
    proposed = executable(initial, state)
    response = edit(client, initial, proposed)
    assert response.status_code == 200, response.text
    spec = response.json()
    assert (
        client.post(
            "/api/v1/specs/" + spec["bundle"]["spec_id"] + "/approve",
            json=expectation(spec),
            headers=headers(client),
        ).status_code
        == 200
    )
    assert client.post(url, json=expectation(initial), headers=headers(client)).status_code == 409
    first = client.post(url, json=expectation(spec), headers=headers(client))
    assert first.status_code == 200, first.text
    info = first.json()
    assert info["status"] == "source_ready" and info["validation_status"] == "not_run"
    assert client.post(url, json=expectation(spec), headers=headers(client)).json() == info
    download = "/api/v1/implementations/" + info["id"] + "/source"
    source = client.get(download)
    assert (
        source.status_code == 200
        and hashlib.sha256(source.content).hexdigest() == info["source_hash"]
    )
    with zipfile.ZipFile(io.BytesIO(source.content)) as archive:
        manifest = json.loads(archive.read("build-manifest.json"))
        assert manifest["spec_hash"] == spec["readiness"]["spec_hash"]
        assert (
            "backend/app.py" in manifest["files"] and "frontend/src/main.tsx" in manifest["files"]
        )
        compile(archive.read("backend/app.py"), "generated_app", "exec")
        assert (
            json.loads(archive.read("traceability.json"))["acceptance_cases"][0]["status"]
            == "not_run"
        )
    # 명시한 테스트 출력 경로에만 격리 검증용 합성 소스를 저장한다.
    if os.environ.get("SPECTON_TEST_SOURCE_OUTPUT"):
        Path(os.environ["SPECTON_TEST_SOURCE_OUTPUT"]).write_bytes(source.content)
    other = TestClient(create_app(settings, pool))
    login(other, monkeypatch, "other")
    assert other.get(download).status_code == 404
    assert other.get("/api/v1/implementations/" + info["id"]).status_code == 404
    assert other.post(url, json=expectation(spec), headers=headers(other)).status_code == 404
    assert client.post(url, json=expectation(spec)).status_code == 403
    with pool.connection() as conn:
        conn.execute(
            "UPDATE implementation_source SET source_zip='tampered'::bytea WHERE id=%s",
            (info["id"],),
        )
    assert client.get(download).status_code == 422
    assert client.post(url, json=expectation(spec), headers=headers(client)).status_code == 409
