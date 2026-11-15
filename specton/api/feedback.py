"""Quoted customer requests, explicit external analysis consent, reviewed SDD changes."""

from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter
from psycopg.types.json import Jsonb
from pydantic import Field

from specton.api import implementations, specifications
from specton.api.adoptions import latest
from specton.api.auth import Mutation, UserDep
from specton.api.deps import ConnDep, SettingsDep
from specton.api.projects import own
from specton.api.specifications import Expected, fail, load, view
from specton.contracts.base import Contract
from specton.contracts.specification import Sha256, SpecBundle
from specton.feedback import analysis, jobs
from specton.implementation.comparison import digest

router = APIRouter(prefix="/api/v1", tags=["feedback"])


class NewChange(Contract):
    project_id: UUID
    request_key: UUID
    title: str = Field(min_length=1, max_length=200)
    quote: str = Field(min_length=1, max_length=8000)
    instruction: str = Field(default="", max_length=4000)


class Version(Contract):
    expected_version: int = Field(ge=1)


class Analyse(Version):
    consent_external_analysis: Literal[True]


class Review(Version):
    analysis: analysis.Analysis


class Clarification(Version):
    instruction: str = Field(min_length=1, max_length=4000)


class Decision(Version):
    target_hash: Sha256
    decision: Literal["approve", "reject"]
    note: str = Field(min_length=10, max_length=2000)
    acknowledge_unverified_acceptance: Literal[True]


def event(conn: ConnDep, row: dict[str, Any], user: UserDep, action: str, note: str) -> None:
    conn.execute(
        "INSERT INTO feedback_event(id,change_id,actor_id,action,target_hash,note) "
        "VALUES(%s,%s,%s,%s,%s,%s)",
        (uuid4(), row["id"], user["id"], action, row.get("proposal_hash"), note),
    )


def snapshot(
    conn: ConnDep,
    row: dict[str, Any],
    details: dict[str, Any],
    proposal: dict[str, Any],
    target_hash: str,
) -> None:
    payload = {
        "analysis": details,
        "proposal": proposal,
        "proposal_hash": target_hash,
        "base_adoption_id": str(row["base_adoption_id"]),
        "spec_hash": row["spec_hash"],
        "quote": row["quote"],
        "instruction": row["instruction"],
    }
    conn.execute(
        "INSERT INTO feedback_revision(change_id,version,payload,payload_hash) VALUES(%s,%s,%s,%s)",
        (row["id"], row["version"] + 1, Jsonb(payload), digest(payload)),
    )


def message(conn: ConnDep, mid: UUID, user: UserDep) -> dict[str, Any]:
    row = conn.execute(
        "SELECT m.* FROM feedback_message m JOIN gmail_connection g ON g.id=m.connection_id "
        "WHERE m.id=%s AND g.owner_id=%s AND m.deleted_at IS NULL",
        (mid, user["id"]),
    ).fetchone()
    if row is None:
        fail(404, "메일을 찾을 수 없습니다.")
    return row


def change(conn: ConnDep, cid: UUID, user: UserDep) -> dict[str, Any]:
    # All mutations use user -> project -> change -> job lock order.
    conn.execute("SELECT id FROM app_user WHERE id=%s FOR KEY SHARE", (user["id"],))
    row = conn.execute("SELECT project_id FROM feedback_change WHERE id=%s", (cid,)).fetchone()
    if row is None:
        fail(404, "변경 요청을 찾을 수 없습니다.")
    own(conn, row["project_id"], user)
    result = conn.execute("SELECT * FROM feedback_change WHERE id=%s FOR UPDATE", (cid,)).fetchone()
    assert result is not None
    return result


