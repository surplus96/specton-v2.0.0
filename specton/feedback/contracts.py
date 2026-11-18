"""Bounded contract edits and human-only review of independent acceptance oracles."""

from typing import Annotated, Any

from pydantic import Field, StringConstraints

from specton.contracts.acceptance import ExactResponse
from specton.contracts.base import Contract

COMMAND_FIELDS = {"before", "after", "writes", "calculations"}
QUERY_FIELDS = {"filters", "windows", "max_rows", "aggregates", "calculations"}


class ExpectedResultReview(Contract):
    step_index: int = Field(ge=0, le=23)
    expect: ExactResponse


class AcceptanceReview(Contract):
    case_id: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=2000)]
    replacements: tuple[ExpectedResultReview, ...] = Field(default=(), max_length=24)


def preserve_structure(field: str, old: Any, new: Any) -> None:
    """Policy changes cannot silently remove guards, targets, filters or calculation nodes."""
    if field == "max_rows":
        return
    if not isinstance(new, list) or len(old) != len(new):
        raise ValueError("기존 조건·쓰기·집계·계산 항목은 삭제하거나 추가할 수 없습니다.")
    for before, after in zip(old, new, strict=True):
        if not isinstance(after, dict):
            raise ValueError("계약 항목은 객체여야 합니다.")
        stable = {
            "calculations": ("id",),
            "aggregates": ("id", "column_id"),
            "filters": ("column_id", "input_field_id"),
            "windows": ("column_id", "start_field_id", "end_field_id"),
            "writes": ("target",),
            "before": ("left",),
            "after": ("left",),
        }[field]
        if any(before.get(key) != after.get(key) for key in stable):
            raise ValueError("기존 계약 대상·입력·조건 출처는 유지해야 합니다.")
        if field == "writes" and (
            not isinstance(after.get("values"), dict)
            or set(before["values"]) != set(after["values"])
        ):
            raise ValueError("쓰기 대상 컬럼은 유지해야 합니다.")


def review_acceptance(
    data: dict[str, Any], reviews: tuple[AcceptanceReview, ...], required: bool
) -> dict[str, Any]:
    # All executable cases: commands can affect queries and indirect downstream reads.
    cases = {c["id"]: c for c in data["acceptance_cases"] if c.get("execution")} if required else {}
    seen: set[str] = set()
    changes = []
    for review in reviews:
        if review.case_id not in cases or review.case_id in seen:
            raise ValueError("검토 대상 인수 사례가 없거나 중복되었습니다.")
        seen.add(review.case_id)
        steps = cases[review.case_id]["execution"]["steps"]
        indexes: set[int] = set()
        for replacement in review.replacements:
            i = replacement.step_index
            if i >= len(steps) or i in indexes:
                raise ValueError("인수 단계가 없거나 중복되었습니다.")
            indexes.add(i)
            before = steps[i]["expect"]
            after = replacement.expect.model_dump(mode="json")
            # Negative/security/replay coverage, status, requests and steps stay intact.
            if before["kind"] != "exact" or before["status"] != after["status"]:
                raise ValueError("실패·권한 검사와 응답 상태는 변경할 수 없습니다.")
            old, new = before["body"], after["body"]
            if isinstance(old, dict):
                same = isinstance(new, dict) and old.keys() == new.keys()
            else:
                same = (
                    isinstance(new, list)
                    and len(old) == len(new)
                    and all(a.keys() == b.keys() for a, b in zip(old, new, strict=True))
                )
            if not same:
                raise ValueError("기대 응답의 필드·행 개수는 줄이거나 변경할 수 없습니다.")
            if before != after:
                changes.append(
                    {
                        "case_id": review.case_id,
                        "step_index": i,
                        "before": before,
                        "after": after,
                        "reason": review.reason,
                    }
                )
                steps[i]["expect"] = after
    return {
        "required_case_ids": sorted(cases),
        "pending_case_ids": sorted(set(cases) - seen),
        "reviews": [r.model_dump(mode="json") for r in reviews],
        "expectation_changes": changes,
        "source": "owner_review_only",
    }
