"""실제 저장 승인 근거를 읽는 SDD 연결 경계. manifest의 선언만으로 승인하지 않는다."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from psycopg import Connection
from psycopg.rows import DictRow

from specton.contracts import DesignState
from specton.model_hash import model_hash
from specton.persistence.validations import REQUIRED_VERSIONS


class ApprovalMismatch(ValueError):
    """현재 파일·스냅샷·DB 승인 근거가 일치하지 않는다."""


@dataclass(frozen=True)
class VerifiedApproval:
    approval_id: UUID
    model_hash: str
    artifact_hashes: dict[str, str]


def verify_approved_files(
    conn: Connection[DictRow],
    *,
    run_id: UUID,
    revision: int,
    owner_ref: str,
    storage_dir: Path,
) -> VerifiedApproval:
    """호출자는 프로젝트 소유권도 확인해야 한다. 반환값 자체는 승인 토큰이 아니다.

    호출자의 트랜잭션에서 run을 잠그고 동일 revision의 최종 승인 근거를 검증한다.
    실제 파일은 저장소 경계를 벗어나거나 심볼릭 링크를 통과할 수 없다.
    """
    if not conn.info.transaction_status:
        raise ApprovalMismatch("명시적 트랜잭션이 필요합니다")
    run = conn.execute(
        "SELECT status, revision FROM run WHERE run_id=%s AND owner_ref=%s FOR UPDATE",
        (run_id, owner_ref),
    ).fetchone()
    if run is None or run["status"] != "completed" or run["revision"] != revision:
        raise ApprovalMismatch("접근 가능한 완료 revision이 아닙니다")
    snapshot = conn.execute(
        "SELECT normalized_model,model_hash FROM model_snapshot WHERE run_id=%s AND revision=%s",
        (run_id, revision),
    ).fetchone()
    if snapshot is None:
        raise ApprovalMismatch("승인 스냅샷이 없습니다")
    try:
        if (
            model_hash(
                DesignState.model_validate({**snapshot["normalized_model"], "run_id": str(run_id)})
            )
            != snapshot["model_hash"]
        ):
            raise ApprovalMismatch("스냅샷 해시가 일치하지 않습니다")
    except ValueError as exc:
        raise ApprovalMismatch("스냅샷을 확인할 수 없습니다") from exc
    rows = conn.execute(
        "SELECT a.kind,a.file_format,a.hash,a.storage_ref,b.artifact_hash,"
        "p.approval_id,s.model_hash,v.status AS validation_status,"
        "v.artifact_hash AS validated_hash,v.model_hash AS validated_model,"
        "v.validator_version,v.policy_version,v.postgres_version "
        "FROM model_snapshot s JOIN artifact a USING(snapshot_id) "
        "JOIN approval_basis b USING(artifact_id) "
        "JOIN approval p ON p.approval_id=b.approval_id AND p.snapshot_id=s.snapshot_id "
        "AND p.run_id=s.run_id "
        "LEFT JOIN artifact_validation v ON v.validation_id=b.validation_id "
        "AND v.artifact_id=a.artifact_id "
        "WHERE s.run_id=%s AND s.revision=%s AND p.decision='approve' "
        "AND a.approval_status='approved'",
        (run_id, revision),
    ).fetchall()
    required = {
        ("functions", "md"),
        ("erd", "mmd"),
        ("ddl", "sql"),
        ("rtm", "csv"),
        ("manifest", "json"),
    }
    chosen = [r for r in rows if (r["kind"], r["file_format"]) in required]
    if len(chosen) != len(required) or len({r["approval_id"] for r in chosen}) != 1:
        raise ApprovalMismatch("동일 최종 승인의 네 산출물과 manifest가 필요합니다")
    try:
        root = storage_dir.resolve(strict=True)
    except OSError as exc:
        raise ApprovalMismatch("산출물 저장소를 확인할 수 없습니다") from exc
    result = {}
    manifest = None
    for row in chosen:
        relative = Path(row["storage_ref"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ApprovalMismatch("허용하지 않는 산출물 경로입니다")
        candidate = root
        for part in relative.parts:
            candidate = candidate / part
            if candidate.is_symlink():
                raise ApprovalMismatch("심볼릭 링크 산출물은 허용하지 않습니다")
        try:
            candidate.resolve(strict=True).relative_to(root)
            content = candidate.read_bytes()
        except (OSError, ValueError) as exc:
            raise ApprovalMismatch("산출물을 확인할 수 없습니다") from exc
        if row["kind"] == "manifest":
            try:
                manifest = json.loads(content)
            except (ValueError, UnicodeDecodeError) as exc:
                raise ApprovalMismatch("manifest 형식 오류") from exc
        digest = hashlib.sha256(content).hexdigest()
        if digest != row["hash"] or digest != row["artifact_hash"]:
            raise ApprovalMismatch("승인 뒤 산출물이 변경됐습니다")
        if row["kind"] == "ddl" and (
            row["validation_status"] != "passed"
            or row["validated_hash"] != digest
            or row["validated_model"] != row["model_hash"]
            or any(row[k] != value for k, value in REQUIRED_VERSIONS.items())
        ):
            raise ApprovalMismatch("승인 DDL의 유효한 검증 근거가 없습니다")
        result[f"{row['kind']}.{row['file_format']}"] = digest
    if not isinstance(manifest, dict) or (
        manifest.get("run_id") != str(run_id)
        or str(manifest.get("revision")) != str(revision)
        or manifest.get("model_hash") != snapshot["model_hash"]
        or manifest.get("approved") is not True
    ):
        raise ApprovalMismatch("manifest 기준 정보가 일치하지 않습니다")
    listed = manifest.get("files")
    if not isinstance(listed, list):
        raise ApprovalMismatch("manifest 파일 목록이 없습니다")
    for row in chosen:
        if (
            row["kind"] != "manifest"
            and listed.count(
                {"kind": row["kind"], "file_format": row["file_format"], "hash": row["hash"]}
            )
            != 1
        ):
            raise ApprovalMismatch("manifest 파일 해시가 일치하지 않습니다")
    return VerifiedApproval(chosen[0]["approval_id"], snapshot["model_hash"], result)
