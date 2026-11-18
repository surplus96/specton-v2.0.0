import pytest
from test_identity_projects import headers, login
from test_previews import settings as settings
from test_previews import source as source
from test_previews import verified as verified
from test_previews import workspace as workspace
from test_specifications import edit, expectation, ready
from test_verification_jobs import enqueue

pytestmark = pytest.mark.db


def test_review_is_owned_read_only_versioned_and_not_a_delivery_approval(workspace, monkeypatch):
    client, initial, _, _ = workspace
    url = "/api/v1/specs/" + initial["bundle"]["spec_id"]
    response = client.get(url + "/handoff")
    assert response.status_code == 200, response.text
    report = response.json()
    assert response.headers["cache-control"] == "no-store"
    assert report["spec_hash"] == initial["readiness"]["spec_hash"]
    assert report["conclusion"] == "contract_work_required"
    assert report["source"] is None
    assert report["customer_handoff"] == "not_recorded"
    assert client.get(url).json() == initial
    current = edit(client, initial, ready(initial)).json()
    assert (
        client.post(
            url + "/approve", json=expectation(current), headers=headers(client)
        ).status_code
        == 200
    )
    assert client.get(url + "/handoff?version=1").json()["is_latest"] is False
    assert client.get(url + "/handoff?version=0").status_code == 422
    assert client.get(url + "/handoff?version=999").status_code == 404
    login(client, monkeypatch, "other-handoff-owner")
    assert client.get(url + "/handoff").status_code == 404


def test_review_checks_source_and_latest_evidence_without_promoting_prose_cases(verified, pool):
    (client, spec, impl), _, _ = verified
    url = "/api/v1/specs/" + spec["bundle"]["spec_id"] + "/handoff"
    response = client.get(url)
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["source"]["source_hash"] == impl["source_hash"]
    assert report["source"]["integrity"]["status"] == "passed"
    assert report["source"]["verification"]["status"] == "passed"
    assert report["source"]["passed_case_ids"] == []
    assert report["business_acceptance"] == "not_run"
    assert enqueue(verified[0]).status_code == 200
    assert client.get(url).json()["source"]["verification"]["status"] == "blocked"
    with pool.connection() as conn:
        conn.execute(
            "UPDATE implementation_source SET source_zip=%s WHERE id=%s", (b"tampered", impl["id"])
        )
    tampered = client.get(url).json()
    assert tampered["source"]["integrity"]["status"] == "blocked"
    assert tampered["source"]["passed_case_ids"] == []
