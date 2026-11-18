import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from specton.contracts import DesignState
from specton.contracts.specification import SpecBundle
from specton.implementation.compiler import Unsupported, compile_contract
from specton.implementation.package import generate
from specton.implementation.verify import inspect_package
from specton.specification.readiness import spec_hash

ROOT = Path("tests/fixtures/implementation")


def inputs():
    bundle = SpecBundle.model_validate_json((ROOT / "spec/approved-spec.json").read_bytes())
    state = DesignState.model_validate_json((ROOT / "spec/design-state.json").read_bytes())
    artifacts = {p.name: p.read_bytes() for p in (ROOT / "design").iterdir()}
    return bundle, state, artifacts


def test_v01_hash_does_not_change_when_new_binding_fields_are_added():
    bundle = SpecBundle.model_validate_json(
        Path("tests/fixtures/specification/item-create-v0.1.json").read_bytes()
    )
    assert spec_hash(bundle) == "f953e566e45641fb4031d071ee003bd3c148990fac324aed035ea7b6868ca329"


def test_generation_is_deterministic_and_all_source_files_are_bound_to_manifest():
    bundle, state, artifacts = inputs()
    source = generate(bundle, state, artifacts)
    assert source == generate(bundle, state, artifacts)
    files, manifest = inspect_package(source, hashlib.sha256(source).hexdigest())
    assert manifest["spec_hash"] == spec_hash(bundle)
    assert files["backend/approved.sql"] == artifacts["ddl.sql"]
    assert json.loads(files["traceability.json"])["acceptance_cases"][0]["status"] == "not_run"
    compile(files["backend/app.py"], "generated", "exec")
    with pytest.raises(ValueError):
        inspect_package(source, "0" * 64)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_bindings",
        "other_table",
        "other_entity",
        "wrong_type",
        "invariant",
        "extra_api",
        "path",
        "missing_screen",
        "root_path",
    ],
)
def test_unsupported_semantics_are_rejected_before_generation(mutation):
    bundle, state, _ = inputs()
    data = bundle.model_dump(mode="json")
    if mutation == "missing_bindings":
        data["operation_bindings"] = []
    elif mutation == "other_table":
        data["storage_bindings"][0]["table_id"] = "not-a-table"
    elif mutation == "other_entity":
        data["entities"][0]["legacy_id"] = "other-entity"
    elif mutation == "wrong_type":
        # Mutate source rather than breaking the already validated use-case/API equality.
        payload = state.model_dump(mode="json")
        table = next(
            t
            for t in payload["normalized"]["tables"]
            if t["id"] == data["storage_bindings"][0]["table_id"]
        )
        table["columns"][0]["nullable"] = not table["columns"][0]["nullable"]
        state = DesignState.model_validate(payload)
    elif mutation == "invariant":
        data["invariants"] = [
            {
                "id": "RULE-custom",
                "req_ids": ["REQ-masterdata"],
                "description": "unsupported policy",
                "match": "all",
                "comparisons": [
                    {
                        "operator": "eq",
                        "left": {"kind": "text", "value": "a"},
                        "right": {"kind": "text", "value": "a"},
                    }
                ],
                "layers": ["api"],
            }
        ]
    elif mutation == "extra_api":
        data["operation_bindings"].pop()
    elif mutation == "path":
        data["apis"][0]["path"] = "/docs"
    elif mutation == "root_path":
        data["apis"][1]["path"] = "/{key}"
    elif mutation == "missing_screen":
        data["screens"] = []
    with pytest.raises(Unsupported):
        compile_contract(SpecBundle.model_validate(data), state)


def test_changed_approved_files_are_not_packaged():
    bundle, state, artifacts = inputs()
    artifacts["ddl.sql"] += b"-- changed"
    with pytest.raises(ValueError):
        generate(bundle, state, artifacts)


@pytest.mark.parametrize("name", ["../escape", "backend/app.py"])
def test_extra_or_duplicate_zip_entries_are_rejected_even_with_matching_outer_hash(name):
    bundle, state, artifacts = inputs()
    output = io.BytesIO(generate(bundle, state, artifacts))
    with (
        zipfile.ZipFile(output, "a") as archive,
        pytest.warns(UserWarning)
        if name == "backend/app.py"
        else __import__("contextlib").nullcontext(),
    ):
        archive.writestr(name, "changed")
    source = output.getvalue()
    with pytest.raises(ValueError):
        inspect_package(source, hashlib.sha256(source).hexdigest())


@pytest.mark.parametrize(
    "name", ["frontend/src/main.tsx", "frontend/vite.config.ts", "frontend/index.html"]
)
def test_untrusted_frontend_is_rejected_even_if_archive_hashes_are_rebuilt(name):
    source = generate(*inputs())
    with zipfile.ZipFile(io.BytesIO(source)) as archive:
        entries = archive.infolist()
        files = {entry.filename: archive.read(entry) for entry in entries}
    files[name] += b"\nmalicious change"
    manifest = json.loads(files["build-manifest.json"])
    manifest["files"][name] = hashlib.sha256(files[name]).hexdigest()
    files["build-manifest.json"] = json.dumps(manifest).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for entry in entries:
            archive.writestr(entry, files[entry.filename])
    changed = output.getvalue()
    with pytest.raises(ValueError, match="프런트엔드"):
        inspect_package(changed, hashlib.sha256(changed).hexdigest())
