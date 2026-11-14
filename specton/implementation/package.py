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

TEMPLATE_VERSION = "master-data-v1"
TEMPLATES = Path(__file__).parent / "templates"


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def generate(bundle: SpecBundle, state: DesignState, artifacts: dict[str, bytes]) -> bytes:
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
    files: dict[str, bytes] = {
        "spec/approved-spec.json": canonical_bytes(bundle),
        "spec/design-state.json": json_bytes(state.model_dump(mode="json")),
        "backend/app.py": (TEMPLATES / "runtime/app.py.txt").read_bytes(),
        "backend/contract.json": json_bytes(contract),
        "backend/approved.sql": artifacts["ddl.sql"],
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
    files["traceability.json"] = json_bytes(
        {
            "operations": [
                {
                    "api_id": a.id,
                    "use_case_id": a.use_case_id,
                    "req_ids": next(u.req_ids for u in bundle.use_cases if u.id == a.use_case_id),
                    "files": ["backend/app.py", "backend/contract.json", "frontend/src/main.tsx"],
                }
                for a in bundle.apis
            ],
            "acceptance_cases": [
                {
                    "id": t.id,
                    "status": "not_run",
                    "reason": "자연어 인수 사례는 자동 실행으로 판정하지 않습니다.",
                }
                for t in bundle.acceptance_cases
            ],
        }
    )
    files["README.md"] = b"""# Generated master-data application

Supported: insert/get using the approved schema, separate role tokens, idempotent insert.
Business acceptance, browser acceptance, inventory ledger commands and deployment are NOT certified.

1. Create an empty, isolated PostgreSQL 18 database and a non-superuser owner.
2. Install backend/requirements.txt with pip --require-hashes in a dedicated environment.
3. Set APP_DATABASE_URL and APP_TOKEN_HASHES (JSON: SHA256(token) -> list of approved role IDs).
   Generate random demo tokens outside this source tree; never use platform OAuth/session tokens.
4. From backend: python app.py (once), then uvicorn app:app --host 127.0.0.1 --port 8000.
5. From frontend: npm ci, npm run dev. The dev proxy forwards /api to localhost:8000.
   Production hosting and external preview authentication are not configured.
6. Use the Specton isolated verifier with the source archive and its trusted expected SHA256.
   Its DB/API smoke result does not mark natural-language acceptance cases passed.
"""
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
