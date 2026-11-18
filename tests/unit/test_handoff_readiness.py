from copy import deepcopy

import pytest
from acceptance_support import scenarios
from domain_support import case

from specton.contracts.specification import SpecBundle
from specton.specification.business_contracts import worksheets
from specton.specification.contract_review import ContractReview, validate_review
from specton.specification.handoff import assess_handoff
from specton.specification.readiness import assess_readiness, spec_hash


@pytest.mark.parametrize("domain", ["booking", "maintenance"])
def test_review_uses_actual_domain_links_and_does_not_mutate_approved_inputs(domain):
    bundle, _, _ = case(domain)
    before = bundle.model_dump_json()
    report = assess_handoff(
        bundle,
        assess_readiness(bundle),
        approved=False,
        is_latest=True,
        generator_error="unresolved contract",
    )
    assert bundle.model_dump_json() == before
    assert report.spec_hash == spec_hash(bundle)
    assert report.conclusion == "contract_work_required"
    assert report.business_acceptance == "not_run"
    assert len(report.contracts) == len(bundle.requirements)
    assert set(t for c in report.contracts for t in c.table_ids) == {
        b.table_id for b in bundle.storage_bindings
    }
    assert {e for c in report.contracts for e in c.entity_ids} <= {e.id for e in bundle.entities}
    assert all(
        a.execution == "not_executable"
        for c in report.contracts
        for t in c.topics
        for a in t.acceptance_outline
    )


def test_excluded_and_nfr_requirements_are_visible_and_prose_is_not_executed():
    bundle, _, _ = case()
    data = bundle.model_dump(mode="json")
    data["requirements"][0].update(
        priority="Won't", rationale="이번 계약에서 제외한다고 검토할 항목"
    )
    data["requirements"][1].update(kind="NFR", text="본인에게 배정된 데이터만 조회")
    result = worksheets(SpecBundle.model_validate(data))
    assert result[0].scope == "excluded"
    assert result[1].topics[0].capability_id == "nonfunctional_review"
    assert any(t.capability_id == "identity" for t in result[1].topics)
    assert not any(c.executable_case_ids for c in result)


def test_partial_scenario_coverage_never_means_delivery_passed():
    bundle, _, _ = case()
    bundle = scenarios(bundle)
    report = assess_handoff(
        bundle, assess_readiness(bundle), approved=True, is_latest=False, generator_error=None
    )
    gates = {g.id: g.status for g in report.gates}
    assert gates["approval"] == "blocked"
    assert gates["executable_cases"] == "not_run"
    assert gates["business_handoff"] == "review_required"
    assert report.requirements_without_executable_cases > 0
    assert report.contracts[0].missing_api_case_categories == ()


def review_fixture(bundle):
    r = bundle.requirements[0]
    return {
        "document": "synthetic-review",
        "source_spec_hash": spec_hash(bundle),
        "contracts": [
            {
                "id": "BC-synthetic",
                "name": "출처 연결 검증",
                "requirement_ids": [r.id],
                "source_rules": [{"requirement_id": r.id, "quote": r.text}],
                "entity_ids": [bundle.entities[0].id],
                "required_capabilities": ["multi_record"],
                "examples": [
                    {
                        "id": f"TC-{c}",
                        "category": c,
                        "given": {"state": "before"},
                        "when": "명령 실행",
                        "expected": {"state": "after"},
                    }
                    for c in ("normal", "boundary", "failure")
                ],
            }
        ],
    }


def test_authored_contracts_bind_spec_hash_quotes_and_entities_without_certification():
    bundle, _, _ = case()
    value = review_fixture(bundle)
    result = validate_review(bundle, ContractReview.model_validate(value))
    assert result["status"] == "references_validated"
    assert result["runtime_execution"] == "not_run"
    assert result["remaining_requirement_ids"]
    for path, replacement in (
        (
            "source_rules",
            [{"requirement_id": bundle.requirements[0].id, "quote": "원문에 없는 승인 규칙"}],
        ),
        ("entity_ids", ["ENTITY-missing"]),
        ("required_capabilities", ["unknown"]),
    ):
        wrong = deepcopy(value)
        wrong["contracts"][0][path] = replacement
        with pytest.raises(ValueError):
            validate_review(bundle, ContractReview.model_validate(wrong))
    other, _, _ = case("maintenance")
    with pytest.raises(ValueError, match="해시"):
        validate_review(other, ContractReview.model_validate(value))


def test_authored_contracts_do_not_accept_missing_categories_or_unknown_policy():
    bundle, _, _ = case()
    data = review_fixture(bundle)
    data["contracts"][0]["examples"][0]["proposed_policy_ids"] = ["POL-missing"]
    with pytest.raises(ValueError, match="정책"):
        validate_review(bundle, ContractReview.model_validate(data))
    data = review_fixture(bundle)
    data["contracts"][0]["examples"][0]["category"] = "boundary"
    with pytest.raises(ValueError, match="정상"):
        validate_review(bundle, ContractReview.model_validate(data))