def fresh(conn: ConnDep, row: dict[str, Any], user: UserDep) -> specifications.SpecView:
    current = latest(conn, row["project_id"])
    if current is None or current["id"] != str(row["base_adoption_id"]):
        fail(409, "채택 기준이 바뀌었습니다. 최신 기준으로 변경 요청을 다시 등록하세요.")
    base, version = load(conn, row["spec_id"], user)
    newest = conn.execute(
        "SELECT id FROM design_baseline WHERE project_id=%s ORDER BY version DESC LIMIT 1",
        (row["project_id"],),
    ).fetchone()
    spec = view(conn, row["spec_id"], version)
    if (
        newest is None
        or newest["id"] != base["id"]
        or version != row["spec_version"]
        or spec.readiness.spec_hash != row["spec_hash"]
        or spec.status != "approved"
    ):
        fail(409, "설계 또는 승인 명세가 바뀌었습니다. 최신 기준으로 다시 검토하세요.")
    return spec


def expected(row: dict[str, Any], payload: Version) -> None:
    if row["version"] != payload.expected_version:
        fail(409, "변경 요청이 갱신됐습니다. 다시 조회하세요.")


@router.get("/feedback", operation_id="listFeedbackMessages")
def inbox(user: UserDep, conn: ConnDep, before: UUID | None = None) -> dict[str, Any]:
    # UUID cursor references a stable (created_at,id) tuple, not Gmail's unordered IDs.
    rows = conn.execute(
        "SELECT m.id,m.subject,m.sender,m.received_at,m.connection_id,"
        "m.created_at FROM feedback_message m "
        "JOIN gmail_connection g ON g.id=m.connection_id WHERE g.owner_id=%s AND "
        "m.deleted_at IS NULL "
        "AND (%s::uuid IS NULL OR (m.created_at,m.id)<"
        "(SELECT created_at,id FROM feedback_message WHERE id=%s)) "
        "ORDER BY m.created_at DESC,m.id DESC LIMIT 51",
        (user["id"], before, before),
    ).fetchall()
    return {"items": rows[:50], "next": str(rows[49]["id"]) if len(rows) > 50 else None}


@router.get("/feedback/{message_id}", operation_id="getFeedbackMessage")
def detail(message_id: UUID, user: UserDep, conn: ConnDep) -> dict[str, Any]:
    return message(conn, message_id, user)


@router.get("/feedback-jobs", operation_id="listFeedbackJobs")
def work(user: UserDep, conn: ConnDep) -> list[dict[str, Any]]:
    return [
        jobs.public(row)
        for row in conn.execute(
            "SELECT * FROM feedback_job WHERE owner_id=%s ORDER BY created_at DESC,"
            "id DESC LIMIT 30",
            (user["id"],),
        ).fetchall()
    ]


@router.post("/feedback/{message_id}/changes", operation_id="createFeedbackChange", status_code=201)
def create(
    message_id: UUID, payload: NewChange, user: UserDep, conn: ConnDep, checked: Mutation
) -> dict[str, Any]:
    with conn.transaction():
        conn.execute("SELECT id FROM app_user WHERE id=%s FOR KEY SHARE", (user["id"],))
        own(conn, payload.project_id, user)
        mail = message(conn, message_id, user)
        if payload.quote not in mail["body"]:
            fail(422, "선택한 인용은 메일 본문의 정확한 부분이어야 합니다.")
        request_hash = digest({"message_id": str(message_id), **payload.model_dump(mode="json")})
        old = conn.execute(
            "SELECT * FROM feedback_change WHERE project_id=%s AND request_key=%s",
            (payload.project_id, payload.request_key),
        ).fetchone()
        if old:
            if old["request_hash"] != request_hash:
                fail(409, "같은 요청 키의 내용이 다릅니다.")
            return old
        adopted = latest(conn, payload.project_id)
        if adopted is None:
            fail(422, "먼저 프로젝트의 검증 후보를 채택하세요.")
        src = adopted["source"]
        row = conn.execute(
            "INSERT INTO feedback_change(id,project_id,message_id,request_key,request_hash,title,"
            "quote,instruction,state,base_adoption_id,spec_id,spec_version,spec_hash,created_by) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'received',%s,%s,%s,%s,%s) RETURNING *",
            (
                uuid4(),
                payload.project_id,
                message_id,
                payload.request_key,
                request_hash,
                payload.title,
                payload.quote,
                payload.instruction,
                adopted["id"],
                src["spec_id"],
                src["spec_version"],
                src["spec_hash"],
                user["id"],
            ),
        ).fetchone()
        assert row is not None
        fresh(conn, row, user)
        event(conn, row, user, "received", "메일 원문을 인용해 변경 요청 등록")
        return row


