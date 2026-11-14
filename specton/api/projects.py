"""소유 프로젝트와 실제 승인 설계 baseline 연결."""

from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from specton.api.auth import Mutation, UserDep
from specton.api.deps import ConnDep, SettingsDep
from specton.api.session import _SESSION_FORMAT, SESSION_COOKIE
from specton.specification.approval import ApprovalMismatch, verify_approved_files

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


class ProjectInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)


class BaselineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: UUID
    revision: int = Field(ge=0)


def own(conn: ConnDep, project_id: UUID, user: UserDep) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM project WHERE id=%s AND owner_id=%s FOR UPDATE", (project_id, user["id"])
    ).fetchone()
    if row is None:
        raise HTTPException(404, "프로젝트를 찾을 수 없습니다")
    return row


@router.post("", operation_id="createProject", status_code=201)
def create(
    payload: ProjectInput, user: UserDep, conn: ConnDep, checked: Mutation
) -> dict[str, Any]:
    row = conn.execute(
        "INSERT INTO project(id,owner_id,name) VALUES(%s,%s,%s) RETURNING id,name",
        (uuid4(), user["id"], payload.name),
    ).fetchone()
    assert row is not None
    return row


@router.get("", operation_id="listProjects")
def listing(user: UserDep, conn: ConnDep) -> list[dict[str, Any]]:
    return conn.execute(
        "SELECT id,name FROM project WHERE owner_id=%s ORDER BY created_at DESC,id LIMIT 100",
        (user["id"],),
    ).fetchall()


@router.get("/{project_id}", operation_id="getProject")
def detail(project_id: UUID, user: UserDep, conn: ConnDep) -> dict[str, Any]:
    with conn.transaction():
        project = own(conn, project_id, user)
        baselines = conn.execute(
            "SELECT id,run_id,revision,artifact_hashes FROM design_baseline "
            "WHERE project_id=%s ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
    return {"id": project["id"], "name": project["name"], "baselines": baselines}


@router.post("/{project_id}/runs/{run_id}/claim", operation_id="claimRun")
def claim(
    project_id: UUID,
    run_id: UUID,
    request: Request,
    user: UserDep,
    conn: ConnDep,
    checked: Mutation,
) -> dict[str, str]:
    owner = f"user:{user['id']}"
    legacy = request.cookies.get(SESSION_COOKIE, "")
    proven_owners = {owner}
    if _SESSION_FORMAT.fullmatch(legacy):
        proven_owners.add(legacy)
    with conn.transaction():
        own(conn, project_id, user)
        run = conn.execute(
            "SELECT owner_ref FROM run WHERE run_id=%s FOR UPDATE", (run_id,)
        ).fetchone()
        if run is None or run["owner_ref"] not in proven_owners:
            raise HTTPException(404, "실행을 찾을 수 없습니다")
        existing = conn.execute(
            "SELECT project_id FROM project_run WHERE run_id=%s", (run_id,)
        ).fetchone()
        if existing and existing["project_id"] != project_id:
            raise HTTPException(409, "다른 프로젝트에 연결된 실행입니다")
        conn.execute("UPDATE run SET owner_ref=%s WHERE run_id=%s", (owner, run_id))
        conn.execute(
            "INSERT INTO project_run VALUES(%s,%s) ON CONFLICT DO NOTHING", (run_id, project_id)
        )
    return {"run_id": str(run_id)}


@router.post("/{project_id}/baselines", operation_id="createBaseline", status_code=201)
def baseline(
    project_id: UUID,
    payload: BaselineInput,
    user: UserDep,
    conn: ConnDep,
    settings: SettingsDep,
    checked: Mutation,
) -> dict[str, Any]:
    with conn.transaction():
        own(conn, project_id, user)
        linked = conn.execute(
            "SELECT 1 FROM project_run WHERE project_id=%s AND run_id=%s",
            (project_id, payload.run_id),
        ).fetchone()
        if linked is None:
            raise HTTPException(404, "프로젝트 실행을 찾을 수 없습니다")
        try:
            verified = verify_approved_files(
                conn,
                run_id=payload.run_id,
                revision=payload.revision,
                owner_ref=f"user:{user['id']}",
                storage_dir=settings.storage_dir,
            )
        except ApprovalMismatch:
            raise HTTPException(422, "승인·산출물·SQL 검증 근거가 일치하지 않습니다") from None
        row = conn.execute(
            "INSERT INTO design_baseline(id,project_id,run_id,revision,artifact_hashes,"
            "approval_id,model_hash,version) "
            "SELECT %s,%s,%s,%s,%s,%s,%s,coalesce(max(version),0)+1 "
            "FROM design_baseline WHERE project_id=%s "
            "ON CONFLICT(project_id,run_id,revision) "
            "DO NOTHING RETURNING id",
            (
                uuid4(),
                project_id,
                payload.run_id,
                payload.revision,
                Jsonb(verified.artifact_hashes),
                verified.approval_id,
                verified.model_hash,
                project_id,
            ),
        ).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT id FROM design_baseline WHERE project_id=%s AND run_id=%s AND revision=%s",
                (project_id, payload.run_id, payload.revision),
            ).fetchone()
        assert row is not None
    return {"id": row["id"], "artifact_hashes": verified.artifact_hashes}
