"""Bounded, read-only comparison of sealed source archives and fixed verification coverage."""

import difflib
import hashlib
import io
import json
import zipfile
from typing import Any

from specton.contracts.specification import SpecBundle
from specton.implementation.package import json_bytes
from specton.implementation.verify import ALLOWED
from specton.specification.readiness import spec_hash


def digest(value: Any) -> str:
    return hashlib.sha256(json_bytes(value)).hexdigest()


def archive(row: dict[str, Any]) -> tuple[dict[str, bytes], dict[str, Any]]:
    content = bytes(row["source_zip"])
    if len(content) > 10 * 1024 * 1024 or hashlib.sha256(content).hexdigest() != row["source_hash"]:
        raise ValueError("소스 해시 불일치")
    with zipfile.ZipFile(io.BytesIO(content)) as package:
        entries = package.infolist()
        if (
            len(entries) != len(ALLOWED)
            or {e.filename for e in entries} != ALLOWED
            or sum(e.file_size for e in entries) > 10 * 1024 * 1024
            or any((e.external_attr >> 16) & 0o170000 != 0o100000 for e in entries)
        ):
            raise ValueError("소스 경로·크기·중복·링크 오류")
        files = {entry.filename: package.read(entry) for entry in entries}
    manifest = json.loads(files["build-manifest.json"])
    if not isinstance(manifest, dict) or manifest.get("files") != {
        key: hashlib.sha256(value).hexdigest()
        for key, value in files.items()
        if key != "build-manifest.json"
    }:
        raise ValueError("소스 내부 manifest 불일치")
    spec = SpecBundle.model_validate_json(files["spec/approved-spec.json"])
    if (
        str(spec.spec_id) != str(row["spec_id"])
        or spec.spec_version != row["spec_version"]
        or spec_hash(spec) != row["spec_hash"]
        or manifest.get("spec_hash") != row["spec_hash"]
        or manifest.get("template_version") != row["template_version"]
    ):
        raise ValueError("소스와 승인 명세 연결 불일치")
    return files, spec.model_dump(mode="json")


def file_changes(before: dict[str, bytes], after: dict[str, bytes]) -> list[dict[str, Any]]:
    result = []
    budget = 65536
    for name in sorted(before.keys() | after.keys()):
        old, new = before.get(name), after.get(name)
        if old == new:
            continue
        item = {
            "path": name,
            "change": "added" if old is None else "removed" if new is None else "modified",
            "before_hash": hashlib.sha256(old).hexdigest() if old is not None else None,
            "after_hash": hashlib.sha256(new).hexdigest() if new is not None else None,
            "diff": None,
            "truncated": True,
        }
        if budget and max(len(old or b""), len(new or b"")) <= 65536:
            try:
                left = (old or b"").decode().splitlines()
                right = (new or b"").decode().splitlines()
                if max(len(left), len(right)) <= 1500:
                    value = "\n".join(
                        difflib.unified_diff(
                            left, right, fromfile="before/" + name, tofile="after/" + name, n=3
                        )
                    )
                    limit = min(8192, budget)
                    item.update(diff=value[:limit], truncated=len(value) > limit)
                    budget -= min(len(value), limit)
            except UnicodeError:
                pass
        result.append(item)
    return result


def semantic_changes(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for section in (
        "requirements",
        "roles",
        "entities",
        "use_cases",
        "invariants",
        "apis",
        "screens",
        "acceptance_cases",
        "questions",
    ):
        left = {item["id"]: item for item in before.get(section, [])}
        right = {item["id"]: item for item in after.get(section, [])}
        result[section] = {
            "added": sorted(right.keys() - left.keys()),
            "removed": sorted(left.keys() - right.keys()),
            "modified": sorted(
                key for key in left.keys() & right.keys() if left[key] != right[key]
            ),
        }
    result["inventory_changed"] = before.get("inventory") != after.get("inventory")
    result["operations_changed"] = before.get("operation_bindings") != after.get(
        "operation_bindings"
    )
    result["storage_changed"] = before.get("storage_bindings") != after.get("storage_bindings")
    return result


def evidence(row: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    from specton.implementation.jobs import public

    public(row)
    report = row["report"]
    if (
        row["status"] != "smoke_passed"
        or not isinstance(report, dict)
        or report.get("status") != "smoke_passed"
        or report.get("cleanup_complete") is not True
        or report.get("browser_acceptance") != "passed"
        or report.get("business_acceptance") != "not_run"
        or not row["browser_image"]
        or not row["browser_suite_hash"]
    ):
        raise ValueError("정리와 브라우저 검증까지 통과한 결과가 필요합니다")
    for key in ("source_hash", "spec_hash"):
        if row[key] != source[key]:
            raise ValueError("검증과 소스 해시 불일치")
    for key in (
        "source_hash",
        "spec_hash",
        "runtime_image",
        "postgres_image",
        "suite_hash",
        "browser_image",
        "browser_suite_hash",
    ):
        if report.get(key) != row[key]:
            raise ValueError("검증 출처 해시 불일치")
    browser = report.get("browser", {})
    if not isinstance(browser, dict):
        raise ValueError("브라우저 검증 형식 오류")
    for checks in (report.get("checks"), browser.get("checks")):
        if (
            not isinstance(checks, list)
            or not checks
            or any(not isinstance(c, dict) or c.get("status") != "passed" for c in checks)
        ):
            raise ValueError("검증 항목 통과 증거 누락")
    if browser.get("status") != "passed":
        raise ValueError("브라우저 검증 누락")
    return {
        key: str(row[key])
        for key in (
            "id",
            "source_hash",
            "spec_hash",
            "report_hash",
            "runtime_image",
            "postgres_image",
            "suite_hash",
            "browser_image",
            "browser_suite_hash",
        )
    } | {
        "checks": report["checks"],
        "browser_checks": browser["checks"],
        "browser_profile": browser.get("profile"),
        "screenshot_sha256": browser.get("screenshot_sha256"),
        "business_acceptance": "not_run",
        "browser_acceptance": "passed",
    }
