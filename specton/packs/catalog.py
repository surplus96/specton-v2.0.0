"""Discover packs and enforce the same admission policy in UI and run creation."""

from pathlib import Path
from typing import Literal

from pydantic import TypeAdapter
from yaml import YAMLError

from specton.contracts.base import Contract
from specton.packs.build import BuildError, pack_content_hash, read_lock_versions, read_yaml
from specton.packs.loader import PackName, available_packs, load_manifest, load_pack


class Display(Contract):
    label: str
    summary: str


class PackEntry(Contract):
    name: str
    label: str
    summary: str
    version: str | None
    common_version: str | None
    status: Literal["available", "draft", "invalid"]
    selectable: bool
    reason: str
    terms: int = 0
    patterns: int = 0


def entry(root: Path, name: str, display: Display | None = None) -> PackEntry:
    label, summary = (display.label, display.summary) if display else (name, "")
    version = common_version = None
    try:
        pack = load_pack(name, root=root)
        version, common_version = pack.manifest.version, pack.common.manifest.version
        summary = summary or pack.manifest.description
        for manifest in (pack.manifest, pack.common.manifest):
            folder = root / manifest.name
            if read_lock_versions(folder).get(manifest.version) != pack_content_hash(folder):
                raise ValueError("pack lock mismatch")
        approved = pack.manifest.status == pack.common.manifest.status == "approved"
        return PackEntry(
            name=name,
            label=label,
            summary=summary,
            version=version,
            common_version=common_version,
            status="available" if approved else "draft",
            selectable=approved,
            reason="설계 분석에 사용 가능 · 업무 구현 범위는 별도 진단"
            if approved
            else "팩 검토·승인 대기",
            terms=len(pack.terms),
            patterns=len(pack.patterns),
        )
    except (OSError, ValueError, BuildError, YAMLError, KeyError, TypeError):
        return PackEntry(
            name=name,
            label=label,
            summary=summary,
            version=version,
            common_version=common_version,
            status="invalid",
            selectable=False,
            reason="팩 형식·출처·버전 해시를 확인해야 합니다.",
        )


def catalog(root: Path) -> tuple[PackEntry, ...]:
    path = root / "catalog.yaml"
    displays = TypeAdapter(dict[PackName, Display]).validate_python(
        read_yaml(path) if path.is_file() else {}
    )
    return tuple(entry(root, name, displays.get(name)) for name in available_packs(root=root))


def require_selectable(root: Path, name: str) -> str:
    # Validate the identifier before reading any user-selected path.
    load_manifest(name, root=root)
    result = entry(root, name)
    if not result.selectable or result.version is None:
        raise ValueError(result.reason)
    return result.version
