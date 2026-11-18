"""Scripted external mail; actual ownership, approval, immutable artifacts and DB rollback."""

import hashlib
import io
import json
import zipfile

import pytest
from fastapi import HTTPException
from test_feedback import connected as connected
from test_feedback import request_change, suggested
from test_feedback import settings as settings
from test_feedback import verified as verified
from test_feedback import workspace as workspace
from test_identity_projects import headers
from test_specifications import edit, expectation

from specton.api import implementations
from specton.contracts.specification import SpecBundle
from specton.implementation.verify import inspect_package

pytestmark = pytest.mark.db


@pytest.fixture
def source(workspace):
    client, initial, _, _ = workspace
    url = "/api/v1/specs/" + initial["bundle"]["spec_id"]
    response = client.post(url + "/derive", json=expectation(initial), headers=headers(client))
    assert response.status_code == 200, response.text
    bundle = response.json()["bundle"]
    bundle["roles"] = [{"id": "ROLE-test-operator", "name": "합성 인수 담당자"}]
    for section in ("use_cases", "apis", "screens"):
        for item in bundle[section]:
            item["actor_roles"] = ["ROLE-test-operator"]
    for coverage in bundle["domain"]["coverage"]:
        coverage.update(
            status="mapped", explanation="이 합성 테스트의 단일 레코드 저장·조회 범위 확인"
        )
    for q in bundle["questions"]:
        q["answer"] = "합성 테스트에서 제시한 API·화면 계약을 확인함"
    saved = edit(client, initial, bundle)
    assert saved.status_code == 200, saved.text
    spec = saved.json()
    assert spec["readiness"]["ready_for_review"], spec["readiness"]["issues"]
    approved = client.post(url + "/approve", json=expectation(spec), headers=headers(client))
    assert approved.status_code == 200, approved.text
    created = client.post(url + "/implementations", json=expectation(spec), headers=headers(client))
    assert created.status_code == 200, created.text
    return client, spec, created.json()


def test_mail_approval_documents_and_failed_candidate_creation_are_atomic(
    connected, pool, settings, monkeypatch
):
    client, _, verified = connected
    original = verified[0][1]
    spec_url = "/api/v1/specs/" + original["bundle"]["spec_id"]
    old_source_id = verified[0][2]["id"]
    old_source = client.get("/api/v1/implementations/" + old_source_id + "/source").content
    row = request_change(connected, pool, settings, monkeypatch)
    root = "/api/v1/changes/" + row["id"]
    review = client.put(
        root + "/proposal",
        headers=headers(client),
        json={
            "expected_version": row["version"],
            "analysis": suggested(verified).model_dump(mode="json"),
        },
    )
    assert review.status_code == 200, review.text
    row = review.json()
    row = client.post(
        root + "/decide",
        headers=headers(client),
        json={
            "expected_version": row["version"],
            "target_hash": row["proposal_hash"],
            "decision": "approve",
            "note": "명세와 재생성 범위를 확인합니다.",
            "acknowledge_unverified_acceptance": True,
        },
    ).json()
    approved_version = row["version"]
    with monkeypatch.context() as patch:

        def fail(*args, **kwargs):
            raise HTTPException(503, "synthetic queue failure")

        patch.setattr(implementations, "request_verification", fail)
        failed = client.post(
            root + "/implement",
            headers=headers(client),
            json={"expected_version": approved_version},
        )
        assert failed.status_code == 503
    assert (
        client.get(spec_url).json()["bundle"]["spec_version"] == original["bundle"]["spec_version"]
    )
    assert client.get(root).json()["state"] == "approved"
    with pool.connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM implementation_source").fetchone()["n"] == 1
        assert (
            conn.execute("SELECT count(*) AS n FROM implementation_adoption").fetchone()["n"] == 1
        )
    retry = client.post(
        root + "/implement", headers=headers(client), json={"expected_version": approved_version}
    )
    assert retry.status_code == 200, retry.text
    row = retry.json()
    candidate = row["implementation_id"]
    assert (
        client.post(
            root + "/implement",
            headers=headers(client),
            json={"expected_version": approved_version},
        ).json()["implementation_id"]
        == candidate
    )
    new_source = client.get("/api/v1/implementations/" + candidate + "/source").content
    files, _ = inspect_package(new_source, hashlib.sha256(new_source).hexdigest())
    latest = client.get(spec_url).json()
    assert latest["bundle"]["screens"][0]["name"] == "고객 재고"
    design = client.get(spec_url + "/design")
    assert design.status_code == 200
    with zipfile.ZipFile(io.BytesIO(design.content)) as z:
        for name in (
            "functions.md",
            "erd.mmd",
            "ddl.sql",
            "rtm.csv",
            "executable-spec.json",
            "manifest.json",
        ):
            assert z.read(name) == files["design/revised/" + name]
    assert json.loads(files["backend/contract.json"])["screens"][0]["name"] == "고객 재고"
    assert client.get("/api/v1/implementations/" + old_source_id + "/source").content == old_source
    old = client.get(spec_url + "/versions/" + str(original["bundle"]["spec_version"])).json()
    assert old["bundle"]["screens"][0]["name"] != "고객 재고" and old["status"] == "approved"
    project = original["bundle"]["baseline"]["project_id"]
    comparison = client.get(f"/api/v1/projects/{project}/candidates/{candidate}/comparison")
    assert comparison.status_code == 200, comparison.text
    assert comparison.json()["artifact_consistency"]["documents"] == "regenerated_exact"
    assert comparison.json()["data_transfer"]["status"] == "ready_for_rehearsal"
    assert comparison.json()["data_transfer"]["execution"] == "not_run"
    assert not comparison.json()["eligible"]  # candidate verification still queued
    assert client.get(root).json()["state"] == "validating"
    assert (
        SpecBundle.model_validate(latest["bundle"]).baseline
        == SpecBundle.model_validate(original["bundle"]).baseline
    )
