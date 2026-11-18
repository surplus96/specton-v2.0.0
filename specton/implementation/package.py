"""고정 경로만 사용하는 결정론 소스 묶음. 파일을 실행하지 않는다."""

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

from specton.contracts import DesignState
from specton.contracts.specification import SpecBundle
from specton.implementation.compiler import compile_contract
from specton.model_hash import model_hash
from specton.specification.readiness import canonical_bytes, spec_hash

TEMPLATE_VERSION = "executable-design-v11"
TEMPLATES = Path(__file__).parent / "templates"
COMMAND_TEMPLATES = {
    "backend/commands.py": "runtime/commands.py.txt",
    "frontend/src/commands.tsx": "frontend/src/commands.tsx",
    "ATOMIC_COMMANDS.md": "delivery/ATOMIC_COMMANDS.md",
}

CALCULATION_TEMPLATES = {
    "backend/calculations.py": "runtime/calculations.py.txt",
    "CALCULATIONS.md": "delivery/CALCULATIONS.md",
}


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def generate(bundle: SpecBundle, state: DesignState, artifacts: dict[str, bytes]) -> bytes:
    if any(a.path == "/auth" or a.path.startswith("/auth/") for a in bundle.apis):
        raise ValueError("고객 인증용 /auth 경로는 업무 API로 사용할 수 없습니다")
    if model_hash(state) != bundle.baseline.model_hash:
        raise ValueError("설계 스냅샷과 명세의 모델 해시가 다릅니다")
    contract = compile_contract(bundle, state)
    for artifact in bundle.baseline.artifacts:
        name = f"{artifact.kind}.{artifact.file_format}"
        if hashlib.sha256(artifacts.get(name, b"")).hexdigest() != artifact.sha256:
            raise ValueError("승인 산출물 바이트가 명세와 다릅니다")
    if (
        hashlib.sha256(artifacts.get("manifest.json", b"")).hexdigest()
        != bundle.baseline.manifest_hash
    ):
        raise ValueError("승인 manifest 바이트가 명세와 다릅니다")
    from specton.specification.documents import revised_files

    revised = revised_files(bundle, artifacts)
    files: dict[str, bytes] = {
        "spec/approved-spec.json": canonical_bytes(bundle),
        "spec/design-state.json": json_bytes(state.model_dump(mode="json")),
        "backend/app.py": (TEMPLATES / "runtime/app.py.txt").read_bytes(),
        "backend/inventory.py": (TEMPLATES / "runtime/inventory.py.txt").read_bytes(),
        "backend/contract.json": json_bytes(contract),
        "backend/approved.sql": revised["ddl.sql"] if bundle.commerce else artifacts["ddl.sql"],
        "backend/domain.py": (TEMPLATES / "runtime/domain.py.txt").read_bytes(),
        "backend/commerce.py": (TEMPLATES / "runtime/commerce.py.txt").read_bytes(),
        "backend/requirements.txt": (TEMPLATES / "runtime/requirements.txt").read_bytes(),
        "frontend/src/contract.json": json_bytes(contract),
    }
    for name in (
        "package.json",
        "package-lock.json",
        "tsconfig.json",
        "vite.config.ts",
        "index.html",
        "src/main.tsx",
    ):
        files["frontend/" + name] = (TEMPLATES / "frontend" / name).read_bytes()
    for name, content in artifacts.items():
        if name not in {"functions.md", "erd.mmd", "ddl.sql", "rtm.csv", "manifest.json"}:
            raise ValueError("지원하지 않는 출처 파일")
        files["design/" + name] = content
    for name, content in revised.items():
        files["design/revised/" + name] = content
    files["traceability.json"] = json_bytes(
        {
            "operations": [
                {
                    "api_id": a.id,
                    "use_case_id": a.use_case_id,
                    "req_ids": next(u.req_ids for u in bundle.use_cases if u.id == a.use_case_id),
                    "files": [
                        "backend/app.py",
                        "backend/inventory.py",
                        "backend/contract.json",
                        "frontend/src/main.tsx",
                    ],
                }
                for a in bundle.apis
            ],
            "acceptance_cases": [
                {
                    "id": t.id,
                    "status": "not_run",
                    "reason": "승인된 API 시나리오는 격리 검증 후 결과를 확인하세요."
                    if t.execution
                    else "자연어 인수 사례는 자동 실행으로 판정하지 않습니다.",
                }
                for t in bundle.acceptance_cases
            ],
        }
    )
    from specton.implementation.delivery import EXTRA_TEMPLATES
    from specton.implementation.delivery import manifest as delivery_manifest

    for name, template in EXTRA_TEMPLATES.items():
        files[name] = (TEMPLATES / template).read_bytes()
    for name, template in (COMMAND_TEMPLATES | CALCULATION_TEMPLATES).items():
        files[name] = (TEMPLATES / template).read_bytes()
    files["delivery.json"] = json_bytes(delivery_manifest(bundle))
    files["README.md"] = """# 승인 설계 기반 고객 앱

설치·계정 관리·백업/복구·납품 인수 절차는 OPERATIONS.md를 따르세요.
먼저 ZIP의 SHA-256을 Specton의 신뢰한 소스 해시와 비교하고
python verify_delivery.py로 파일 무결성을 확인하세요.
고객 앱은 별도 로컬 계정·서버 세션을 사용합니다. 기본 계정은 없습니다.
APP_DATABASE_URL은 플랫폼과 분리한 빈 전용 DB를 가리켜야 합니다.
APP_AUTH_MODE=session과 실제 APP_ORIGIN을 설정하고 승인 명세의 역할로 계정을 만드세요.

명세·역할·기술 테이블·납품 범위: delivery.json
다중 레코드 명령의 지원 범위·역할·재시도: ATOMIC_COMMANDS.md
계산·집계의 단위·범위·반올림·실패 정책: CALCULATIONS.md
승인 원본: design/ / 변경 실행 설계: design/revised/
도메인 레코드·관계·명시한 업무 조건만 실행하며 미지원 업무를 추정하지 않습니다.
계정별 행 접근·외부 SSO·스키마 변경 이전·운영 배포·시각 디자인 명세는 별도 범위입니다.
검증/미리보기의 APP_TOKEN_HASHES 역할 토큰 모드는 고객 로그인과 별개입니다.
소스 생성은 업무 인수·설치·복구 성공을 자동 인증하지 않습니다.
""".encode()
    if bundle.commerce:
        files["README.md"] += (
            b"\n## Wholesale demonstration\n"
            b"Fourteen fixed commands and six screens cover products, units, members, receipts, "
            b"orders, returns and in-app alerts. Source table IDs are provenance references; "
            b"demo transactions use the explicitly derived _specton_c_* schema "
            b"in backend/approved.sql. "
            b"Apply this full script only to a fresh database. It is not a live data migration.\n"
            b"Review the policy and excluded requirements in "
            b"design/revised/functions.md before approval. "
            b"Use an operator token; member-by-member authentication "
            b"and production SLAs are out of scope.\n"
        )
    files["build-manifest.json"] = json_bytes(
        {
            "template_version": TEMPLATE_VERSION,
            "spec_hash": spec_hash(bundle),
            "files": {
                name: hashlib.sha256(content).hexdigest() for name, content in sorted(files.items())
            },
        }
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    return output.getvalue()
