import pytest
from test_identity_projects import headers
from test_specifications import edit, expectation
from test_specifications import settings as settings
from test_specifications import workspace as workspace

pytestmark = pytest.mark.db


def test_executable_case_is_saved_in_new_version_and_invalid_steps_are_rejected(workspace):
    client, initial, _, _ = workspace
    url = "/api/v1/specs/" + initial["bundle"]["spec_id"]
    response = client.post(url + "/derive", json=expectation(initial), headers=headers(client))
    assert response.status_code == 200
    bundle = response.json()["bundle"]
    bundle["schema_version"] = "spec-v0.7"
    api = next(a for a in bundle["apis"] if a["method"] == "GET")
    use = next(u for u in bundle["use_cases"] if u["id"] == api["use_case_id"])
    bundle["acceptance_cases"].append(
        dict(
            id="TC-explicit-empty",
            req_ids=use["req_ids"],
            use_case_ids=[use["id"]],
            tier="api",
            given=["빈 테스트 DB"],
            when="목록 조회",
            then=["빈 목록"],
            fixture_ids=["empty"],
            execution=dict(
                category="normal",
                steps=[dict(api_id=api["id"], expect=dict(kind="exact", status=200, body=[]))],
            ),
        )
    )
    saved = edit(client, initial, bundle)
    assert saved.status_code == 200, saved.text
    current = saved.json()
    assert current["bundle"]["spec_version"] == 2 and current["status"] != "approved"
    assert current["readiness"]["spec_hash"] != initial["readiness"]["spec_hash"]
    old = client.get(url + "/versions/1").json()
    assert old["readiness"]["spec_hash"] == initial["readiness"]["spec_hash"]
    changed = current["bundle"]
    changed["acceptance_cases"][-1]["execution"]["steps"][0]["api_id"] = "API-missing"
    assert edit(client, current, changed).status_code == 422
    assert client.get(url).json()["bundle"]["spec_version"] == 2
