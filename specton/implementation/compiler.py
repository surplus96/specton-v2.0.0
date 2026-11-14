"""자유 설명을 실행하지 않는 제한된 명세 컴파일러."""

import re
from typing import Any

from pydantic import BaseModel

from specton.contracts import DesignState
from specton.contracts.specification import SpecBundle
from specton.specification.readiness import assess_readiness


class Unsupported(ValueError):
    """추측해서 구현할 수 없는 명세."""


def compile_contract(bundle: SpecBundle, state: DesignState) -> dict[str, Any]:
    if (
        bundle.schema_version not in {"spec-v0.2", "spec-v0.3"}
        or not assess_readiness(bundle).ready_for_review
    ):
        raise Unsupported("검토 가능한 spec-v0.2/v0.3 실행 연결이 필요합니다.")
    if state.normalized is None or bundle.invariants:
        raise Unsupported("정규화 모델이 필요하며 사용자 불변식 컴파일은 아직 지원하지 않습니다.")
    if not bundle.apis or len(bundle.apis) > 40 or len(bundle.entities) > 20:
        raise Unsupported("1~40개 API, 최대 20개 엔티티만 지원합니다.")
    inventory_ids = set(bundle.inventory.api_ids.values()) if bundle.inventory else set()
    if {o.api_id for o in bundle.operation_bindings} | inventory_ids != {a.id for a in bundle.apis}:
        raise Unsupported("모든 API에 명시적인 insert/get 동작을 연결하세요.")
    if any(t.physical_name.startswith("_specton_") for t in state.normalized.tables):
        raise Unsupported("승인 DDL에서 생성기 예약 테이블 이름을 사용할 수 없습니다.")
    tables = {t.id: t for t in state.normalized.tables}
    entities = {e.id: e for e in bundle.entities}
    stores = {b.entity_id: b for b in bundle.storage_bindings}
    if set(stores) != set(entities):
        raise Unsupported("모든 엔티티의 승인 DDL 연결이 필요합니다.")
    if len({b.table_id for b in stores.values()}) != len(stores):
        raise Unsupported("하나의 테이블을 여러 엔티티로 중복 노출할 수 없습니다.")
    compiled: dict[str, Any] = {}
    types = {"varchar": "string", "integer": "integer", "boolean": "boolean"}
    for key, entity in entities.items():
        binding = stores[key]
        table = tables.get(binding.table_id)
        if table is None or table.entity_id != entity.legacy_id:
            raise Unsupported("엔티티의 원본 ID와 승인 테이블이 일치하지 않습니다.")
        if len(table.primary_key) != 1 or any(
            f.table_id == table.id for f in state.normalized.foreign_keys
        ):
            raise Unsupported("현재는 단일 기본키이며 외래키가 없는 기준정보 테이블만 지원합니다.")
        columns = {c.id: c for c in table.columns}
        if set(binding.columns.values()) != set(columns):
            raise Unsupported("승인 테이블의 모든 컬럼을 명세에 명시해야 합니다.")
        fields = []
        for field in entity.fields:
            if hasattr(BaseModel, field.name):
                raise Unsupported("DTO 예약 이름은 필드명으로 사용할 수 없습니다.")
            column = columns[binding.columns[field.id]]
            if types.get(column.data_type.value) != field.data_type or field.required != (
                not column.nullable
            ):
                raise Unsupported("필드 타입·필수 여부와 승인 컬럼이 다릅니다.")
            fields.append(
                {
                    **field.model_dump(),
                    "column": column.physical_name,
                    "length": column.length,
                    "primary": column.id == table.primary_key[0],
                }
            )
        if any(
            not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", n)
            for n in [table.physical_name, *(f["column"] for f in fields)]
        ):
            raise Unsupported("생성기에서 지원하지 않는 SQL 식별자입니다.")
        compiled[key] = {"table": table.physical_name, "fields": fields}
    if not bundle.screens or {a for s in bundle.screens for a in s.api_ids} != {
        a.id for a in bundle.apis
    }:
        raise Unsupported("모든 API가 실제 화면에 연결되어야 합니다.")
    if any("{" in s.route for s in bundle.screens):
        raise Unsupported("현재 화면은 정적 경로만 지원합니다.")
    apis = {a.id: a for a in bundle.apis}
    operations = []
    for operation_binding in bundle.operation_bindings:
        api = apis[operation_binding.api_id]
        entity = entities[operation_binding.entity_id]
        store = compiled[entity.id]
        primary = next(f for f in store["fields"] if f["primary"])
        if primary["id"] != operation_binding.key_field_id or primary["data_type"] not in {
            "string",
            "integer",
        }:
            raise Unsupported("조회 키는 승인 테이블의 문자열·정수 기본키여야 합니다.")
        if tuple(api.response_fields) != entity.fields or api.pagination != "none":
            raise Unsupported("현재 응답은 엔티티 전체 필드와 단건 응답만 지원합니다.")
        if operation_binding.action == "insert":
            valid = (
                api.method == "POST"
                and re.fullmatch(r"(?:/[A-Za-z0-9_-]+)+", api.path) is not None
                and api.success_status == 201
                and api.request_fields == entity.fields
                and api.concurrency == "optimistic"
                and set(api.error_codes) == {"DUPLICATE_KEY", "IDEMPOTENCY_CONFLICT"}
            )
        else:
            valid = (
                api.method == "GET"
                and re.fullmatch(r"(?:/[A-Za-z0-9_-]+)+/\{key\}", api.path) is not None
                and api.path.count("{") == 1
                and api.success_status == 200
                and api.concurrency == "read_only"
                and tuple(f.id for f in api.request_fields) == (primary["id"],)
                and set(api.error_codes) == {"NOT_FOUND"}
            )
        if not valid or api.path.startswith(("/health", "/docs", "/openapi", "/redoc")):
            raise Unsupported(
                "insert/get의 메서드·경로·입출력·오류·동시성 계약이 지원 범위와 다릅니다."
            )
        operations.append(
            {
                **api.model_dump(mode="json"),
                **operation_binding.model_dump(),
                **store,
                "key": primary,
            }
        )
    # 각 저장 동작은 실제 재조회가 가능해야 하며 프로브가 이를 독립 검증한다.
    for entity_id in entities:
        if sum(o["entity_id"] == entity_id for o in operations) != 2:
            raise Unsupported("각 엔티티에 등록·조회 API를 정확히 하나씩 연결하세요.")
        if {o["action"] for o in operations if o["entity_id"] == entity_id} != {"insert", "get"}:
            raise Unsupported("각 엔티티에 등록과 단건 조회를 함께 연결하세요.")
    from specton.implementation.inventory_contract import compile_inventory

    return {
        "inventory": compile_inventory(bundle, compiled),
        "operations": operations,
        "screens": [s.model_dump(mode="json") for s in bundle.screens],
    }