@router.get("/projects/{project_id}/changes", operation_id="listProjectChanges")
def listing(project_id: UUID, user: UserDep, conn: ConnDep) -> list[dict[str, Any]]:
    with conn.transaction():
        own(conn, project_id, user)
        return conn.execute(
            "SELECT id,title,state,version,created_at,implementation_id FROM feedback_change "
            "WHERE project_id=%s ORDER BY created_at DESC,id DESC LIMIT 100",
            (project_id,),
        ).fetchall()


@router.get("/changes/{change_id}", operation_id="getFeedbackChange")
def get(change_id: UUID, user: UserDep, conn: ConnDep) -> dict[str, Any]:
    with conn.transaction():
        row = change(conn, change_id, user)
        records = conn.execute(
            "SELECT action,target_hash,note,created_at FROM feedback_event "
            "WHERE change_id=%s ORDER BY created_at,id",
            (change_id,),
        ).fetchall()
        verification = None
        if row["implementation_id"]:
            verification = conn.execute(
                "SELECT id,status,report->>'browser_acceptance' AS browser_acceptance "
                "FROM implementation_verification WHERE implementation_id=%s "
                "ORDER BY created_at DESC,id DESC LIMIT 1",
                (row["implementation_id"],),
            ).fetchone()
        current = latest(conn, row["project_id"])
        return {
            **row,
            "events": records,
            "verification": verification,
            "baseline_stale": current is None or current["id"] != str(row["base_adoption_id"]),
        }


@router.post("/changes/{change_id}/analyse", operation_id="analyseFeedbackChange", status_code=202)
def analyse(
    change_id: UUID,
    payload: Analyse,
    user: UserDep,
    conn: ConnDep,
    settings: SettingsDep,
    checked: Mutation,
) -> dict[str, Any]:
    if not settings.feedback_analysis_enabled or not settings.openai_api_key:
        fail(503, "외부 분석 활성화와 OpenAI 키 설정이 필요합니다.")
    with conn.transaction():
        conn.execute("SELECT id FROM app_user WHERE id=%s FOR UPDATE", (user["id"],))
        row = change(conn, change_id, user)
        expected(row, payload)
        if row["state"] not in (
            "received",
            "needs_input",
            "failed",
            "awaiting_decision",
            "analysing",
        ):
            fail(409, "현재 상태에서는 분석할 수 없습니다.")
        fresh(conn, row, user)
        message(conn, row["message_id"], user)
        if row["state"] == "analysing":
            return jobs.public(jobs.enqueue(conn, user["id"], "analyse", change_id, row["version"]))
        count = conn.execute(
            "SELECT count(*) AS n FROM feedback_job WHERE owner_id=%s AND kind='analyse' "
            "AND created_at>now()-interval '24 hours'",
            (user["id"],),
        ).fetchone()
        if count and count["n"] >= settings.feedback_daily_analysis_limit:
            fail(429, "24시간 분석 요청 한도에 도달했습니다.")
        conn.execute(
            "UPDATE feedback_change SET state='analysing',version=version+1,"
            "approved_hash=NULL WHERE id=%s",
            (change_id,),
        )
        event(
            conn,
            row,
            user,
            "external_analysis_consent",
            "선택 원문·사용자 지시·승인 명세의 외부 모델 전송에 동의",
        )
        return jobs.public(jobs.enqueue(conn, user["id"], "analyse", change_id, row["version"] + 1))


