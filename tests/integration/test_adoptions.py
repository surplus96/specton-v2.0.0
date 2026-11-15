import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_identity_projects import headers, login
from test_previews import settings as settings
from test_previews import source as source
from test_previews import verified as verified
from test_previews import workspace as workspace
from test_verification_jobs import enqueue

from specton.api.main import create_app

pytestmark = pytest.mark.db


def review(verified):
    (client, spec, impl), _, _ = verified
    url = "/api/v1/projects/" + spec["bundle"]["baseline"]["project_id"]
    response = client.get(url + "/candidates/" + impl["id"] + "/comparison")
    assert response.status_code == 200, response.text
    comparison = response.json()
    payload = {
        "implementation_id": impl["id"],
        "verification_id": comparison["latest_verification_id"],
        "expected_current_id": comparison["current_adoption"]["id"]
        if comparison["current_adoption"]
        else None,
        "comparison_hash": comparison["comparison_hash"],
        "request_key": str(uuid4()),
        "rationale": "고정 브라우저 검증과 변경 범위를 확인하여 구현 기준으로 채택합니다.",
        "acknowledge_unverified_acceptance": True,
    }
    return client, url, comparison, payload


def test_adoption_comparison_history_and_idempotency(verified):
    client, url, comparison, payload = review(verified)
    assert comparison["eligible"], comparison
    assert comparison["ddl_changed"]
    assert comparison["files"]
    assert comparison["unverified_acceptance_count"] > 0
    assert client.get(url + "/candidates").json()["items"][0]["id"] == payload["implementation_id"]
    response = client.post(url + "/adoptions", json=payload, headers=headers(client))
    assert response.status_code == 200, response.text
    record = response.json()
    if output := os.environ.get("SPECTON_TEST_ADOPTION_REPORT"):
        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps({"comparison": comparison, "adoption": record}, ensure_ascii=False, indent=2)
        )
    assert record["sequence"] == 1 and record["previous_id"] is None
    assert record["business_acceptance"] == "not_run"
    assert client.post(url + "/adoptions", json=payload, headers=headers(client)).json() == record
    changed = {**payload, "rationale": "다른 판단 사유를 같은 요청 키에 사용하면 충돌합니다."}
    assert client.post(url + "/adoptions", json=changed, headers=headers(client)).status_code == 409
    history = client.get(url + "/implementation-baseline").json()
    assert history["current"] == record and len(history["history"]) == 1
    _, _, again, _ = review(verified)
    assert not again["eligible"] and again["files"] == []


def test_adoption_latest_verification_and_stale_review(verified):
    client, url, _, payload = review(verified)
    assert enqueue(verified[0]).status_code == 200
    response = client.post(url + "/adoptions", json=payload, headers=headers(client))
    assert response.status_code == 409, response.text
    _, _, changed, payload = review(verified)
    assert not changed["eligible"]
    assert client.post(url + "/adoptions", json=payload, headers=headers(client)).status_code == 422


def test_adoption_owner_csrf_and_acknowledgement(verified, pool, settings, monkeypatch):
    client, url, _, payload = review(verified)
    assert client.post(url + "/adoptions", json=payload).status_code == 403
    assert (
        client.post(
            url + "/adoptions",
            json={**payload, "acknowledge_unverified_acceptance": False},
            headers=headers(client),
        ).status_code
        == 422
    )
    other = TestClient(create_app(settings, pool))
    login(other, monkeypatch, "other")
    assert other.get(url + "/candidates").status_code == 404
    assert other.post(url + "/adoptions", json=payload, headers=headers(other)).status_code == 404


def test_adoption_concurrent_compare_and_swap(verified):
    client, url, _, payload = review(verified)
    csrf = headers(client)

    def submit(key):
        return client.post(url + "/adoptions", json={**payload, "request_key": key}, headers=csrf)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(submit, [str(uuid4()), str(uuid4())]))
    assert sorted(r.status_code for r in results) == [200, 409]
    assert len(client.get(url + "/implementation-baseline").json()["history"]) == 1


def test_adoption_source_tamper_rejected(verified, pool):
    client, url, _, payload = review(verified)
    with pool.connection() as conn:
        conn.execute(
            "UPDATE implementation_source SET source_zip=%s WHERE id=%s",
            (b"tampered", payload["implementation_id"]),
        )
    assert client.post(url + "/adoptions", json=payload, headers=headers(client)).status_code == 422


def test_readoption_chain_and_old_request_retry(verified, pool):
    from psycopg.types.json import Jsonb

    from specton.implementation import jobs
    from specton.implementation.browser_runner import suite_hash

    client, url, _, first_payload = review(verified)
    first = client.post(url + "/adoptions", json=first_payload, headers=headers(client)).json()
    enqueue(verified[0])
    with pool.connection() as conn:
        job = jobs.claim(conn, "r", "p", "suite", "test-host", "b", suite_hash())
        report = {**verified[1]["report"]}
        assert jobs.finish(conn, job, report)
    _, _, comparison, second_payload = review(verified)
    assert comparison["eligible"] and not comparison["files"]
    second = client.post(url + "/adoptions", json=second_payload, headers=headers(client))
    assert second.status_code == 200, second.text
    record = second.json()
    assert record["sequence"] == 2
    assert record["previous_record_hash"] == first["record_hash"]
    assert (
        client.post(url + "/adoptions", json=first_payload, headers=headers(client)).json() == first
    )
    assert len(client.get(url + "/implementation-baseline").json()["history"]) == 2
    with pool.connection() as conn:
        conn.execute(
            "UPDATE implementation_adoption SET record=%s WHERE id=%s",
            (Jsonb({**record, "rationale": "tampered"}), record["id"]),
        )
    assert client.get(url + "/implementation-baseline").status_code == 422


