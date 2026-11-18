import hashlib
import json
from copy import deepcopy

import pytest
from calculation_support import calculated_command, calculation_case
from feedback_contract_support import QUOTE, reviews, suggestion

from specton.api.feedback import Review
from specton.feedback.analysis import needs_input, proposal_hash, propose
from specton.implementation.compiler import compile_contract
from specton.implementation.consistency import check
from specton.implementation.package import generate
from specton.implementation.verify import inspect_package


@pytest.mark.parametrize("domain", ["inventory", "maintenance"])
@pytest.mark.parametrize("command", [False, True])
def test_contract_review_preserves_source_cases_and_binds_reviewed_results(domain, command):
    base, state, artifacts = (calculated_command if command else calculation_case)(domain)
    analysis = suggestion(base, command)
    draft, details = propose(base, analysis, QUOTE)
    assert draft.acceptance_cases == base.acceptance_cases
    assert needs_input(details) and details["executable_change"]
    owner = reviews(base, change_average=not command)
    reviewed, final = propose(base, analysis, QUOTE, owner)
    assert not needs_input(final)
    assert proposal_hash("a" * 64, QUOTE, draft.model_dump(mode="json"), details) != proposal_hash(
        "a" * 64, QUOTE, reviewed.model_dump(mode="json"), final
    )
    assert (
        reviewed.baseline == base.baseline and reviewed.domain.operations == base.domain.operations
    )
    for old, new in zip(base.acceptance_cases, reviewed.acceptance_cases, strict=True):
        if old.execution:
            assert old.execution.category == new.execution.category
            for a, b in zip(old.execution.steps, new.execution.steps, strict=True):
                assert a.model_dump(exclude={"expect"}) == b.model_dump(exclude={"expect"})
                if a.expect.kind == "error":
                    assert a.expect == b.expect
    compile_contract(reviewed, state)
    source = generate(reviewed, state, artifacts)
    files, _ = inspect_package(source, hashlib.sha256(source).hexdigest())
    assert check(files)["documents"] == "regenerated_exact"
    assert files["design/revised/ddl.sql"] == artifacts["ddl.sql"]
    saved = json.loads(files["design/revised/executable-spec.json"])
    assert saved["domain"] == reviewed.model_dump(mode="json")["domain"]
    assert b'"rounding": "down"' in files["backend/contract.json"]


@pytest.mark.parametrize(
    "mutation",
    ["remove_guard", "remove_filter", "target", "node", "schema", "fake_quote", "ai_oracle"],
)
def test_unscoped_edits_rejected(mutation):
    base, _, _ = calculation_case()
    analysis = suggestion(base).model_dump(mode="json")
    patch = analysis["suggestions"][0]
    if mutation == "remove_guard":
        patch.update(
            section="domain_commands", object_id="API-atomic", field="before", value_json="[]"
        )
    elif mutation == "remove_filter":
        patch.update(field="filters", value_json="[]")
    elif mutation == "target":
        patch["object_id"] = "API-missing"
    elif mutation == "node":
        value = json.loads(patch["value_json"])
        value[0]["id"] = "new"
        patch["value_json"] = json.dumps(value)
    elif mutation == "schema":
        patch["field"] = "table_id"
    elif mutation == "fake_quote":
        analysis["quotes"] = ["위조한 고객 요청"]
    else:
        analysis["acceptance_reviews"] = [r.model_dump(mode="json") for r in reviews(base)]
    with pytest.raises(ValueError):
        payload = Review.model_validate({"expected_version": 1, "analysis": analysis})
        propose(base, payload.analysis, QUOTE)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "bad_index", "error", "drop_field"])
def test_owner_cannot_remove_failure_or_partial_response_checks(mutation):
    base, _, _ = calculation_case()
    owner = [r.model_dump(mode="json") for r in reviews(base, True)]
    review = next(r for r in owner if r["case_id"] == "TC-summary-normal")
    if mutation == "missing":
        owner.pop()
        _, details = propose(
            base,
            suggestion(base),
            QUOTE,
            tuple(
                Review.model_validate(
                    {
                        "expected_version": 1,
                        "analysis": suggestion(base),
                        "acceptance_reviews": owner,
                    }
                ).acceptance_reviews
            ),
        )
        assert needs_input(details)
        return
    if mutation == "duplicate":
        owner.append(deepcopy(review))
    elif mutation == "bad_index":
        review["replacements"][0]["step_index"] = 23
    elif mutation == "error":
        review["case_id"] = "TC-summary-failure"
        owner = [review]
    else:
        review["replacements"][0]["expect"]["body"].pop("total")
    with pytest.raises(ValueError):
        payload = Review.model_validate(
            {"expected_version": 1, "analysis": suggestion(base), "acceptance_reviews": owner}
        )
        propose(base, payload.analysis, QUOTE, payload.acceptance_reviews)
