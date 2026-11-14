import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from implementation_support import inventory_executable
from pydantic import ValidationError

from specton.contracts import DesignState
from specton.contracts.specification import SpecBundle
from specton.implementation.compiler import Unsupported, compile_contract
from specton.implementation.package import generate
from specton.specification.readiness import spec_hash

ROOT = Path("tests/fixtures/implementation")


def inputs():
    initial = json.loads((ROOT / "spec/approved-spec.json").read_bytes())
    initial["requirements"] = [r for r in initial["requirements"] if r["origin"] == "design"]
    state = DesignState.model_validate_json((ROOT / "spec/design-state.json").read_bytes())
    return SpecBundle.model_validate(inventory_executable({"bundle": initial}, state)), state


def test_old_v02_approval_hash_is_preserved():
    payload = json.loads((ROOT / "spec/approved-spec.json").read_bytes())
    old = hashlib.sha256(
        b"specton:spec-v0.2\0"
        + json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    assert spec_hash(SpecBundle.model_validate(payload)) == old


def test_policy_is_hashed_and_compiles_deterministically():
    bundle, state = inputs()
    result = compile_contract(bundle, state)
    assert result["inventory"]["quantity_scale"] == 3
    assert len(result["inventory"]["operations"]) == 6
    payload = bundle.model_dump(mode="json")
    payload["inventory"]["api_ids"] = dict(reversed(list(payload["inventory"]["api_ids"].items())))
    reversed_bundle = SpecBundle.model_validate(payload)
    assert spec_hash(bundle) == spec_hash(reversed_bundle)
    artifacts = {p.name: p.read_bytes() for p in (ROOT / "design").iterdir()}
    assert generate(bundle, state, artifacts) == generate(reversed_bundle, state, artifacts)


@pytest.mark.parametrize(
    "field,value", [("quantity_scale", 2), ("negative_stock", True), ("cancel_received", "always")]
)
def test_unapproved_policy_variants_are_rejected(field, value):
    bundle, _ = inputs()
    payload = bundle.model_dump(mode="json")
    payload["inventory"][field] = value
    with pytest.raises(ValidationError):
        SpecBundle.model_validate(payload)


def test_wrong_api_contract_and_missing_storage_are_not_guessed():
    bundle, state = inputs()
    payload = bundle.model_dump(mode="json")
    target = next(
        a for a in payload["apis"] if a["id"] == payload["inventory"]["api_ids"]["confirm"]
    )
    target["concurrency"] = "optimistic"
    with pytest.raises(Unsupported):
        compile_contract(SpecBundle.model_validate(payload), state)
    payload = deepcopy(bundle.model_dump(mode="json"))
    payload["inventory"]["warehouse_entity_id"] = "ENTITY-unknown"
    with pytest.raises(ValidationError):
        SpecBundle.model_validate(payload)


def test_inventory_cannot_be_inserted_into_old_schema_without_new_approval():
    bundle, _ = inputs()
    payload = bundle.model_dump(mode="json")
    payload["schema_version"] = "spec-v0.2"
    with pytest.raises(ValidationError):
        SpecBundle.model_validate(payload)