@router.put("/changes/{change_id}/proposal", operation_id="reviewFeedbackProposal")
def review(
    change_id: UUID, payload: Review, user: UserDep, conn: ConnDep, checked: Mutation
) -> dict[str, Any]:
    with conn.transaction():
        row = change(conn, change_id, user)
        expected(row, payload)
        if row["state"] not in ("received", "awaiting_decision", "needs_input", "failed"):
            fail(409, "분석 중이거나 승인된 변경안은 수정할 수 없습니다.")
        spec = fresh(conn, row, user)
        message(conn, row["message_id"], user)
        try:
            proposed, details = analysis.propose(spec.bundle, payload.analysis, row["quote"])
        except ValueError:
            fail(422, "변경안의 인용·수정 대상·실행 명세를 확인하세요.")
        document = proposed.model_dump(mode="json")
        target_hash = analysis.proposal_hash(row["spec_hash"], row["quote"], document, details)
        status = (
            "needs_input"
            if (
                payload.analysis.questions
                or payload.analysis.unsupported
                or not details["executable_change"]
            )
            else "awaiting_decision"
        )
        conn.execute(
            "UPDATE feedback_change SET analysis=%s,proposal=%s,proposal_hash=%s,"
            "approved_hash=NULL,"
            "state=%s,version=version+1 WHERE id=%s",
            (Jsonb(details), Jsonb(document), target_hash, status, change_id),
        )
        snapshot(conn, row, details, document, target_hash)
        event(
            conn,
            {**row, "proposal_hash": target_hash},
            user,
            "proposal_reviewed",
            "사용자가 제한된 명세 변경안을 검토·수정",
        )
    return get(change_id, user, conn)


@router.post("/changes/{change_id}/decide", operation_id="decideFeedbackChange")
def decide(
    change_id: UUID, payload: Decision, user: UserDep, conn: ConnDep, checked: Mutation
) -> dict[str, Any]:
    with conn.transaction():
        row = change(conn, change_id, user)
        expected(row, payload)
        if row["state"] != "awaiting_decision" or row["proposal_hash"] != payload.target_hash:
            fail(409, "검토 대상 또는 상태가 바뀌었습니다.")
        fresh(conn, row, user)
        if (
            analysis.proposal_hash(row["spec_hash"], row["quote"], row["proposal"], row["analysis"])
            != payload.target_hash
        ):
            fail(422, "변경안 해시가 일치하지 않습니다.")
        conn.execute(
            "UPDATE feedback_change SET state=%s,approved_hash=%s,version=version+1 WHERE id=%s",
            (
                "approved" if payload.decision == "approve" else "rejected",
                payload.target_hash if payload.decision == "approve" else None,
                change_id,
            ),
        )
        event(conn, row, user, payload.decision, payload.note)
    return get(change_id, user, conn)


@router.post("/changes/{change_id}/implement", operation_id="implementFeedbackChange")
def implement(
    change_id: UUID,
    payload: Version,
    user: UserDep,
    conn: ConnDep,
    settings: SettingsDep,
    checked: Mutation,
) -> dict[str, Any]:
    with conn.transaction():
        row = change(conn, change_id, user)
        if row["implementation_id"]:
            return get(change_id, user, conn)  # Retry returns the original immutable candidate.
        expected(row, payload)
        if row["state"] != "approved" or row["approved_hash"] != row["proposal_hash"]:
            fail(409, "변경안 승인이 필요합니다.")
        fresh(conn, row, user)
        message(conn, row["message_id"], user)
        if (
            analysis.proposal_hash(row["spec_hash"], row["quote"], row["proposal"], row["analysis"])
            != row["approved_hash"]
        ):
            fail(422, "승인한 변경안 해시가 다릅니다.")
        proposed = SpecBundle.model_validate(row["proposal"])
        spec = specifications.edit(
            row["spec_id"],
            specifications.Edit(
                expected_version=row["spec_version"], spec_hash=row["spec_hash"], bundle=proposed
            ),
            user,
            conn,
            settings,
            checked,
        )
        expectation = Expected(
            expected_version=spec.bundle.spec_version, spec_hash=spec.readiness.spec_hash
        )
        # The human decision explicitly approves this exact executable specification.
        specifications.approve(row["spec_id"], expectation, user, conn, settings, checked)
        source = implementations.create(row["spec_id"], expectation, user, conn, settings, checked)
        job = implementations.request_verification(
            UUID(str(source["id"])),
            implementations.VerificationRequest(
                **expectation.model_dump(), source_hash=source["source_hash"], request_key=change_id
            ),
            user,
            conn,
            settings,
            checked,
        )
        conn.execute(
            "UPDATE feedback_change SET state='validating',implementation_id=%s,"
            "verification_id=%s,version=version+1 WHERE id=%s",
            (source["id"], job["id"], change_id),
        )
        event(conn, row, user, "implemented", "승인 변경안에서 새 명세·소스·검증 작업 생성")
    return get(change_id, user, conn)


