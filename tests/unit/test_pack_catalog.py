import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from specton.api.errors import ApiError
from specton.api.main import create_app
from specton.api.runs import _pack_version
from specton.config import Settings
from specton.packs.build import lock_content, pack_content_hash
from specton.packs.catalog import catalog
from specton.packs.loader import load_manifest


@pytest.fixture
def root(tmp_path):
    path = tmp_path / "packs"
    shutil.copytree(Path("domain_packs"), path)
    manifest = path / "maintenance/manifest.yaml"
    manifest.write_text(manifest.read_text().replace("status: approved", "status: draft"))
    version = load_manifest("maintenance", root=path).version
    (path / "maintenance/pack.lock").write_text(
        lock_content({version: pack_content_hash(path / "maintenance")})
    )
    return path


def test_catalog_and_creation_agree_on_draft_gate(root):
    settings = Settings(_env_file=None, pack_root=root)
    rows = {p.name: p for p in catalog(root)}
    assert rows["inventory"].selectable
    assert rows["inventory"].label == "재고관리"
    assert not rows["maintenance"].selectable
    assert rows["maintenance"].status == "draft"
    assert _pack_version(settings, "inventory") == rows["inventory"].version
    for name in ("maintenance", "../inventory", "common", "unknown"):
        with pytest.raises(ApiError):
            _pack_version(settings, name)


def test_same_version_tampering_is_not_selectable(root):
    file = root / "inventory/patterns.yaml"
    file.write_text(file.read_text() + "\n# unversioned change\n")
    rows = {p.name: p for p in catalog(root)}
    assert rows["inventory"].status == "invalid"
    with pytest.raises(ApiError):
        _pack_version(Settings(_env_file=None, pack_root=root), "inventory")


def test_new_pack_appears_without_client_changes_and_broken_pack_is_isolated(root):
    folder = root / "facilities"
    shutil.copytree(root / "maintenance", folder)
    path = folder / "manifest.yaml"
    path.write_text(path.read_text().replace("name: maintenance", "name: facilities"))
    version = load_manifest("facilities", root=root).version
    (folder / "pack.lock").write_text(lock_content({version: pack_content_hash(folder)}))
    (root / "maintenance/terms.yaml").write_text("terms: [broken")
    rows = {p.name: p for p in catalog(root)}
    assert rows["facilities"].status == "draft"
    assert rows["maintenance"].status == "invalid"
    assert rows["inventory"].selectable


def test_catalog_http_requires_no_customer_or_database_access(root):
    client = TestClient(create_app(Settings(_env_file=None, pack_root=root)))
    response = client.get("/api/v1/packs")
    assert response.status_code == 200
    assert {r["name"] for r in response.json()} == {"inventory", "maintenance"}
    response = client.get("/api/v1/capabilities")
    assert response.status_code == 200
    assert any(
        c["id"] == "multi_record" and c["status"] == "not_supported" for c in response.json()
    )
