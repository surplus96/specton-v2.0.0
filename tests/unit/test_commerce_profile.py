import hashlib
import io
import zipfile

import pytest
from commerce_support import source
from pydantic import ValidationError

from specton.contracts.specification import SpecBundle
from specton.feedback.analysis import Analysis, propose
from specton.implementation.compiler import Unsupported, compile_contract
from specton.implementation.package import generate
from specton.implementation.verify import inspect_package
from specton.specification.commerce import propose_business
from specton.specification.documents import revised_files
from specton.specification.readiness import assess_readiness, canonical_bytes


def change(field, value):
    quote = "기본 시스템의 변경 요청"
    return Analysis(
        summary=quote,
        quotes=[quote],
        requests=[quote],
        questions=[],
        unsupported=[],
        suggestions=[
            dict(
                section="commerce",
                object_id="wholesale-demo-v1",
                field=field,
                value_json=value,
                rationale=quote,
            )
        ],
    ), quote


def test_business_proposal_traceability_and_readiness():
    current, state, _ = source()
    before = canonical_bytes(current)
    result = propose_business(current, state)
    assert len(result.screens) == 6 and len(result.apis) == 14
    assert assess_readiness(result).ready_for_review
    assert {r.legacy_id for r in current.requirements} == {r.legacy_id for r in result.requirements}
    assert all(r.priority == "Won't" for r in result.requirements if r.legacy_id == "REQ-17")
    assert canonical_bytes(current) == before
    assert len(compile_contract(result, state)["commerce"]["operations"]) == 14
    data = result.model_dump(mode="json")
    data["commerce"]["source_tables"]["product"] = "TBL-forged"
    with pytest.raises(Unsupported):
        compile_contract(SpecBundle.model_validate(data), state)


def test_customer_note_change_regenerates_api_ddl_erd_and_package():
    current, state, artifacts = source()
    baseline = propose_business(current, state)
    suggestion, quote = change("product_note_enabled", "true")
    revised, impact = propose(baseline, suggestion, quote)
    assert impact["executable_change"] and impact["semantic"]["commerce_changed"]
    old_files = revised_files(baseline, artifacts)
    new_files = revised_files(revised, artifacts)
    assert b"ADD COLUMN note" not in old_files["ddl.sql"]
    assert b"ADD COLUMN note" in new_files["ddl.sql"]
    assert b"varchar note" in new_files["erd.mmd"]
    assert b"note" in new_files["functions.md"]
    assert new_files["manifest.json"] != old_files["manifest.json"]
    assert old_files["ddl.sql"].startswith(artifacts["ddl.sql"])
    compiled = compile_contract(revised, state)
    product = next(o for o in compiled["commerce"]["operations"] if o["action"] == "product")
    assert product["request_fields"][-1]["name"] == "note"
    content = generate(revised, state, artifacts)
    files, _ = inspect_package(content, hashlib.sha256(content).hexdigest())
    # Reloading canonical JSON sorts mapping keys; documents must remain identical.
    reloaded = SpecBundle.model_validate_json(canonical_bytes(revised))
    assert revised_files(reloaded, artifacts) == new_files
    assert generate(reloaded, state, artifacts) == content
    assert files["backend/approved.sql"] == new_files["ddl.sql"]
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        assert z.read("design/ddl.sql") == artifacts["ddl.sql"]
    disabled, _ = propose(revised, *change("product_note_enabled", "false"))
    assert not any(f.name == "note" for a in disabled.apis for f in a.request_fields)
    compile_contract(disabled, state)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("cutoff_hour", "24"),
        ("cutoff_hour", "null"),
        ("cutoff_hour", '{"value":17}'),
        ("expiry_days", "0"),
        ("return_warning_percent", "101"),
        ("product_note_enabled", '"yes"'),
    ],
)
def test_invalid_policy_changes_are_rejected(field, value):
    current, state, _ = source()
    with pytest.raises(ValidationError):
        propose(propose_business(current, state), *change(field, value))


def test_existing_spec_hashes_do_not_include_new_profile_default():
    current, _, _ = source()
    assert b"commerce" not in canonical_bytes(current)


@pytest.mark.parametrize(
    ("field", "value", "legacy", "expected"),
    [
        ("return_warning_percent", "10", "REQ-13", "10%"),
        ("cutoff_hour", "18", "REQ-06", "18:00"),
        ("expiry_days", "45", "REQ-11", "45일"),
    ],
)
def test_policy_changes_update_functional_requirements(field, value, legacy, expected):
    current, state, artifacts = source()
    revised, _ = propose(propose_business(current, state), *change(field, value))
    assert expected in next(r.text for r in revised.requirements if r.legacy_id == legacy)
    assert expected in revised_files(revised, artifacts)["functions.md"].decode()
    assert assess_readiness(revised).ready_for_review
