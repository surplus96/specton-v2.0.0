"""Versioned implementation design documents. Original approved artifacts remain immutable."""

import csv
import hashlib
import io
import json
import zipfile

from specton.contracts.specification import SpecBundle
from specton.specification.readiness import canonical_bytes, domain_payload, spec_hash


def revised_files(bundle: SpecBundle, originals: dict[str, bytes]) -> dict[str, bytes]:
    for digest in bundle.baseline.artifacts:
        name = f"{digest.kind}.{digest.file_format}"
        if hashlib.sha256(originals.get(name, b"")).hexdigest() != digest.sha256:
            raise ValueError("승인 설계 산출물 해시가 다릅니다.")
    if (
        hashlib.sha256(originals.get("manifest.json", b"")).hexdigest()
        != bundle.baseline.manifest_hash
    ):
        raise ValueError("승인 설계 manifest 해시가 다릅니다.")
    lines = [
        f"# 실행 설계 · 명세 버전 {bundle.spec_version}",
        "",
        f"명세 ID: {bundle.spec_id}",
        f"명세 SHA-256: {spec_hash(bundle)}",
        "",
        "이 문서는 승인 원본에서 파생된 실행 명세의 기능·화면 계약입니다.",
        "승인 원본을 보존하고 실행 설계의 새 버전을 생성합니다. "
        "파생 스키마가 있으면 ERD·DDL에 함께 포함합니다.",
        "인수 사례는 검증 계획이며 자동으로 통과한 결과가 아닙니다.",
        "",
        "## 요구사항",
    ]
    for req in bundle.requirements:
        lines.extend(
            [f"### {req.id} · {req.priority}", req.text, f"범위 근거: {req.rationale}", ""]
        )
    lines.append("## 기능 계약")
    for case in bundle.use_cases:
        lines.extend(
            [
                f"### {case.id} · {case.name}",
                f"요구: {', '.join(case.req_ids)}",
                f"역할: {', '.join(case.actor_roles)}",
                *[f"- {step}" for step in case.steps],
                "",
            ]
        )
    lines.append("## 화면 계약")
    for screen in bundle.screens:
        lines.extend(
            [
                f"### {screen.id} · {screen.name}",
                f"경로: {screen.route}",
                f"역할: {', '.join(screen.actor_roles)}",
                f"API: {', '.join(screen.api_ids)}",
                f"빈 화면: {screen.empty_state}",
                f"로딩: {screen.loading_state}",
                f"오류: {screen.error_state}",
                "",
            ]
        )
    lines.append("## API 계약")
    for api in bundle.apis:
        lines.extend(
            [
                f"### {api.id} · {api.method} {api.path}",
                f"입력: {', '.join(f.name for f in api.request_fields)}",
                f"출력: {', '.join(f.name for f in api.response_fields)}",
                f"오류: {', '.join(api.error_codes)}",
                "",
            ]
        )
    lines.append("## 인수 계획")
    for test in bundle.acceptance_cases:
        lines.extend(
            [
                f"### {test.id}",
                f"요구: {', '.join(test.req_ids)}",
                f"조건: {test.when}",
                *[f"- 기대: {expected}" for expected in test.then],
                (
                    f"실행 계약: API · {test.execution.category} · "
                    f"{len(test.execution.steps)}단계 · 사례별 빈 DB"
                    if test.execution
                    else "자연어 계획: 자동 실행 계약 없음"
                ),
                "이 문서는 계획이며 실행 결과는 소스 해시에 연결된 검증 보고서에서 확인한다.",
                "",
            ]
        )
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(
        [
            "requirement_id",
            "legacy_id",
            "priority",
            "requirement",
            "use_cases",
            "apis",
            "screens",
            "acceptance_cases",
            "verification_status",
            "spec_version",
            "spec_hash",
        ]
    )
    for req in bundle.requirements:
        uses = [u.id for u in bundle.use_cases if req.id in u.req_ids]
        apis = [a.id for a in bundle.apis if a.use_case_id in uses]
        screens = [s.id for s in bundle.screens if set(s.api_ids) & set(apis)]
        # Prevent spreadsheet formula execution for user/customer supplied cells.
        row = [
            req.id,
            req.legacy_id or "",
            req.priority,
            req.text,
            ";".join(uses),
            ";".join(apis),
            ";".join(screens),
            ";".join(a.id for a in bundle.acceptance_cases if req.id in a.req_ids),
            "not_run",
            str(bundle.spec_version),
            spec_hash(bundle),
        ]
        writer.writerow(
            ["'" + cell if cell.lstrip().startswith(("=", "+", "-", "@")) else cell for cell in row]
        )
    if bundle.invariants:
        lines.extend(
            [
                "## 데이터 조건 계약",
                "```json",
                json.dumps(
                    [v.model_dump(mode="json") for v in bundle.invariants],
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                ),
                "```",
                "명시한 계층에서 검증하는 조건이며 검증 통과 결과를 뜻하지 않습니다.",
            ]
        )
    if bundle.domain:
        domain = domain_payload(bundle)
        lines.extend(
            [
                "## 도메인 실행 규칙",
                "```json",
                json.dumps(
                    domain,
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                ),
                "```",
                "저장은 원본 승인 DDL을 사용합니다. 도메인별 기본 테이블을 삽입하지 않습니다.",
            ]
        )
    if bundle.commerce:
        lines.extend(
            [
                "## 기본 업무 정책",
                "",
                "```json",
                json.dumps(
                    bundle.commerce.model_dump(mode="json"),
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                ),
                "```",
                "원본 논리 설계의 테이블 ID는 출처로 보존합니다. "
                "실제 데모 데이터는 별도 _specton_c_* 파생 테이블에 저장합니다.",
                "담당자 단일 역할의 시연이며 "
                "상용 회원점별 인증·운영 성능·보존 정책을 인증하지 않습니다.",
            ]
        )
    files = {
        "functions.md": ("\n".join(lines) + "\n").encode(),
        "rtm.csv": stream.getvalue().encode("utf-8-sig"),
        "erd.mmd": originals["erd.mmd"],
        "ddl.sql": originals["ddl.sql"],
        "executable-spec.json": canonical_bytes(bundle),
    }
    if bundle.commerce:
        from specton.implementation.commerce_schema import schema

        DDL, ERD = schema(bundle.commerce)
        policy = json.dumps(
            bundle.commerce.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        files["ddl.sql"] = (
            originals["ddl.sql"]
            + ("\n-- Derived wholesale demo schema; policy: " + policy + "\n" + DDL).encode()
        )
        files["erd.mmd"] = (
            originals["erd.mmd"] + ("\n%% Derived wholesale demo schema\n" + ERD).encode()
        )
    manifest = {
        "kind": "derived-executable-design",
        "spec_id": str(bundle.spec_id),
        "spec_version": bundle.spec_version,
        "spec_hash": spec_hash(bundle),
        "source_baseline": bundle.baseline.model_dump(mode="json"),
        "schema_change": bundle.commerce is not None,
        "storage_profile": bundle.commerce.storage if bundle.commerce else "approved-source",
        "business_acceptance": "not_run",
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())},
    }
    files["manifest.json"] = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, indent=2
    ).encode()
    return files


def archive(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as z:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            z.writestr(info, data)
    return output.getvalue()