def test_adoption_spec_change_and_report_tamper(verified, pool):
    from psycopg.types.json import Jsonb
    from test_specifications import edit

    client, url, _, payload = review(verified)
    _, spec, _ = verified[0]
    bundle = json.loads(json.dumps(spec["bundle"]))
    bundle["requirements"][0]["rationale"] += " 추가 검토가 필요합니다."
    changed = edit(client, spec, bundle)
    assert changed.status_code == 200, changed.text
    assert client.post(url + "/adoptions", json=payload, headers=headers(client)).status_code == 409
    _, _, comparison, new_payload = review(verified)
    assert not comparison["eligible"]
    assert (
        client.post(url + "/adoptions", json=new_payload, headers=headers(client)).status_code
        == 422
    )
    with pool.connection() as conn:
        conn.execute(
            "UPDATE implementation_verification SET report=%s WHERE id=%s",
            (Jsonb({"status": "smoke_passed"}), payload["verification_id"]),
        )
    assert not review(verified)[2]["eligible"]


def test_adoption_migration_preserves_evidence(verified, pool):
    from specton.persistence.db import apply_schema

    client, url, comparison, _ = review(verified)
    with pool.connection() as conn:
        conn.execute(
            "DROP TABLE feedback_revision,"
            "feedback_event,feedback_job,feedback_change,feedback_message,"
            "gmail_connection,gmail_oauth,implementation_adoption"
        )
        conn.execute("UPDATE alembic_version SET version_num='0006_preview'")
    apply_schema(pool)
    assert review(verified)[2] == comparison
    assert client.get(url + "/implementation-baseline").json() == {"current": None, "history": []}


def test_candidate_comparison_project_and_base_boundaries(verified):
    client, url, _, payload = review(verified)
    candidate = payload["implementation_id"]
    selected = client.get(url + "/candidates/" + candidate + "/comparison?base_id=" + candidate)
    assert selected.status_code == 200
    assert selected.json()["files"] == []
    assert not selected.json()["eligible"]
    other = client.post("/api/v1/projects", json={"name": "별도 프로젝트"}, headers=headers(client))
    assert other.status_code == 201, other.text
    cross = "/api/v1/projects/" + other.json()["id"] + "/candidates/" + candidate + "/comparison"
    assert client.get(cross).status_code == 404


def test_candidate_malformed_zip_and_schema_drift(verified, pool):
    import hashlib

    from specton.persistence.db import apply_schema
    from specton.persistence.migrate import SchemaVersionError

    client, url, _, payload = review(verified)
    with pool.connection() as conn:
        conn.execute(
            "UPDATE implementation_source SET source_zip=%s,source_hash=%s WHERE id=%s",
            (b"invalid", hashlib.sha256(b"invalid").hexdigest(), payload["implementation_id"]),
        )
    response = client.get(url + "/candidates/" + payload["implementation_id"] + "/comparison")
    assert response.status_code == 422
    with pool.connection() as conn:
        conn.execute("ALTER TABLE implementation_adoption ADD COLUMN drift text")
    with pytest.raises(SchemaVersionError, match="채택 스키마"):
        apply_schema(pool)


def test_new_spec_candidate_replaces_baseline_with_diff(verified, pool):
    from test_specifications import edit, expectation

    from specton.implementation import jobs
    from specton.implementation.browser_runner import suite_hash

    client, url, _, first_payload = review(verified)
    first = client.post(url + "/adoptions", json=first_payload, headers=headers(client)).json()
    _, old_spec, _ = verified[0]
    bundle = json.loads(json.dumps(old_spec["bundle"]))
    bundle["requirements"][0]["rationale"] += " 고객 검토 결과를 반영합니다."
    spec = edit(client, old_spec, bundle).json()
    spec_url = "/api/v1/specs/" + spec["bundle"]["spec_id"]
    approved = client.post(spec_url + "/approve", json=expectation(spec), headers=headers(client))
    assert approved.status_code == 200, approved.text
    candidate = client.post(
        spec_url + "/implementations", json=expectation(spec), headers=headers(client)
    ).json()
    newer = (client, spec, candidate)
    assert enqueue(newer).status_code == 200
    with pool.connection() as conn:
        job = jobs.claim(conn, "r", "p", "suite", "test-host", "b", suite_hash())
        report = {
            **verified[1]["report"],
            "source_hash": job["source_hash"],
            "spec_hash": job["spec_hash"],
        }
        assert jobs.finish(conn, job, report)
    _, _, comparison, payload = review((newer, None, None))
    assert comparison["eligible"], comparison
    assert comparison["current_adoption"]["id"] == first["id"]
    assert comparison["base"]["id"] == first["implementation_id"]
    assert comparison["semantic"]["requirements"]["modified"] == [bundle["requirements"][0]["id"]]
    assert any(f["path"] == "spec/approved-spec.json" for f in comparison["files"])
    adopted = client.post(url + "/adoptions", json=payload, headers=headers(client))
    assert adopted.status_code == 200, adopted.text
    assert adopted.json()["previous_id"] == first["id"]
    assert adopted.json()["implementation_id"] != first["implementation_id"]
