"""Synthetic source signatures for profile tests; no customer mailbox or real project state."""

import hashlib
from copy import deepcopy
from pathlib import Path

from specton.contracts import DesignState
from specton.contracts.specification import SpecBundle
from specton.implementation.commerce_contract import SOURCE_TABLES
from specton.model_hash import model_hash


def source():
    root = Path("tests/fixtures/implementation")
    state = DesignState.model_validate_json((root / "spec/design-state.json").read_bytes())
    current = SpecBundle.model_validate_json((root / "spec/approved-spec.json").read_bytes())
    data = state.model_dump(mode="json")
    prototype = deepcopy(data["normalized"]["tables"][0])
    data["normalized"]["tables"] = []
    data["normalized"]["foreign_keys"] = []
    for index, (key, (name, columns)) in enumerate(SOURCE_TABLES.items()):
        table = deepcopy(prototype)
        table.update(
            id="TBL-demo-" + key,
            name=name,
            physical_name="demo_" + key,
            columns=[],
            primary_key=[],
            unique_keys=[],
        )
        for n, title in enumerate(sorted(columns)):
            col = deepcopy(prototype["columns"][0])
            col.update(
                id=f"COL-demo-{index}-{n}",
                name=title,
                physical_name=f"field_{n}",
                data_type="varchar",
                length=64,
                precision=None,
                scale=None,
                references=None,
                relationship_id=None,
            )
            table["columns"].append(col)
        table["primary_key"] = [table["columns"][0]["id"]]
        data["normalized"]["tables"].append(table)
    state = DesignState.model_validate(data)
    bundle = current.model_dump(mode="json")
    bundle.update(
        entities=[],
        storage_bindings=[],
        operation_bindings=[],
        use_cases=[],
        screens=[],
        apis=[],
        acceptance_cases=[],
        questions=[],
        inventory=None,
    )
    prototype = bundle["requirements"][0]
    bundle["requirements"] = [
        {
            **prototype,
            "id": f"REQ-source-{n:02d}",
            "legacy_id": f"REQ-{n:02d}",
            "text": f"합성 업무 요구 {n}",
        }
        for n in range(1, 26)
    ]
    bundle["baseline"]["model_hash"] = model_hash(state)
    artifacts = {p.name: p.read_bytes() for p in (root / "design").iterdir()}
    assert all(
        hashlib.sha256(artifacts[d["kind"] + "." + d["file_format"]]).hexdigest() == d["sha256"]
        for d in bundle["baseline"]["artifacts"]
    )
    return SpecBundle.model_validate(bundle), state, artifacts
