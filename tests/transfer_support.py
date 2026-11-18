"""Fixed customer request and source values; never derive oracles from app responses."""

import hashlib

from domain_support import case, reviewed

from specton.feedback.analysis import Analysis, Suggestion, propose
from specton.implementation.data_transfer import plan
from specton.implementation.package import generate


def change(domain="booking"):
    draft, state, originals = case(domain)
    before = reviewed(draft)
    column = next(
        c.id for t in state.normalized.tables for c in t.columns if c.physical_name == "amount"
    )
    operations = [
        o
        for o in before.domain.operations
        if o.table_id == state.normalized.tables[1].id and o.action in ("insert", "update")
    ]
    quote = (
        "화면 이름을 고객 요청 화면으로 바꾸고, 이후 등록·수정하는 금액은 10 이하여야 합니다. "
        "기존 기록은 그대로 보관하세요."
    )
    import json

    analysis = Analysis(
        summary=quote,
        quotes=[quote],
        requests=[quote],
        questions=[],
        unsupported=[],
        suggestions=[
            Suggestion(
                section="screens",
                object_id=before.screens[0].id,
                field="name",
                value_json='"고객 요청 화면"',
                rationale=quote,
            ),
            *[
                Suggestion(
                    section="domain_operations",
                    object_id=o.api_id,
                    field="guards",
                    value_json=json.dumps([{"column_id": column, "operator": "le", "value": "10"}]),
                    rationale=quote,
                )
                for o in operations
            ],
        ],
    )
    after, details = propose(before, analysis, quote)
    after = after.evolve(spec_version=before.spec_version + 1)
    old = generate(before, state, originals)
    new = generate(after, state, originals)
    frozen = plan(old, hashlib.sha256(old).hexdigest(), new, hashlib.sha256(new).hexdigest())
    return before, after, state, originals, old, new, frozen, details
