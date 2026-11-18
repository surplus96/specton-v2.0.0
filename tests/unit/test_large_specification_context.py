import json
from types import SimpleNamespace

import pytest
from calculation_support import calculation_case

from specton.config import Settings
from specton.feedback import analysis
from specton.specification import completion
from specton.specification.llm_context import specification_context
from specton.specification.readiness import spec_hash
from specton.specification.refinement import Refinement, apply_refinement


def edit(bundle, **changes):
    return {
        "section": "screens",
        "object_id": bundle.screens[0].id,
        "field": "loading_state",
        "value_json": '"자료를 불러오는 중입니다."',
        "rationale": "고객이 요청한 화면 안내 보완",
        **changes,
    }


@pytest.mark.parametrize("domain", ["inventory", "maintenance"])
def test_context_preserves_contracts_without_duplicate_schemas_or_test_bodies(domain):
    bundle, _, _ = calculation_case(domain)
    before = spec_hash(bundle)
    full = specification_context(bundle)
    compact = specification_context(bundle, api_fields=False)
    assert full["specification"]["domain"] == bundle.domain.model_dump(mode="json")
    assert full["specification"]["apis"] == [a.model_dump(mode="json") for a in bundle.apis]
    assert all("inputs" not in u for u in full["specification"]["use_cases"])
    assert all("request_fields" not in a for a in compact["specification"]["apis"])
    cases = compact["specification"]["acceptance_cases"]
    assert {c["id"] for c in cases} == {c.id for c in bundle.acceptance_cases}
    assert all("execution" not in c and "expect" not in c for c in cases)
    assert sum(c["protected"] for c in cases) == sum(
        c.execution is not None for c in bundle.acceptance_cases
    )
    assert len(json.dumps(compact)) < len(bundle.model_dump_json())
    assert spec_hash(bundle) == before


def test_large_proposal_changes_only_requested_fields_and_never_supplies_answers(monkeypatch):
    bundle, state, _ = calculation_case()
    old = spec_hash(bundle)
    output = Refinement.model_validate(
        {
            "edits": [edit(bundle)],
            "questions": [
                {
                    "req_ids": [bundle.requirements[0].id],
                    "question": "새 업무의 운영 권한을 확인해 주세요.",
                }
            ],
        }
    )
    requests = []

    def complete(request, output_type, **kwargs):
        requests.append(request)
        assert output_type is Refinement
        return SimpleNamespace(output=output, calls=[])

    monkeypatch.setattr(completion, "openai_client", lambda _: SimpleNamespace(complete=complete))
    proposed, calls = completion.refine_large(
        Settings(_env_file=None), bundle, state, "화면 안내 보완"
    )
    assert proposed.screens[0].loading_state == "자료를 불러오는 중입니다."
    for field in (
        "baseline",
        "spec_version",
        "requirements",
        "roles",
        "entities",
        "apis",
        "domain",
        "acceptance_cases",
    ):
        assert getattr(proposed, field) == getattr(bundle, field)
    assert proposed.questions[-1].answer is None
    assert spec_hash(bundle) == old and calls == []
    assert requests[0].prompt_version == "specification-refinement-v1"


@pytest.mark.parametrize(
    "kind", ["unknown", "duplicate", "answer", "source", "oracle", "unknown_requirement"]
)
def test_refinement_rejects_unknown_targets_and_protected_edits(kind):
    bundle, _, _ = calculation_case()
    changes = [edit(bundle)]
    questions = []
    if kind == "unknown":
        changes[0]["object_id"] = "SCREEN-missing"
    elif kind == "duplicate":
        changes *= 2
    elif kind == "answer":
        changes[0].update(section="questions", field="answer")
    elif kind == "source":
        changes[0].update(section="requirements", object_id=bundle.requirements[0].id, field="text")
    elif kind == "oracle":
        changes[0].update(section="acceptance_cases", field="execution")
    else:
        questions = [{"req_ids": ["REQ-missing"], "question": "없는 요구를 변경"}]
    with pytest.raises(ValueError):
        apply_refinement(
            bundle, Refinement.model_validate({"edits": changes, "questions": questions})
        )


def test_feedback_uses_projection_and_retains_original_expected_results(monkeypatch):
    bundle, _, _ = calculation_case()
    requests = []
    result = analysis.Analysis.model_validate(
        {
            "summary": "화면 이름 변경",
            "quotes": ["화면 이름 변경"],
            "requests": ["화면 이름 변경"],
            "questions": [],
            "unsupported": [],
            "suggestions": [
                {
                    "section": "screens",
                    "object_id": bundle.screens[0].id,
                    "field": "name",
                    "value_json": '"변경한 화면"',
                    "rationale": "원문에서 요청한 화면 이름",
                }
            ],
        }
    )

    def complete(request, output_type, **kwargs):
        requests.append(request)
        return SimpleNamespace(output=result, calls=[])

    monkeypatch.setattr(analysis, "openai_client", lambda _: SimpleNamespace(complete=complete))
    output, _ = analysis.run(
        Settings(_env_file=None, feedback_analysis_enabled=True), "화면 이름 변경", "", bundle
    )
    payload = json.loads(requests[0].messages[-1].content)
    assert payload["approved_specification"]["projection"] == "specification-context-v1"
    proposed, _ = analysis.propose(bundle, output, "화면 이름 변경")
    assert proposed.acceptance_cases == bundle.acceptance_cases
    assert proposed.domain == bundle.domain and proposed.apis == bundle.apis
    assert proposed.screens[0].name == "변경한 화면"
