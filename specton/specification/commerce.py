"""Deterministic, owner-reviewed business demonstration from a recognized approved design."""

from specton.contracts import DesignState
from specton.contracts.commerce import CommercePolicy
from specton.contracts.specification import SpecBundle
from specton.implementation.commerce_contract import COMMANDS, SCREEN_NAMES, resolve_sources

DEFAULTS = (
    "기본 시연: 실행 명세의 업무 정책에 따라 주문 접수 시 유통기한 순으로 낱개 환산 차감, "
    "부족 시 전체 거절, 마감 전 변경·취소와 재고 복구를 적용합니다. "
    "반품은 현재 등록 금액을 포함해 월 구매 대비 비율을 비교하며 자동 재입고하지 않습니다. "
    "마감 시각·알림 일수·경고 비율은 구조화된 업무 정책을 따릅니다. "
    "담당자 내부 알림이며 상용 회원점 인증·운영 성능·보존 정책은 후속 범위입니다."
)


def propose_business(current: SpecBundle, state: DesignState) -> SpecBundle:
    tables = resolve_sources(state)
    data = current.model_dump(mode="json")
    source_req = {r.legacy_id: r.id for r in current.requirements if r.origin == "design"}
    supported = {i for command in COMMANDS.values() for i in command[3]}
    if not supported <= source_req.keys():
        raise ValueError("업무 프로필 요구 출처가 없습니다. 자동으로 요구를 추측하지 않습니다.")
    for r in data["requirements"]:
        included = r["origin"] == "design" and r["legacy_id"] in supported
        r.update(
            priority="Must" if included else "Won't",
            requires_ui=included,
            rationale="기본 시연 프로필의 API·화면으로 검증합니다."
            if included
            else "기본 업무 시연 범위 밖이며 원본 요구를 후속 구현 대상으로 보존합니다.",
        )
    for q in data["questions"]:
        if q["answer"] is None:
            q["answer"] = DEFAULTS
    data.update(
        schema_version="spec-v0.5",
        inventory=None,
        entities=[],
        storage_bindings=[],
        operation_bindings=[],
        roles=[{"id": "ROLE-operator", "name": "데모 담당자"}],
        use_cases=[],
        apis=[],
        screens=[],
        invariants=[],
        acceptance_cases=[],
    )
    data["commerce"] = CommercePolicy(
        source_tables=tables,
        api_ids={k: "API-commerce-" + k for k in COMMANDS},
        defaults_acknowledged=True,
    ).model_dump(mode="json")
    for action, (title, method, inputs, requirements, _screen) in COMMANDS.items():
        aid = "API-commerce-" + action
        uid = "UC-commerce-" + action
        fields = [
            {"id": "FIELD-" + name, "name": name, "data_type": kind, "required": True}
            for name, kind in inputs
        ]
        outputs = [
            {"id": "FIELD-result", "name": "result_json", "data_type": "string", "required": True}
        ]
        write = method != "GET"
        errors = (
            [
                "INVALID_STATE",
                "REFERENCE_NOT_FOUND",
                "INSUFFICIENT_STOCK",
                "CUTOFF_PASSED",
                "DUPLICATE_KEY",
                "IDEMPOTENCY_CONFLICT",
            ]
            if write
            else []
        )
        refs = [source_req[r] for r in requirements]
        data["use_cases"].append(
            dict(
                id=uid,
                name=title,
                req_ids=refs,
                actor_roles=["ROLE-operator"],
                preconditions=["승인된 데모 정책과 담당자 토큰"],
                inputs=fields,
                steps=[title, DEFAULTS],
                outputs=outputs,
                error_codes=errors,
                transaction="atomic" if write else "read_only",
                idempotency="key" if write else "not_applicable",
            )
        )
        data["apis"].append(
            dict(
                id=aid,
                use_case_id=uid,
                method=method,
                path="/commerce/" + action,
                actor_roles=["ROLE-operator"],
                request_fields=fields,
                response_fields=outputs,
                success_status=200,
                error_codes=errors,
                pagination="none",
                concurrency="row_lock" if write else "read_only",
            )
        )
        data["acceptance_cases"].append(
            dict(
                id="TC-commerce-" + action,
                req_ids=refs,
                use_case_ids=[uid],
                tier="browser",
                given=["격리 데모 DB와 담당자 토큰"],
                when=title,
                then=["API 결과와 저장 상태가 승인 정책에 부합한다"],
                fixture_ids=["wholesale-demo-v1"],
            )
        )
    for key, title in SCREEN_NAMES.items():
        data["screens"].append(
            dict(
                id="SCREEN-commerce-" + key,
                route="/commerce/" + key,
                name=title,
                actor_roles=["ROLE-operator"],
                api_ids=["API-commerce-" + k for k, v in COMMANDS.items() if v[4] == key],
                empty_state="자료 없음",
                loading_state="처리 중",
                error_state="요청 실패",
            )
        )
    return SpecBundle.model_validate(data)