@router.delete("/feedback/{message_id}", operation_id="eraseFeedbackMessage")
def erase(message_id: UUID, user: UserDep, conn: ConnDep, checked: Mutation) -> dict[str, str]:
    with conn.transaction():
        conn.execute("SELECT id FROM app_user WHERE id=%s FOR UPDATE", (user["id"],))
        message(conn, message_id, user)
        # The tombstone prevents future reconciliation from importing erased content again.
        rows = conn.execute(
            "SELECT project_id FROM feedback_change WHERE message_id=%s ORDER BY project_id",
            (message_id,),
        ).fetchall()
        for row in rows:
            own(conn, row["project_id"], user)
        conn.execute(
            "UPDATE feedback_job SET state='cancelled',lease_token=NULL,result=NULL "
            "WHERE change_id IN (SELECT id FROM feedback_change WHERE message_id=%s)",
            (message_id,),
        )
        conn.execute(
            "UPDATE feedback_revision SET payload='{}'::jsonb,payload_hash=%s "
            "WHERE change_id IN (SELECT id FROM feedback_change WHERE message_id=%s)",
            (digest({}), message_id),
        )
        conn.execute(
            "UPDATE feedback_event SET note='원문 삭제 요청으로 내용 삭제' "
            "WHERE change_id IN (SELECT id FROM feedback_change WHERE message_id=%s)",
            (message_id,),
        )
        conn.execute(
            "UPDATE feedback_change SET title='삭제된 메일 요청',quote='',instruction='',"
            "analysis=NULL,proposal=NULL,approved_hash=NULL,version=version+1,"
            "state=CASE WHEN implementation_id IS NULL THEN 'rejected' ELSE state END "
            "WHERE message_id=%s",
            (message_id,),
        )
        conn.execute(
            "UPDATE feedback_message SET subject='',sender='',body='',attachments='[]'::jsonb,"
            "deleted_at=now() WHERE id=%s",
            (message_id,),
        )
    return {"status": "erased", "retained": "이미 생성·승인한 명세와 구현 소스의 별도 보존 이력"}


@router.patch("/changes/{change_id}/clarification", operation_id="clarifyFeedbackChange")
def clarify(
    change_id: UUID, payload: Clarification, user: UserDep, conn: ConnDep, checked: Mutation
) -> dict[str, Any]:
    with conn.transaction():
        row = change(conn, change_id, user)
        expected(row, payload)
        if row["state"] not in ("received", "needs_input", "failed", "awaiting_decision"):
            fail(409, "분석 중이거나 승인된 변경 요청은 수정할 수 없습니다.")
        fresh(conn, row, user)
        message(conn, row["message_id"], user)
        conn.execute(
            "UPDATE feedback_change SET instruction=%s,state='received',version=version+1,"
            "analysis=NULL,proposal=NULL,proposal_hash=NULL,approved_hash=NULL WHERE id=%s",
            (payload.instruction, change_id),
        )
        event(conn, row, user, "clarified", "질문 답변과 추가 지시를 저장; 재분석 필요")
    return get(change_id, user, conn)


@router.get("/changes/{change_id}/reviews", operation_id="listFeedbackReviews")
def reviews(change_id: UUID, user: UserDep, conn: ConnDep) -> list[dict[str, Any]]:
    with conn.transaction():
        change(conn, change_id, user)
        rows = conn.execute(
            "SELECT version,payload,payload_hash,created_at FROM feedback_revision "
            "WHERE change_id=%s ORDER BY version DESC LIMIT 50",
            (change_id,),
        ).fetchall()
        if any(digest(row["payload"]) != row["payload_hash"] for row in rows):
            fail(422, "검토 버전 해시가 일치하지 않습니다.")
        return rows
