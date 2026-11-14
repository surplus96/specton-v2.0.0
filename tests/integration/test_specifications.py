"""실제 승인 파이프라인 → 명세 보완 → 해시에 묶인 승인. 외부 LLM/OAuth는 고정 응답."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from test_identity_projects import headers, login
from test_scripted_flow import _Flow, _to_final_review

from specton.api.main import create_app
from specton.config import Settings

pytestmark = pytest.mark.db


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        google_client_id="test-client",
        google_client_secret="test-secret",
        storage_dir=tmp_path,
        public_origin="http://localhost:5173",
        runner_poll_seconds=0.05,
    )


@pytest.fixture
def workspace(pool, settings, monkeypatch):
    flow = _Flow(pool, settings)
    flow.runner.start()
    try:
        run, current = _to_final_review(flow)
        assert (
            flow.resume(
                current, {"kind": "review", "decision": "approve", "feedback": ""}
            ).status_code
            == 202
        )
        done = flow.wait(run, state="completed")
        client = flow.client
        login(client, monkeypatch)
        project = client.post(
            "/api/v1/projects", json={"name": "spec test"}, headers=headers(client)
        ).json()["id"]
        assert (
            client.post(
                f"/api/v1/projects/{project}/runs/{run}/claim", headers=headers(client)
            ).status_code
            == 200
        )
        base = client.post(
            f"/api/v1/projects/{project}/baselines",
            json={"run_id": run, "revision": done["revision"]},
            headers=headers(client),
        ).json()["id"]
        result = client.post(f"/api/v1/baselines/{base}/specs", headers=headers(client))
        assert result.status_code == 200, result.text
        yield client, result.json(), base, run
    finally:
        flow.runner.stop()
        flow.client.close()


def expectation(spec):
    return {
        "expected_version": spec["bundle"]["spec_version"],
        "spec_hash": spec["readiness"]["spec_hash"],
    }


def edit(client, current, bundle):
    return client.patch(
        "/api/v1/specs/" + current["bundle"]["spec_id"],
        json={**expectation(current), "bundle": bundle},
        headers=headers(client),
    )


def ready(spec):
    bundle = deepcopy(spec["bundle"])
    bundle["roles"] = [{"id": "ROLE-viewer", "name": "조회 담당자"}]
    for q in bundle["questions"]:
        q["answer"] = (
            "합성 인수 계약: 조회 전용 역할과 요구별 조회 API·화면·인수 사례를 확인했습니다."
        )
    for index, req in enumerate(bundle["requirements"]):
        if req["kind"] == "NFR":
            bundle["acceptance_cases"].append(
                {
                    "id": f"TEST-policy{index}",
                    "req_ids": [req["id"]],
                    "use_case_ids": [],
                    "tier": "policy",
                    "given": ["고정 환경"],
                    "when": "정책을 확인한다",
                    "then": ["명시된 기준 충족"],
                    "fixture_ids": ["fixture-inventory"],
                }
            )
            continue
        uc, api = f"UC-view{index}", f"API-view{index}"
        output = [
            {"id": f"FIELD-value{index}", "name": "value", "data_type": "string", "required": True}
        ]
        bundle["use_cases"].append(
            {
                "id": uc,
                "name": req["text"],
                "req_ids": [req["id"]],
                "actor_roles": ["ROLE-viewer"],
                "preconditions": ["로그인"],
                "inputs": [],
                "steps": ["조회"],
                "outputs": output,
                "error_codes": [],
                "transaction": "read_only",
                "idempotency": "not_applicable",
            }
        )
        bundle["apis"].append(
            {
                "id": api,
                "use_case_id": uc,
                "method": "GET",
                "path": f"/view{index}",
                "actor_roles": ["ROLE-viewer"],
                "request_fields": [],
                "response_fields": output,
                "success_status": 200,
                "error_codes": [],
                "pagination": "none",
                "concurrency": "read_only",
            }
        )
        bundle["screens"].append(
            {
                "id": f"SCREEN-view{index}",
                "route": f"/view{index}",
                "name": "조회",
                "actor_roles": ["ROLE-viewer"],
                "api_ids": [api],
                "empty_state": "없음",
                "loading_state": "조회 중",
                "error_state": "실패",
            }
        )
        bundle["acceptance_cases"].append(
            {
                "id": f"TEST-view{index}",
                "req_ids": [req["id"]],
                "use_case_ids": [uc],
                "tier": "browser",
                "given": ["등록된 자료"],
                "when": "조회한다",
                "then": ["자료가 표시된다"],
                "fixture_ids": ["fixture-inventory"],
            }
        )
    return bundle


def test_versions_readiness_approval_and_preserved_history(workspace):
    client, initial, base, _ = workspace
    url = "/api/v1/specs/" + initial["bundle"]["spec_id"]
    assert initial["status"] == "needs_input"
    assert not initial["readiness"]["ready_for_review"]
    assert client.post(f"/api/v1/baselines/{base}/specs", headers=headers(client)).json() == initial
    assert (
        client.post(
            url + "/approve", json=expectation(initial), headers=headers(client)
        ).status_code
        == 422
    )
    result = edit(client, initial, ready(initial))
    assert result.status_code == 200, result.text
    second = result.json()
    assert second["bundle"]["spec_version"] == 2
    assert second["bundle"]["parent_spec_hash"] == initial["readiness"]["spec_hash"]
    assert second["status"] == "ready_for_review"
    assert edit(client, initial, ready(initial)).status_code == 409
    assert (
        client.post(
            url + "/approve", json=expectation(initial), headers=headers(client)
        ).status_code
        == 409
    )
    approved = client.post(url + "/approve", json=expectation(second), headers=headers(client))
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["approved_by"] == client.get("/api/v1/auth/me").json()["id"]
    assert (
        client.post(url + "/approve", json=expectation(second), headers=headers(client)).json()
        == approved.json()
    )
    changed = deepcopy(second["bundle"])
    changed["roles"][0]["name"] = "이름을 바꾼 조회 담당자"
    third = edit(client, second, changed).json()
    assert third["bundle"]["spec_version"] == 3 and third["status"] == "ready_for_review"
    assert third["bundle"]["roles"][0]["id"] == second["bundle"]["roles"][0]["id"]
    history = client.get(url + "/versions/2").json()
    assert history["status"] == "approved" and history["bundle"] == second["bundle"]
    assert client.get(url + "/versions/1").json()["bundle"] == initial["bundle"]


def test_ownership_csrf_provenance_and_retired_ids(workspace, pool, settings, monkeypatch):
    client, initial, base, _ = workspace
    url = "/api/v1/specs/" + initial["bundle"]["spec_id"]
    other = TestClient(create_app(settings, pool))
    login(other, monkeypatch, "other")
    assert other.get(url).status_code == 404
    assert other.get(url + "/versions/1").status_code == 404
    assert other.post(f"/api/v1/baselines/{base}/specs", headers=headers(other)).status_code == 404
    assert (
        other.post(url + "/approve", json=expectation(initial), headers=headers(other)).status_code
        == 404
    )
    assert (
        other.patch(
            url, json={**expectation(initial), "bundle": initial["bundle"]}, headers=headers(other)
        ).status_code
        == 404
    )
    assert (
        client.patch(url, json={**expectation(initial), "bundle": initial["bundle"]}).status_code
        == 403
    )
    changed = deepcopy(initial["bundle"])
    changed["baseline"]["model_hash"] = "a" * 64
    assert edit(client, initial, changed).status_code == 422
    changed = deepcopy(initial["bundle"])
    changed["requirements"][0].update(origin="user", legacy_id=None)
    assert edit(client, initial, changed).status_code == 422
    changed = deepcopy(initial["bundle"])
    changed["requirements"][0]["priority"] = "Should"
    assert edit(client, initial, changed).status_code == 422
    changed = deepcopy(initial["bundle"])
    changed["questions"] = []
    assert edit(client, initial, changed).status_code == 422
    second = edit(client, initial, ready(initial)).json()
    changed = deepcopy(second["bundle"])
    changed["roles"].append({"id": "ROLE-unconfirmed", "name": "再利用"})
    assert edit(client, second, changed).status_code == 422
    assert client.get(url).json()["bundle"]["spec_version"] == 2
    assert edit(client, second, second["bundle"]).json() == second


def test_tampered_baseline_blocks_creation_edit_and_approval(workspace, pool, settings):
    client, initial, base, run = workspace
    second = edit(client, initial, ready(initial)).json()
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT storage_ref FROM artifact a JOIN model_snapshot s USING(snapshot_id) "
            "WHERE s.run_id=%s AND a.kind='ddl'",
            (run,),
        ).fetchone()
    (settings.storage_dir / row["storage_ref"]).write_bytes(b"-- changed")
    url = "/api/v1/specs/" + initial["bundle"]["spec_id"]
    assert (
        client.post(f"/api/v1/baselines/{base}/specs", headers=headers(client)).status_code == 422
    )
    assert edit(client, second, second["bundle"]).status_code == 422
    assert (
        client.post(url + "/approve", json=expectation(second), headers=headers(client)).status_code
        == 422
    )
    assert client.get(url).json()["status"] == "ready_for_review"


def test_concurrent_edits_only_one_new_version(workspace):
    client, initial, _, _ = workspace
    a, b = ready(initial), ready(initial)
    b["roles"][0]["name"] = "경쟁 요청"
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(
            workers.map(lambda bundle: edit(client, initial, bundle).status_code, [a, b])
        )
    assert sorted(results) == [200, 409]
    latest = client.get("/api/v1/specs/" + initial["bundle"]["spec_id"]).json()
    assert latest["versions"] == [1, 2]


def test_other_domain_cannot_be_presented_as_inventory_template(workspace, pool):
    client, initial, base, run = workspace
    with pool.connection() as conn:
        conn.execute("UPDATE run SET pack='maintenance' WHERE run_id=%s", (run,))
    assert (
        client.post(f"/api/v1/baselines/{base}/specs", headers=headers(client)).status_code == 422
    )
    assert edit(client, initial, ready(initial)).status_code == 422
    assert (
        client.post(
            "/api/v1/specs/" + initial["bundle"]["spec_id"] + "/approve",
            json=expectation(initial),
            headers=headers(client),
        ).status_code
        == 422
    )
