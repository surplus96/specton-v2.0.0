import hashlib
import io
import json
import zipfile

import pytest
from customer_support import customer

from specton.implementation.comparison import archive as comparison_archive
from specton.implementation.delivery import EXTRA_TEMPLATES
from specton.implementation.package import (
    CALCULATION_TEMPLATES,
    COMMAND_TEMPLATES,
    TEMPLATE_VERSION,
    TEMPLATES,
    generate,
)
from specton.implementation.verify import inspect_package


def repack(files):
    manifest = json.loads(files["build-manifest.json"])
    manifest["files"] = {
        n: hashlib.sha256(v).hexdigest() for n, v in files.items() if n != "build-manifest.json"
    }
    files["build-manifest.json"] = json.dumps(manifest).encode()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, data in files.items():
            entry = zipfile.ZipInfo(name)
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, data)
    return stream.getvalue()


def contents():
    source = generate(*customer())
    return inspect_package(source, hashlib.sha256(source).hexdigest())[0]


@pytest.mark.parametrize("domain", ["booking", "maintenance"])
def test_delivery_is_domain_bound_deterministic_and_contains_no_account(domain):
    inputs = customer(domain)
    content = generate(*inputs)
    assert content == generate(*inputs)
    files, manifest = inspect_package(content, hashlib.sha256(content).hexdigest())
    assert manifest["template_version"] == TEMPLATE_VERSION
    delivery = json.loads(files["delivery.json"])
    assert delivery["default_accounts"] == [] and delivery["business_acceptance"] == "not_run"
    assert delivery["spec_hash"] == manifest["spec_hash"]
    assert files["backend/approved.sql"] == inputs[2]["ddl.sql"]
    assert (
        comparison_archive(
            {
                "source_zip": content,
                "source_hash": hashlib.sha256(content).hexdigest(),
                "spec_id": inputs[0].spec_id,
                "spec_version": inputs[0].spec_version,
                "spec_hash": manifest["spec_hash"],
                "template_version": manifest["template_version"],
            }
        )[0]
        == files
    )
    for name in ("auth", "serve", "manage", "domain", "app"):
        compile(files[f"backend/{name}.py"], name, "exec")


@pytest.mark.parametrize(
    "path",
    [
        "backend/auth.py",
        "backend/manage.py",
        "backend/serve.py",
        "OPERATIONS.md",
        "Dockerfile",
        "frontend/src/customer.tsx",
        "delivery.json",
    ],
)
def test_resigned_delivery_file_cannot_replace_fixed_templates_or_scope(path):
    files = contents()
    files[path] = b"{}" if path.endswith(".json") else b"forged"
    changed = repack(files)
    with pytest.raises(ValueError):
        inspect_package(changed, hashlib.sha256(changed).hexdigest())


@pytest.mark.parametrize(
    "version", ["executable-design-v7", "executable-design-v8", "executable-design-v9"]
)
def test_frozen_prior_templates_still_inspect(version):
    files = contents()
    for name in CALCULATION_TEMPLATES:
        del files[name]
    for name in COMMAND_TEMPLATES:
        del files[name]
    if version != "executable-design-v9":
        for name in (*EXTRA_TEMPLATES, "delivery.json"):
            del files[name]
    for name, template in (
        ("backend/app.py", "app.py.txt"),
        ("backend/domain.py", "domain.py.txt"),
        ("frontend/src/main.tsx", "main.tsx"),
    ):
        files[name] = (TEMPLATES / "legacy" / version / template).read_bytes()
    manifest = json.loads(files["build-manifest.json"])
    manifest["template_version"] = version
    files["build-manifest.json"] = json.dumps(manifest).encode()
    content = repack(files)
    assert (
        inspect_package(content, hashlib.sha256(content).hexdigest())[1]["template_version"]
        == version
    )
