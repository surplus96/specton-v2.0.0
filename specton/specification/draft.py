"""승인 스냅샷에서 출처를 보존한 초안. 업무 동작은 추측해서 확정하지 않는다."""

from uuid import UUID, uuid5

from specton.contracts import DesignState
from specton.contracts.specification import BaselineReference, SpecBundle


def source_id(project: UUID, run: UUID, kind: str, legacy: str) -> str:
    # run마다 REQ-01 등이 재사용되므로 서로 다른 run의 객체를 자동 병합하지 않는다.
    return f"{kind}-{uuid5(project, f'{run}:{kind}:{legacy}').hex}"


def draft(spec_id: UUID, baseline: BaselineReference, state: DesignState) -> SpecBundle:
    requirements = [
        {
            "id": source_id(baseline.project_id, baseline.source_run_id, "REQ", r.id),
            "legacy_id": r.id,
            "origin": "design",
            "text": r.text,
            "kind": r.type.value,
            "priority": "Must",
            "requires_ui": r.type.value == "FR",
            "rationale": (
                "초안은 누락 방지를 위해 Must로 둡니다. 범위·우선순위·화면 필요 여부를 확인하세요."
            ),
        }
        for r in state.requirements
    ]
    questions = [
        {
            "id": source_id(baseline.project_id, baseline.source_run_id, "QUESTION", r.id),
            "req_ids": [requirements[index]["id"]],
            "question": (
                "이 요구의 범위·우선순위·화면 필요 여부와 허용 역할, 입력·출력, 실패 조건, "
                "업무 규칙을 확인하고 유스케이스·API·화면·인수 사례 계약에 반영하세요."
            ),
        }
        for index, r in enumerate(state.requirements)
    ]
    return SpecBundle.model_validate(
        {
            "spec_id": spec_id,
            "spec_version": 1,
            "baseline": baseline,
            "template": "domain-fastapi-react-v1",
            "requirements": requirements,
            "roles": [{"id": "ROLE-unconfirmed", "name": "미확정 역할 (실제 업무 역할로 교체)"}],
            "entities": [],
            "use_cases": [],
            "invariants": [],
            "apis": [],
            "screens": [],
            "acceptance_cases": [],
            "questions": questions,
        }
    )
