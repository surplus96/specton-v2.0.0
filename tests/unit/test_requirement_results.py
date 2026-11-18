from domain_support import case, reviewed

from specton.implementation.requirement_results import requirement_results


def test_results_require_actual_api_evidence_and_never_certify_business():
    draft, _, _ = case()
    spec = reviewed(draft)
    # A table-level or unknown-API result is not evidence for each linked API.
    summary = requirement_results(
        spec,
        [
            {"table_id": spec.domain.operations[0].table_id, "status": "passed"},
            {"api_id": "API-unknown", "status": "passed"},
        ],
    )
    assert len(summary["items"]) == len(spec.requirements)
    assert {r["api_check_status"] for r in summary["items"]} == {"not_run"}
    checks = [{"api_id": a.id, "status": "passed", "checks": ["insert"]} for a in spec.apis]
    full = requirement_results(spec, checks)
    assert {r["api_check_status"] for r in full["items"]} == {"checks_passed"}
    assert {r["business_acceptance"] for r in full["items"]} == {"not_run"}
    assert all(t["status"] == "not_run" for r in full["items"] for t in r["acceptance_cases"])


def test_incomplete_and_failed_api_evidence_are_not_hidden():
    draft, _, _ = case()
    spec = reviewed(draft)
    partial = requirement_results(spec, [{"api_id": spec.apis[0].id, "status": "passed"}])
    row = next(r for r in partial["items"] if spec.apis[0].id in r["api_ids"])
    assert row["api_check_status"] == "partial" and row["missing_api_ids"]
    failed = requirement_results(
        spec,
        [
            {"api_id": spec.apis[0].id, "status": "passed"},
            {"api_id": spec.apis[0].id, "status": "failed"},
        ],
    )
    row = next(r for r in failed["items"] if spec.apis[0].id in r["api_ids"])
    assert row["api_check_status"] == "failed"
    assert spec.apis[0].id not in row["passed_api_ids"]
