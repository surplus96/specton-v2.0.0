"""Fixed business commands, linked to recognized source tables without arbitrary SQL/code."""

from typing import Any

from specton.contracts import DesignState
from specton.contracts.commerce import CommercePolicy
from specton.contracts.specification import SpecBundle

# Logical source names are deliberately explicit. Ambiguous/missing mappings are rejected.
SOURCE_TABLES = {
    "product": ("상품", {"품목코드", "품목명", "안전재고수량"}),
    "unit": ("상품단위", {"품목코드", "단위명", "낱개환산수량"}),
    "member": ("회원점", {"회원점번호", "사업자등록번호"}),
    "order": ("주문", {"주문번호", "거래일시"}),
    "line": ("주문상세", {"주문번호", "주문수량", "판매단가", "주문금액"}),
    "lot": ("입고재고", {"품목코드", "유통기한", "재고수량"}),
    "allocation": ("주문재고배정", {"배정수량", "차감수량"}),
    "return": ("반품", {"반품금액", "거래일시"}),
}
# action: title, method, typed input names, requirement IDs, screen
COMMANDS = {
    "product": (
        "상품 등록·수정",
        "POST",
        [
            ("id", "string"),
            ("name", "string"),
            ("specification", "string"),
            ("barcode", "string"),
            ("tax", "string"),
            ("safety_stock", "decimal"),
        ],
        ["REQ-01", "REQ-08"],
        "catalog",
    ),
    "unit": (
        "거래 단위 등록·수정",
        "POST",
        [
            ("product_id", "string"),
            ("name", "string"),
            ("factor", "decimal"),
            ("is_default", "boolean"),
        ],
        ["REQ-01", "REQ-02"],
        "catalog",
    ),
    "member": (
        "회원점 등록·수정",
        "POST",
        [
            ("id", "string"),
            ("name", "string"),
            ("representative", "string"),
            ("business_number", "string"),
            ("grade", "string"),
        ],
        ["REQ-04", "REQ-05"],
        "members",
    ),
    "receive": (
        "상품 입고",
        "POST",
        [("id", "string"), ("product_id", "string"), ("expires", "date"), ("quantity", "decimal")],
        ["REQ-10"],
        "stock",
    ),
    "place": (
        "주문 접수",
        "POST",
        [("id", "string"), ("member_id", "string"), ("lines_json", "string")],
        ["REQ-03", "REQ-06", "REQ-07", "REQ-12"],
        "orders",
    ),
    "revise": (
        "주문 수량 변경",
        "POST",
        [("id", "string"), ("lines_json", "string")],
        ["REQ-03", "REQ-06", "REQ-07", "REQ-12"],
        "orders",
    ),
    "cancel": ("주문 취소", "POST", [("id", "string")], ["REQ-06"], "orders"),
    "return": (
        "반품 등록",
        "POST",
        [("id", "string"), ("member_id", "string"), ("amount", "decimal")],
        ["REQ-13"],
        "returns",
    ),
    "catalog": ("상품·거래 단위 목록", "GET", [], ["REQ-01", "REQ-02", "REQ-08"], "catalog"),
    "members": ("회원점 목록", "GET", [], ["REQ-04"], "members"),
    "orders": ("주문·수량·금액 조회", "GET", [], ["REQ-07"], "orders"),
    "returns": ("반품·경고 조회", "GET", [], ["REQ-13"], "returns"),
    "stock": ("유통기한별 재고 조회", "GET", [], ["REQ-10"], "stock"),
    "alerts": ("안전재고·유통기한 알림", "GET", [], ["REQ-09", "REQ-11", "REQ-12"], "alerts"),
}
SCREEN_NAMES = {
    "catalog": "상품 기준정보 관리",
    "members": "회원점 관리",
    "stock": "입고·재고 관리",
    "orders": "주문 관리",
    "returns": "반품 관리",
    "alerts": "재고·유통기한 알림",
}


def commands(policy: CommercePolicy) -> dict[str, Any]:
    result = dict(COMMANDS)
    if policy.product_note_enabled:
        title, method, fields, reqs, screen = result["product"]
        result["product"] = (title, method, [*fields, ("note", "string")], reqs, screen)
    return result


def resolve_sources(state: DesignState) -> dict[str, str]:
    if state.normalized is None:
        raise ValueError("정규화 설계가 필요합니다.")
    result = {}
    for key, (name, columns) in SOURCE_TABLES.items():
        matches = [
            t
            for t in state.normalized.tables
            if t.name == name and columns <= {c.name for c in t.columns}
        ]
        if len(matches) != 1:
            raise ValueError(f"업무 프로필에 필요한 {name} 테이블을 명확하게 연결할 수 없습니다.")
        result[key] = matches[0].id
    return result


def compile_commerce(bundle: SpecBundle, state: DesignState) -> dict[str, Any]:
    from specton.implementation.compiler import Unsupported
    from specton.specification.readiness import assess_readiness

    policy = bundle.commerce
    if policy is None or not assess_readiness(bundle).ready_for_review:
        raise Unsupported("검토 가능한 업무 명세가 필요합니다.")
    if policy.source_tables != resolve_sources(state):
        raise Unsupported("업무 테이블 출처가 승인 설계와 다릅니다.")
    if set(policy.api_ids) != set(COMMANDS) or set(policy.api_ids.values()) != {
        a.id for a in bundle.apis
    }:
        raise Unsupported("업무 API 전체 연결이 필요합니다.")
    if bundle.entities or bundle.storage_bindings or bundle.invariants:
        raise Unsupported("이 프로필은 명시된 파생 업무 저장 구조만 사용합니다.")
    ops = []
    for action, (title, method, inputs, _reqs, _screen) in commands(policy).items():
        api = next(a for a in bundle.apis if a.id == policy.api_ids[action])
        write = method != "GET"
        if (
            api.method != method
            or api.path != "/commerce/" + action
            or api.success_status != 200
            or [(f.name, f.data_type) for f in api.request_fields] != inputs
            or any(not f.required for f in api.request_fields)
            or [(f.name, f.data_type) for f in api.response_fields] != [("result_json", "string")]
            or api.concurrency != ("row_lock" if write else "read_only")
            or set(api.error_codes)
            != (
                {
                    "INVALID_STATE",
                    "REFERENCE_NOT_FOUND",
                    "INSUFFICIENT_STOCK",
                    "CUTOFF_PASSED",
                    "DUPLICATE_KEY",
                    "IDEMPOTENCY_CONFLICT",
                }
                if write
                else set()
            )
        ):
            raise Unsupported("고정 업무 API 계약과 다릅니다.")
        ops.append(
            {
                "id": api.id,
                "action": action,
                "title": title,
                "path": api.path,
                "method": method,
                "actor_roles": list(api.actor_roles),
                "request_fields": [f.model_dump() for f in api.request_fields],
            }
        )
    if {i for s in bundle.screens for i in s.api_ids} != {a.id for a in bundle.apis}:
        raise Unsupported("모든 업무에 화면 연결이 필요합니다.")
    return {
        "operations": [],
        "inventory": None,
        "commerce": {**policy.model_dump(mode="json"), "operations": ops},
        "screens": [s.model_dump(mode="json") for s in bundle.screens],
    }
