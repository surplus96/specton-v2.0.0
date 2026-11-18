import io
import zipfile

import pytest
from pydantic import SecretStr
from test_identity_projects import headers, login
from test_specifications import edit, expectation, ready
from test_specifications import settings as settings
from test_specifications import workspace as workspace

from specton.contracts.specification import SpecBundle
from specton.specification import completion

pytestmark = pytest.mark.db


def test_completion_consent_version_ownership_and_no_auto_save(workspace, settings, monkeypatch):
    client, initial, _, _ = workspace
    settings.openai_api_key = SecretStr("synthetic-key")
    url = "/api/v1/specs/" + initial["bundle"]["spec_id"]
    calls = []

    def propose(config, current, state, instruction):
        calls.append(instruction)
        return current, []

    monkeypatch.setattr(completion, "propose", propose)
    body = {**expectation(initial), "consent_external_analysis": True, "instruction": "범위 검토"}
    assert (
        client.post(
            url + "/complete",
            json={**body, "consent_external_analysis": False},
            headers=headers(client),
        ).status_code
        == 422
    )
    result = client.post(url + "/complete", json=body, headers=headers(client))
    assert result.status_code == 200, result.text
    assert result.json()["generation_ready"] is False
    assert calls == ["범위 검토"]
    assert client.get(url).json()["versions"] == [1]
    assert client.get(url).json()["approved_by"] is None
    assert client.get(url + "/design").status_code == 422
    assert (
        client.post(
            url + "/complete", json={**body, "spec_hash": "0" * 64}, headers=headers(client)
        ).status_code
        == 409
    )
    login(client, monkeypatch, subject="other")
    assert client.post(url + "/complete", json=body, headers=headers(client)).status_code == 404
    assert len(calls) == 1


def test_approved_design_export_and_later_changes_preserve_previous_version(workspace):
    client, initial, _, _ = workspace
    current = edit(client, initial, ready(initial)).json()
    url = "/api/v1/specs/" + initial["bundle"]["spec_id"]
    approved = client.post(url + "/approve", json=expectation(current), headers=headers(client))
    assert approved.status_code == 200
    original = client.get(url + "/design")
    assert original.status_code == 200
    bundle = SpecBundle.model_validate(current["bundle"]).model_dump(mode="json")
    bundle["screens"][0]["name"] = "고객 변경 화면"
    next_version = edit(client, current, bundle).json()
    assert client.get(url + "/design").status_code == 422
    assert (
        client.post(
            url + "/approve", json=expectation(next_version), headers=headers(client)
        ).status_code
        == 200
    )
    revised = client.get(url + "/design")
    with zipfile.ZipFile(io.BytesIO(revised.content)) as z:
        assert "고객 변경 화면" in z.read("functions.md").decode()
    with zipfile.ZipFile(io.BytesIO(original.content)) as z:
        assert "고객 변경 화면" not in z.read("functions.md").decode()
    assert client.get(url + "/versions/2").json()["status"] == "approved"


def test_legacy_profiles_retired(workspace):
    client, initial, _, _ = workspace
    url = "/api/v1/specs/" + initial["bundle"]["spec_id"]
    body = {**expectation(initial), "acknowledge_demo_defaults": True}
    assert client.post(url + "/business", json=body, headers=headers(client)).status_code == 410


def test_domain_structure_proposal_is_owned_versioned_and_not_auto_approved(workspace, monkeypatch):
    client, initial, _, _ = workspace
    url = "/api/v1/specs/" + initial["bundle"]["spec_id"]
    body = expectation(initial)
    result = client.post(url + "/derive", json=body, headers=headers(client))
    assert result.status_code == 200, result.text
    proposal = result.json()
    assert proposal["bundle"]["domain"]
    assert not proposal["generation_ready"]
    assert not proposal["readiness"]["ready_for_review"]
    assert all(c["status"] == "needs_review" for c in proposal["bundle"]["domain"]["coverage"])
    assert client.get(url).json()["versions"] == [1]
    assert client.get(url).json()["approved_by"] is None
    assert (
        client.post(
            url + "/derive", json={**body, "spec_hash": "0" * 64}, headers=headers(client)
        ).status_code
        == 409
    )
    login(client, monkeypatch, subject="other-domain-owner")
    assert client.post(url + "/derive", json=body, headers=headers(client)).status_code == 404


def test_scope_report_preserves_saved_version_and_ownership(workspace, monkeypatch):
    client, initial, _, run = workspace
    url = "/api/v1/specs/" + initial["bundle"]["spec_id"]
    response = client.get(url + "/scope?version=1")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["assessment_kind"] == "advisory"
    assert result["business_acceptance"] == "not_run"
    assert len(result["items"]) == len(initial["bundle"]["requirements"])
    assert client.get(url).json()["versions"] == [1]
    run_scope = client.get(f"/runs/{run}/scope")
    assert run_scope.status_code == 200
    assert len(run_scope.json()["items"]) == len(result["items"])
    login(client, monkeypatch, subject="other-scope-owner")
    assert client.get(url + "/scope").status_code == 404
    assert client.get(f"/runs/{run}/scope").status_code == 404
