"""SDD 실행 명세 v0.1. 파일 해시는 출처 참조이며 실제 승인을 증명하지 않는다.

이 계약의 통과는 명세 검토 준비 상태만 뜻한다. DB 승인 조회와 생성/실행 권한은
별도 application 계층에서 확인해야 한다. 기존 DesignState와 model_hash는 바꾸지 않는다.
"""

import re
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator

from specton.contracts.acceptance import ApiScenario, ErrorResponse
from specton.contracts.base import Contract, NonEmptyText
from specton.contracts.commerce import CommercePolicy
from specton.contracts.domain import DomainPlan

Key = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{1,15}-[A-Za-z0-9_-]{1,64}$")]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
PositiveVersion = Annotated[int, Field(strict=True, ge=1)]
ScalarType = Literal["string", "integer", "decimal", "boolean", "date", "datetime", "uuid"]


class ArtifactDigest(Contract):
    kind: Literal["functions", "erd", "ddl", "rtm"]
    file_format: Literal["md", "mmd", "sql", "csv", "xlsx"]
    sha256: Sha256

    @model_validator(mode="after")
    def _format(self) -> Self:
        allowed = {"functions": {"md"}, "erd": {"mmd"}, "ddl": {"sql"}, "rtm": {"csv", "xlsx"}}
        if self.file_format not in allowed[self.kind]:
            raise ValueError("산출물 종류와 기계가 읽을 파일 형식이 다릅니다")
        return self


class BaselineReference(Contract):
    project_id: UUID
    baseline_id: UUID
    source_run_id: UUID
    source_revision: Annotated[int, Field(strict=True, ge=0)]
    model_hash: Sha256
    manifest_hash: Sha256
    approval_id: UUID
    artifacts: tuple[ArtifactDigest, ...] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def _four_artifacts(self) -> Self:
        if {a.kind for a in self.artifacts} != {"functions", "erd", "ddl", "rtm"}:
            raise ValueError("기능 명세·ERD·DDL·RTM이 각각 하나씩 필요합니다")
        return self


class SpecRequirement(Contract):
    id: Key
    text: NonEmptyText
    kind: Literal["FR", "NFR"]
    priority: Literal["Must", "Should", "Could", "Won't"]
    origin: Literal["design", "user"]
    legacy_id: str | None = None
    rationale: NonEmptyText
    requires_ui: bool

    @model_validator(mode="after")
    def _provenance(self) -> Self:
        if self.origin == "design" and not self.legacy_id:
            raise ValueError("설계에서 가져온 요구에는 원래 요구 ID가 필요합니다")
        if self.origin == "user" and self.legacy_id is not None:
            raise ValueError("추가한 요구를 원래 설계 요구로 표시할 수 없습니다")
        return self


class ActorRole(Contract):
    id: Key
    name: NonEmptyText


class SpecField(Contract):
    id: Key
    name: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,62}$")]
    data_type: ScalarType
    required: bool


class SpecEntity(Contract):
    id: Key
    legacy_id: NonEmptyText
    name: NonEmptyText
    fields: tuple[SpecField, ...] = Field(min_length=1)


class FieldRef(Contract):
    kind: Literal["field"] = "field"
    entity_id: Key
    field_id: Key


