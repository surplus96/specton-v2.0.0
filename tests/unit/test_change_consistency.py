import hashlib
import io
import json
import zipfile

import pytest
from transfer_support import change

from specton.implementation.consistency import check
from specton.implementation.data_transfer import plan
from specton.implementation.verify import inspect_package


@pytest.mark.parametrize("domain", ["booking", "maintenance"])
def test_same_schema_request_updates_spec_documents_and_runtime_together(domain):
    before, after, _, originals, _old, new, frozen, details = change(domain)
    files, _ = inspect_package(new, hashlib.sha256(new).hexdigest())
    assert check(files)["documents"] == "regenerated_exact"
    assert "고객 요청 화면" in files["design/revised/functions.md"].decode()
    assert '"value": "10"' in files["design/revised/functions.md"].decode()
    assert files["design/revised/ddl.sql"] == originals["ddl.sql"]
    assert files["design/revised/erd.mmd"] == originals["erd.mmd"]
    assert files["design/functions.md"] == originals["functions.md"]
    assert (
        before.requirements == after.requirements
        and before.acceptance_cases == after.acceptance_cases
    )
    assert frozen["status"] == "ready_for_rehearsal" and frozen["execution"] == "not_run"
    assert frozen["tables"][-1]["name"] == "_specton_commands"
    assert details["executable_change"]


def repack(source, target, content):
    with zipfile.ZipFile(io.BytesIO(source)) as z:
        entries = z.infolist()
        files = {x.filename: z.read(x) for x in entries}
    files[target] = content
    if target.startswith("design/revised/"):
        revised = json.loads(files["design/revised/manifest.json"])
        revised["files"][target.removeprefix("design/revised/")] = hashlib.sha256(
            content
        ).hexdigest()
        files["design/revised/manifest.json"] = json.dumps(revised).encode()
    build = json.loads(files["build-manifest.json"])
    build["files"] = {
        k: hashlib.sha256(v).hexdigest() for k, v in files.items() if k != "build-manifest.json"
    }
    files["build-manifest.json"] = json.dumps(build).encode()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        for entry in entries:
            z.writestr(entry, files[entry.filename])
    return stream.getvalue()


@pytest.mark.parametrize(
    "target",
    [
        "backend/contract.json",
        "frontend/src/contract.json",
        "backend/approved.sql",
        "design/revised/functions.md",
        "design/revised/erd.mmd",
        "design/revised/rtm.csv",
    ],
)
def test_resigned_outer_manifest_cannot_hide_divergent_runtime_or_documents(target):
    source = change()[5]
    content = b"{}" if target.endswith(".json") else b"altered"
    changed = repack(source, target, content)
    with pytest.raises(ValueError):
        inspect_package(changed, hashlib.sha256(changed).hexdigest())


def test_different_storage_structure_is_not_claimed_as_data_preserved():
    old = change("booking")[4]
    new = change("maintenance")[5]
    result = plan(old, hashlib.sha256(old).hexdigest(), new, hashlib.sha256(new).hexdigest())
    assert result["status"] == "blocked" and result["schema_changed"]
    assert result["execution"] == "not_run"
