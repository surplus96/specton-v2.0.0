"""Mail policy deltas and independent owner reviews, fixed before execution."""

import json
from copy import deepcopy

from specton.feedback.analysis import Analysis, Suggestion
from specton.feedback.contracts import AcceptanceReview

QUOTE = "계산 결과의 소수 두 자리 처리를 반올림 대신 절삭으로 변경해 주세요."


def suggestion(bundle, command=False):
    domain = bundle.model_dump(mode="json")["domain"]
    section, field = ("commands", "calculations") if command else ("calculations", "aggregates")
    target = domain[section][0]
    value = deepcopy(target[field])
    if command:
        value[0]["result"]["rounding"] = "down"
    else:
        next(a for a in value if a["id"] == "average")["result"]["rounding"] = "down"
    return Analysis(
        summary=QUOTE,
        quotes=[QUOTE],
        requests=[QUOTE],
        questions=[],
        unsupported=[],
        suggestions=[
            Suggestion(
                section="domain_" + section,
                object_id=target["api_id"],
                field=field,
                value_json=json.dumps(value),
                rationale=QUOTE,
            )
        ],
    )


def reviews(bundle, change_average=False):
    result = []
    for case in bundle.acceptance_cases:
        if not case.execution:
            continue
        replacements = []
        if change_average and case.id == "TC-summary-normal":
            expected = case.execution.steps[-1].expect.model_dump(mode="json")
            expected["body"]["average"] = "1.51"  # (1.01 + 2.02) / 2, truncate to two places
            replacements = [{"step_index": len(case.execution.steps) - 1, "expect": expected}]
        result.append(
            AcceptanceReview(
                case_id=case.id,
                reason="독립 계산 근거와 기존 입력·실패 조건을 확인했습니다.",
                replacements=replacements,
            )
        )
    return tuple(result)
