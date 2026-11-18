"""Structural executable draft derived from approved tables, not domain-name templates."""

from hashlib import sha256

from specton.contracts import DesignState
from specton.contracts.specification import SpecBundle

TYPES = {
    "varchar": "string",
    "char": "string",
    "text": "string",
    "integer": "integer",
    "bigint": "integer",
    "smallint": "integer",
    "numeric": "decimal",
    "boolean": "boolean",
    "date": "date",
    "timestamp": "datetime",
    "timestamptz": "datetime",
    "uuid": "uuid",
}


def identifier(prefix: str, source: str) -> str:
    return prefix + "-" + sha256(source.encode()).hexdigest()[:24]


def derive(current: SpecBundle, state: DesignState) -> SpecBundle:
    if current.domain and (current.domain.commands or current.domain.calculations):
        raise ValueError(
            "명령·계산 계약이 있는 명세는 구조 재연결로 덮어쓸 수 없습니다. "
            "기존 실행 계약을 보완하세요."
        )
    if not state.normalized or not state.normalized.tables:
        raise ValueError("승인된 테이블과 관계가 필요합니다.")
    data = current.model_dump(mode="json")
    data.update(
        schema_version="spec-v0.6",
        commerce=None,
        inventory=None,
        entities=[],
        storage_bindings=[],
        operation_bindings=[],
        use_cases=[],
        apis=[],
        screens=[],
        acceptance_cases=[],
        invariants=[],
    )
    roles = [r["id"] for r in data["roles"]]
    source_reqs = {r["legacy_id"]: r["id"] for r in data["requirements"] if r["origin"] == "design"}
    ops = []
    for table in state.normalized.tables:
        if not table.primary_key or any(c.data_type.value not in TYPES for c in table.columns):
            raise ValueError(f"{table.name}: 지원하지 않는 키/자료형을 보완해야 합니다.")
        eid = identifier("ENTITY", table.id)
        fields = [
            dict(
                id=identifier("FIELD", c.id),
                name=c.physical_name,
                data_type=TYPES[c.data_type.value],
                required=not c.nullable,
            )
            for c in table.columns
        ]
        data["entities"].append(
            dict(id=eid, legacy_id=table.entity_id or table.id, name=table.name, fields=fields)
        )
        data["storage_bindings"].append(
            dict(
                entity_id=eid,
                table_id=table.id,
                columns={f["id"]: c.id for f, c in zip(fields, table.columns, strict=True)},
            )
        )
        refs = [source_reqs[r] for r in table.req_ids if r in source_reqs]
        if not refs:
            raise ValueError(f"{table.name}: 원본 요구 연결이 없습니다.")
        aids = []
        for action, label in [("insert", "등록"), ("list", "조회"), ("update", "수정")]:
            crud = {"insert": "C", "list": "R", "update": "U"}[action]
            # A requirement can belong to a function without being repeated on its table.
            # Preserve that declared CRUD trace, without claiming business coverage is complete.
            action_refs = list(
                dict.fromkeys(
                    [
                        *refs,
                        *(
                            source_reqs[r]
                            for function in state.functions
                            if any(
                                o.entity_id == table.entity_id and crud in o.operations
                                for o in function.entity_ops
                            )
                            for r in function.req_ids
                            if r in source_reqs
                        ),
                    ]
                )
            )
            aid = identifier("API", table.id + action)
            uid = identifier("UC", table.id + action)
            aids.append(aid)
            write = action != "list"
            inputs = fields if write else []
            errors = (
                [
                    "DUPLICATE_KEY",
                    "REFERENCE_NOT_FOUND",
                    "CONSTRAINT_VIOLATION",
                    "RULE_VIOLATION",
                    "NOT_FOUND",
                    "IDEMPOTENCY_CONFLICT",
                ]
                if write
                else []
            )
            data["use_cases"].append(
                dict(
                    id=uid,
                    name=table.name + " " + label,
                    req_ids=action_refs,
                    actor_roles=roles,
                    preconditions=["검토한 역할과 실행 계약"],
                    inputs=inputs,
                    steps=[table.name + " 데이터 " + label + " (업무 규칙 구현과 별도 검토)"],
                    outputs=fields,
                    error_codes=errors,
                    transaction="atomic" if write else "read_only",
                    idempotency="key" if write else "not_applicable",
                )
            )
            data["apis"].append(
                dict(
                    id=aid,
                    use_case_id=uid,
                    method="POST" if write else "GET",
                    path="/data/" + identifier("resource", table.id).lower() + "/" + action,
                    actor_roles=roles,
                    request_fields=inputs,
                    response_fields=fields,
                    success_status=200,
                    error_codes=errors,
                    pagination="none",
                    concurrency="row_lock" if write else "read_only",
                )
            )
            ops.append(dict(api_id=aid, table_id=table.id, action=action))
            data["acceptance_cases"].append(
                dict(
                    id=identifier("TC", aid),
                    req_ids=action_refs,
                    use_case_ids=[uid],
                    tier="browser",
                    given=["격리 DB의 원본 승인 구조"],
                    when=table.name + " " + label,
                    then=["입력·키·관계 계약을 만족한다"],
                    fixture_ids=["schema-derived"],
                )
            )
        data["screens"].append(
            dict(
                id=identifier("SCREEN", table.id),
                route="/data/" + identifier("resource", table.id).lower(),
                name=table.name,
                actor_roles=roles,
                api_ids=aids,
                empty_state="등록된 자료가 없습니다.",
                loading_state="처리 중",
                error_state="요청을 처리하지 못했습니다.",
            )
        )
    data["domain"] = dict(
        operations=ops,
        coverage=[
            dict(
                requirement_id=r["id"],
                status="needs_review",
                api_ids=sorted(
                    {
                        a["id"]
                        for a in data["apis"]
                        if r["id"]
                        in next(
                            u["req_ids"] for u in data["use_cases"] if u["id"] == a["use_case_id"]
                        )
                    }
                ),
                explanation=(
                    "저장 구조를 연결했습니다. "
                    "원본 기능·업무 규칙과 실행 동작의 일치를 검토해야 합니다."
                ),
            )
            for r in data["requirements"]
        ],
    )
    return SpecBundle.model_validate(data)
