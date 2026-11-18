"""Compare generated runtime and design documents to their sealed executable specification."""

import hashlib
import json
from typing import Any

from specton.contracts import DesignState
from specton.contracts.specification import SpecBundle
from specton.implementation.compiler import compile_contract
from specton.model_hash import model_hash
from specton.specification.documents import revised_files
from specton.specification.readiness import canonical_bytes, spec_hash


def check(files: dict[str, bytes], *, regenerate: bool = True) -> dict[str, Any]:
    spec = SpecBundle.model_validate_json(files["spec/approved-spec.json"])
    state = DesignState.model_validate_json(files["spec/design-state.json"])
    if model_hash(state) != spec.baseline.model_hash:
        raise ValueError("설계·실행 명세 모델 해시가 다릅니다.")
    expected = compile_contract(spec, state)
    for name in ("backend/contract.json", "frontend/src/contract.json"):
        if json.loads(files[name]) != expected:
            raise ValueError("실행 계약이 승인 명세와 다릅니다.")
    originals = {
        name.removeprefix("design/"): data
        for name, data in files.items()
        if name.startswith("design/") and not name.startswith("design/revised/")
    }
    revised = revised_files(spec, originals)  # Also validates original approval hashes.
    actual = {
        name.removeprefix("design/revised/"): data
        for name, data in files.items()
        if name.startswith("design/revised/")
    }
    manifest = json.loads(actual["manifest.json"])
    if (
        manifest.get("spec_hash") != spec_hash(spec)
        or manifest.get("spec_version") != spec.spec_version
        or manifest.get("source_baseline") != spec.baseline.model_dump(mode="json")
        or manifest.get("files")
        != {n: hashlib.sha256(v).hexdigest() for n, v in actual.items() if n != "manifest.json"}
        or actual["executable-spec.json"] != canonical_bytes(spec)
        or files["backend/approved.sql"] != actual["ddl.sql"]
    ):
        raise ValueError("파생 설계·DDL·명세 연결이 다릅니다.")
    if regenerate and actual != revised:
        raise ValueError("기능·ERD·DDL·RTM이 승인 실행 명세에서 재생성한 결과와 다릅니다.")
    return {
        "status": "passed",
        "spec_hash": spec_hash(spec),
        "documents": "regenerated_exact" if regenerate else "legacy_seal_checked",
        "runtime_contract": "matched",
        "business_acceptance": "not_run",
    }