class NumberLiteral(Contract):
    kind: Literal["number"] = "number"
    # Decimal을 부동소수로 바꾸지 않는다. 컴파일 단계에서 Decimal(value)로 읽는다.
    value: Annotated[
        str, StringConstraints(pattern=r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$", max_length=64)
    ]


class TextLiteral(Contract):
    kind: Literal["text"] = "text"
    value: Annotated[str, StringConstraints(strip_whitespace=False)]


class BooleanLiteral(Contract):
    kind: Literal["boolean"] = "boolean"
    value: Annotated[bool, Field(strict=True)]


ValueExpression = Annotated[
    FieldRef | NumberLiteral | TextLiteral | BooleanLiteral, Field(discriminator="kind")
]


class Comparison(Contract):
    operator: Literal["eq", "ne", "lt", "le", "gt", "ge"]
    left: ValueExpression
    right: ValueExpression


class Invariant(Contract):
    id: Key
    req_ids: tuple[Key, ...] = Field(min_length=1)
    description: NonEmptyText
    match: Literal["all", "any"]
    comparisons: tuple[Comparison, ...] = Field(min_length=1, max_length=32)
    layers: tuple[Literal["database", "api"], ...] = Field(min_length=1)


class UseCase(Contract):
    id: Key
    name: NonEmptyText
    req_ids: tuple[Key, ...] = Field(min_length=1)
    actor_roles: tuple[Key, ...] = Field(min_length=1)
    preconditions: tuple[NonEmptyText, ...]
    inputs: tuple[SpecField, ...]
    steps: tuple[NonEmptyText, ...] = Field(min_length=1)
    outputs: tuple[SpecField, ...]
    error_codes: tuple[NonEmptyText, ...]
    transaction: Literal["read_only", "atomic"]
    idempotency: Literal["not_applicable", "key"]


class ApiOperation(Contract):
    id: Key
    use_case_id: Key
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: Annotated[str, StringConstraints(pattern=r"^/[a-zA-Z0-9_/{}/-]*$")]
    actor_roles: tuple[Key, ...] = Field(min_length=1)
    request_fields: tuple[SpecField, ...]
    response_fields: tuple[SpecField, ...] = Field(min_length=1)
    success_status: Annotated[int, Field(strict=True, ge=200, le=299)]
    error_codes: tuple[NonEmptyText, ...]
    pagination: Literal["none", "cursor"]
    concurrency: Literal["read_only", "row_lock", "optimistic"]


class Screen(Contract):
    id: Key
    route: Annotated[str, StringConstraints(pattern=r"^/[a-zA-Z0-9_/{}/-]*$")]
    name: NonEmptyText
    actor_roles: tuple[Key, ...] = Field(min_length=1)
    api_ids: tuple[Key, ...] = Field(min_length=1)
    empty_state: NonEmptyText
    loading_state: NonEmptyText
    error_state: NonEmptyText


class AcceptanceCase(Contract):
    id: Key
    req_ids: tuple[Key, ...] = Field(min_length=1)
    use_case_ids: tuple[Key, ...]
    tier: Literal["unit", "database", "api", "browser", "policy"]
    given: tuple[NonEmptyText, ...] = Field(min_length=1)
    when: NonEmptyText
    then: tuple[NonEmptyText, ...] = Field(min_length=1)
    fixture_ids: tuple[NonEmptyText, ...] = Field(min_length=1)
    execution: ApiScenario | None = None


class OpenQuestion(Contract):
    id: Key
    req_ids: tuple[Key, ...] = Field(min_length=1)
    question: NonEmptyText
    answer: NonEmptyText | None = None


def _unique(values: tuple[str, ...], label: str) -> set[str]:
    if len(set(values)) != len(values):
        raise ValueError(f"중복 ID/연결: {label}")
    return set(values)


def _refs(values: tuple[str, ...], allowed: set[str], label: str) -> None:
    unknown = _unique(values, label) - allowed
    if unknown:
        raise ValueError(f"없는 참조 {label}: {', '.join(sorted(unknown))}")


class StorageBinding(Contract):
    entity_id: Key
    table_id: NonEmptyText
    columns: dict[Key, NonEmptyText]


class OperationBinding(Contract):
    api_id: Key
    entity_id: Key
    action: Literal["insert", "get", "list", "update"]
    key_field_id: Key
    key_format: Literal["url-safe-segment"]


class InventoryPolicy(Contract):
    profile: Literal["stock-ledger-v1"]
    storage: Literal["generated-ledger-v1"]
    warehouse_entity_id: Key
    item_entity_id: Key
    quantity_scale: Literal[3]
    negative_stock: Literal[False]
    cancel_received: Literal["require_available_stock"]
    api_ids: dict[Literal["draft", "edit", "confirm", "cancel", "movement", "balance"], Key]

    @model_validator(mode="after")
    def _complete(self) -> Self:
        if set(self.api_ids) != {"draft", "edit", "confirm", "cancel", "movement", "balance"}:
            raise ValueError("재고 명령과 조회 6개의 연결이 필요합니다")
        _unique(tuple(self.api_ids.values()), "재고 API 연결")
        if self.warehouse_entity_id == self.item_entity_id:
            raise ValueError("창고와 품목은 서로 다른 엔티티여야 합니다")
        return self


class SpecBundle(Contract):
    schema_version: Literal[
        "spec-v0.1",
        "spec-v0.2",
        "spec-v0.3",
        "spec-v0.4",
        "spec-v0.5",
        "spec-v0.6",
        "spec-v0.7",
        "spec-v0.8",
        "spec-v0.9",
    ] = "spec-v0.1"
    domain: DomainPlan | None = None
    commerce: CommercePolicy | None = None
    inventory: InventoryPolicy | None = None
    storage_bindings: tuple[StorageBinding, ...] = ()
    operation_bindings: tuple[OperationBinding, ...] = ()
    spec_id: UUID
    spec_version: PositiveVersion
    parent_spec_hash: Sha256 | None = None
    baseline: BaselineReference
    template: Literal["inventory-fastapi-react-v1", "domain-fastapi-react-v1"]
    requirements: tuple[SpecRequirement, ...] = Field(min_length=1)
    roles: tuple[ActorRole, ...] = Field(min_length=1)
    entities: tuple[SpecEntity, ...]
    use_cases: tuple[UseCase, ...]
    invariants: tuple[Invariant, ...]
    apis: tuple[ApiOperation, ...]
    screens: tuple[Screen, ...]
    acceptance_cases: tuple[AcceptanceCase, ...]
    questions: tuple[OpenQuestion, ...]

    @model_validator(mode="after")
    def _references(self) -> Self:
        if self.domain is not None:
            if (
                self.schema_version not in {"spec-v0.6", "spec-v0.7", "spec-v0.8", "spec-v0.9"}
                or self.commerce
                or self.inventory
                or self.operation_bindings
            ):
                raise ValueError("도메인 실행 계약은 spec-v0.6/0.7/0.8에서 독립적으로 승인합니다")
            if self.domain.version != {
                "spec-v0.8": "domain-ir-v2",
                "spec-v0.9": "domain-ir-v3",
            }.get(self.schema_version, "domain-ir-v1"):
                raise ValueError("다중 레코드 명령은 spec-v0.8 / domain-ir-v2에서 별도 승인합니다")
            if self.domain.commands and self.domain.version not in {"domain-ir-v2", "domain-ir-v3"}:
                raise ValueError("명령에는 domain-ir-v2가 필요합니다")
            if self.schema_version != "spec-v0.9" and (
                self.domain.calculations
                or any(c.calculations or c.column_units for c in self.domain.commands)
            ):
                raise ValueError("계산·집계 계약은 spec-v0.9 / domain-ir-v3에서 승인합니다")
            _refs(
                (
                    tuple(o.api_id for o in self.domain.operations)
                    + tuple(c.api_id for c in self.domain.commands)
                    + tuple(c.api_id for c in self.domain.calculations)
                ),
                {a.id for a in self.apis},
                "도메인 API",
            )
            _refs(
                tuple(c.requirement_id for c in self.domain.coverage),
                {r.id for r in self.requirements},
                "요구 커버리지",
            )
            if {c.requirement_id for c in self.domain.coverage} != {
                r.id for r in self.requirements
            }:
                raise ValueError("모든 요구의 구현 상태를 명시해야 합니다")
            for coverage in self.domain.coverage:
                _refs(tuple(coverage.api_ids), {a.id for a in self.apis}, "구현 연결")
        elif self.schema_version in {"spec-v0.6", "spec-v0.7", "spec-v0.8", "spec-v0.9"}:
            raise ValueError("도메인 실행 계약이 필요합니다")
        if self.commerce is not None:
            if (
                self.schema_version != "spec-v0.5"
                or self.inventory is not None
                or self.operation_bindings
            ):
                raise ValueError("업무 데모는 spec-v0.5에서 별도 승인해야 합니다")
            _refs(tuple(self.commerce.api_ids.values()), {a.id for a in self.apis}, "업무 API")
        elif self.schema_version == "spec-v0.5":
            raise ValueError("spec-v0.5에는 업무 데모 정책이 필요합니다")
        if self.schema_version == "spec-v0.1" and (
            self.storage_bindings or self.operation_bindings
        ):
            raise ValueError("실행 연결은 spec-v0.2에서 명시적으로 승인해야 합니다")
        if (self.schema_version == "spec-v0.3" and self.inventory is None) or (
            self.inventory is not None and self.schema_version not in {"spec-v0.3", "spec-v0.4"}
        ):
            raise ValueError("재고 정책은 spec-v0.3에서 별도 승인해야 합니다")
        if self.inventory:
            _refs(tuple(self.inventory.api_ids.values()), {a.id for a in self.apis}, "재고 API")
            _refs(
                (self.inventory.warehouse_entity_id, self.inventory.item_entity_id),
                {e.id for e in self.entities},
                "창고·품목",
            )
            if set(self.inventory.api_ids.values()) & {o.api_id for o in self.operation_bindings}:
                raise ValueError("API를 기준정보와 재고 명령에 중복 연결할 수 없습니다")
        if self.schema_version != "spec-v0.4" and any(
            o.action in {"list", "update"} for o in self.operation_bindings
        ):
            raise ValueError("목록·수정 동작은 spec-v0.4에서 별도 승인해야 합니다")
        entities = {e.id: e for e in self.entities}
        _unique(tuple(b.entity_id for b in self.storage_bindings), "저장 연결")
        _unique(tuple(b.api_id for b in self.operation_bindings), "동작 연결")
        for binding in self.storage_bindings:
            _refs((binding.entity_id,), set(entities), "저장 엔티티")
            if set(binding.columns) != {f.id for f in entities[binding.entity_id].fields}:
                raise ValueError("모든 엔티티 필드의 원본 컬럼 연결이 필요합니다")
            _unique(tuple(binding.columns.values()), "원본 컬럼")
        for operation in self.operation_bindings:
            _refs((operation.api_id,), {a.id for a in self.apis}, "실행 API")
            _refs((operation.entity_id,), set(entities), "실행 엔티티")
            _refs(
                (operation.key_field_id,),
                {f.id for f in entities[operation.entity_id].fields},
                "조회 키",
            )
        if (self.spec_version == 1) != (self.parent_spec_hash is None):
            raise ValueError("첫 명세만 부모 해시가 없고 후속 버전에는 부모 해시가 필요합니다")
        groups = (
            self.requirements,
            self.roles,
            self.entities,
            self.use_cases,
            self.invariants,
            self.apis,
            self.screens,
            self.acceptance_cases,
            self.questions,
        )
        _unique(tuple(obj.id for group in groups for obj in group), "명세 객체")
        reqs = {r.id for r in self.requirements}
        roles = {r.id for r in self.roles}
        cases = {u.id: u for u in self.use_cases}
        apis = {a.id: a for a in self.apis}
        fields: dict[tuple[str, str], str] = {}
        for entity in self.entities:
            _unique(tuple(f.id for f in entity.fields), entity.id)
            _unique(tuple(f.name for f in entity.fields), entity.id)
            fields.update({(entity.id, f.id): f.data_type for f in entity.fields})
        for group in (self.use_cases, self.invariants, self.acceptance_cases, self.questions):
            for item in group:
                _refs(item.req_ids, reqs, item.id)
        for use_case in self.use_cases:
            _refs(use_case.actor_roles, roles, use_case.id)
            for field_group in (use_case.inputs, use_case.outputs):
                _unique(tuple(f.id for f in field_group), use_case.id)
                _unique(tuple(f.name for f in field_group), use_case.id)
        calculation_ids = {q.api_id for q in self.domain.calculations} if self.domain else set()
        for api in self.apis:
            _refs((api.use_case_id,), set(cases), api.id)
            _refs(api.actor_roles, roles, api.id)
            case = cases[api.use_case_id]
            if set(api.actor_roles) != set(case.actor_roles):
                raise ValueError(f"API와 유스케이스 권한이 다릅니다: {api.id}")
            if api.request_fields != case.inputs or api.response_fields != case.outputs:
                raise ValueError(f"API와 유스케이스 입출력이 다릅니다: {api.id}")
            if set(api.error_codes) != set(case.error_codes):
                raise ValueError(f"API와 유스케이스 오류 계약이 다릅니다: {api.id}")
            if api.method == "GET" and (
                case.transaction != "read_only" or api.concurrency != "read_only"
            ):
                raise ValueError(f"GET은 읽기 전용이어야 합니다: {api.id}")
            if api.id in calculation_ids and (
                api.method != "POST"
                or case.transaction != "read_only"
                or api.concurrency != "read_only"
                or case.idempotency != "not_applicable"
            ):
                raise ValueError("계산 API는 본문을 받는 읽기 전용 POST여야 합니다")
            if (
                api.method != "GET"
                and api.id not in calculation_ids
                and (case.transaction != "atomic" or api.concurrency == "read_only")
            ):
                raise ValueError(f"변경 API에는 원자성과 동시성 정책이 필요합니다: {api.id}")
        routes = tuple(f"{a.method} {re.sub(r'\{[^{}]+\}', '{}', a.path)}" for a in self.apis)
        _unique(routes, "API 경로")
        _unique(tuple(re.sub(r"\{[^{}]+\}", "{}", s.route) for s in self.screens), "화면 경로")
        for screen in self.screens:
            _refs(screen.actor_roles, roles, screen.id)
            _refs(screen.api_ids, set(apis), screen.id)
            for api_id in screen.api_ids:
                if not set(screen.actor_roles) <= set(apis[api_id].actor_roles):
                    raise ValueError(f"화면 역할이 연결 API를 사용할 수 없습니다: {screen.id}")
        for test in self.acceptance_cases:
            _refs(test.use_case_ids, set(cases), test.id)
            linked = {r for key in test.use_case_ids for r in cases[key].req_ids}
            if test.use_case_ids and not set(test.req_ids) <= linked:
                raise ValueError(f"테스트 요구와 유스케이스의 추적이 다릅니다: {test.id}")
            if test.execution:
                if (
                    self.schema_version not in {"spec-v0.7", "spec-v0.8", "spec-v0.9"}
                    or test.tier != "api"
                ):
                    raise ValueError(
                        "실행 인수 계약은 spec-v0.7/0.8의 API 사례에서 승인해야 합니다"
                    )
                for step in test.execution.steps:
                    if (
                        step.api_id not in apis
                        or apis[step.api_id].use_case_id not in test.use_case_ids
                    ):
                        raise ValueError(f"실행 인수 API와 유스케이스 연결이 다릅니다: {test.id}")
                    api = apis[step.api_id]
                    if api.id in calculation_ids:
                        if step.body is None or step.request_key is not None:
                            raise ValueError(
                                "계산 테스트에는 본문이 필요하고 변경 요청 키는 쓰지 않습니다"
                            )
                    elif api.method == "GET":
                        if step.body is not None or step.request_key is not None:
                            raise ValueError("조회 테스트에는 본문·요청 키를 지정할 수 없습니다")
                    elif api.method != "POST" or step.body is None or step.request_key is None:
                        raise ValueError("변경 테스트에는 POST 본문·요청 키가 필요합니다")
                    if isinstance(step.expect, ErrorResponse):
                        standard = {
                            401: {"AUTH_REQUIRED"},
                            403: {"FORBIDDEN"},
                            404: {"NOT_FOUND"},
                            409: {
                                "DUPLICATE_KEY",
                                "REFERENCE_NOT_FOUND",
                                "RULE_VIOLATION",
                                "INVALID_STATE",
                                "IDEMPOTENCY_CONFLICT",
                                "CONCURRENT_MODIFICATION",
                                "COMMAND_TIMEOUT",
                                "TRANSACTION_FAILED",
                                "CALCULATION_ERROR",
                                "RESULT_LIMIT_EXCEEDED",
                            },
                            422: {"VALIDATION_ERROR", "CONSTRAINT_VIOLATION"},
                        }
                        if step.expect.code not in standard[step.expect.status]:
                            raise ValueError("지원하지 않는 인수 오류 상태·코드 조합입니다")
        executions = [t.execution for t in self.acceptance_cases if t.execution]
        if len(executions) > 32 or sum(len(e.steps) for e in executions) > 128:
            raise ValueError("실행 인수는 명세당 32개 사례·128개 단계까지 지원합니다")
        if sum(len(e.model_dump_json()) for e in executions) > 500000:
            raise ValueError("실행 인수 입력·기대값이 500,000자 한도를 초과했습니다")
        for invariant in self.invariants:
            for comparison in invariant.comparisons:
                types = []
                for value in (comparison.left, comparison.right):
                    if isinstance(value, FieldRef):
                        field_type = fields.get((value.entity_id, value.field_id))
                        if field_type is None:
                            raise ValueError(f"없는 규칙 필드: {invariant.id}")
                        types.append(
                            "number" if field_type in {"integer", "decimal"} else field_type
                        )
                    else:
                        types.append("string" if value.kind == "text" else value.kind)
                if types[0] != types[1]:
                    raise ValueError(f"규칙 비교 타입이 다릅니다: {invariant.id}")
                if comparison.operator not in {"eq", "ne"} and types[0] not in {
                    "number",
                    "date",
                    "datetime",
                }:
                    raise ValueError(f"이 타입은 순서 비교를 지원하지 않습니다: {invariant.id}")
        return self
