"""Scripted Google/analysis; real approval, immutable designs, proposal review and job queue."""

import hashlib
import io
import json
import zipfile

import pytest
import test_feedback_consistency
from feedback_contract_support import reviews
from pydantic import SecretStr
from test_feedback import connected as connected
from test_feedback import request_change
from test_feedback import settings as settings
from test_feedback import verified as verified
from test_feedback import workspace as workspace
from test_identity_projects import headers
from test_specifications import edit, expectation

from specton.api import implementations
from specton.contracts import DesignState
from specton.contracts.specification import SpecBundle
from specton.feedback import analysis, worker
from specton.implementation.calculations import QUERY_ERRORS
from specton.implementation.domain import compile_domain
from specton.implementation.verify import inspect_package

pytestmark = pytest.mark.db


def mail():
    from test_feedback import mail as original_mail

    value = original_mail()
    value.update(
        subject="계산 반올림 변경 요청",
        body="건수 비율의 소수 두 자리 반올림을 half_even에서 half_up으로 변경해 주세요.",
    )
    return value


@pytest.fixture(autouse=True)
def policy_mail(monkeypatch):
    import test_feedback

    original = test_feedback.mail()
    original.update(
        subject="계산 반올림 변경 요청",
        body="건수 비율의 소수 두 자리 반올림을 half_even에서 half_up으로 변경해 주세요.",
    )
    monkeypatch.setattr(test_feedback, "mail", lambda: original)


@pytest.fixture
def base_source(workspace):
    return test_feedback_consistency.source.__wrapped__(workspace)


@pytest.fixture
def source(base_source, pool):
    client, original, _ = base_source
    base = SpecBundle.model_validate(original["bundle"])
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT normalized_model FROM model_snapshot WHERE run_id=%s AND revision=%s",
            (base.baseline.source_run_id, base.baseline.source_revision),
        ).fetchone()
    state = DesignState.model_validate(
        {**row["normalized_model"], "run_id": str(base.baseline.source_run_id)}
    )
    config = compile_domain(base, state)["domain"]
    seed = config["fixtures"][0]  # First table has no FK prerequisites.
    table = next(t for t in config["tables"] if t["id"] == seed["table_id"])
    numeric = next(
        (t, c) for t in config["tables"] for c in t["columns"] if c["data_type"] == "numeric"
    )
    data = base.model_dump(mode="json")
    data["schema_version"] = "spec-v0.9"
    data["domain"]["version"] = "domain-ir-v3"
    rid = data["requirements"][0]["id"]
    role = data["roles"][0]["id"]
    inp = [{"id": "INPUT-divisor", "name": "divisor", "data_type": "decimal", "required": True}]
    out = [{"id": "OUTPUT-ratio", "name": "ratio", "data_type": "decimal", "required": True}]
    data["use_cases"].append(
        dict(
            id="UC-summary",
            name="합성 건수 비율",
            req_ids=[rid],
            actor_roles=[role],
            preconditions=["고정 합성 분모"],
            inputs=inp,
            outputs=out,
            steps=["건수 나누기"],
            error_codes=sorted(QUERY_ERRORS),
            transaction="read_only",
            idempotency="not_applicable",
        )
    )
    data["apis"].append(
        dict(
            id="API-summary",
            use_case_id="UC-summary",
            method="POST",
            path="/calculations/summary",
            actor_roles=[role],
            request_fields=inp,
            response_fields=out,
            success_status=200,
            error_codes=sorted(QUERY_ERRORS),
            pagination="none",
            concurrency="read_only",
        )
    )
    data["screens"].append(
        dict(
            id="SCREEN-summary",
            route="/summary",
            name="합성 건수 비율",
            actor_roles=[role],
            api_ids=["API-summary"],
            empty_state="분모 입력",
            loading_state="계산 중",
            error_state="입력 확인",
        )
    )
    data["domain"]["calculations"] = [
        dict(
            api_id="API-summary",
            table_id=table["id"],
            input_bindings=[
                dict(
                    field_id="INPUT-divisor", table_id=numeric[0]["id"], column_id=numeric[1]["id"]
                )
            ],
            column_units=[dict(table_id=numeric[0]["id"], column_id=numeric[1]["id"], unit={})],
            filters=[],
            windows=[],
            max_rows=10,
            aggregates=[
                dict(
                    id="count",
                    operator="count",
                    column_id=None,
                    null_policy="ignore",
                    empty_policy="zero",
                    result=dict(precision=12, scale=0, rounding="half_even", unit={}),
                )
            ],
            calculations=[
                dict(
                    id="ratio",
                    operator="divide",
                    left=dict(kind="aggregate", aggregate_id="count"),
                    right=dict(kind="input", field_id="INPUT-divisor"),
                    result=dict(precision=12, scale=2, rounding="half_even", unit={}),
                    null_policy="error",
                    zero_division="error",
                )
            ],
            returns={"OUTPUT-ratio": dict(kind="calculated", calculation_id="ratio")},
        )
    ]
    seed_step = dict(
        api_id=seed["api_id"],
        body=seed["values"],
        request_key="seed",
        expect=dict(kind="exact", status=200, body=seed["values"]),
    )
    seed_use = next(a["use_case_id"] for a in data["apis"] if a["id"] == seed["api_id"])
    for category, initial, divisor, expected in [
        ("normal", [seed_step], "8", dict(kind="exact", status=200, body={"ratio": "0.12"})),
        ("boundary", [], "8", dict(kind="exact", status=200, body={"ratio": "0.00"})),
        ("failure", [], "0", dict(kind="error", status=409, code="CALCULATION_ERROR")),
    ]:
        data["acceptance_cases"].append(
            dict(
                id="TC-summary-" + category,
                req_ids=[rid],
                use_case_ids=["UC-summary", seed_use],
                tier="api",
                given=["고정 합성 데이터"],
                when="건수/8 조회",
                then=["독립 계산 기대값 확인"],
                fixture_ids=["FIX-summary"],
                execution=dict(
                    category=category,
                    steps=[
                        *initial,
                        dict(api_id="API-summary", body={"divisor": divisor}, expect=expected),
                    ],
                ),
            )
        )
    saved = edit(client, original, data)
    assert saved.status_code == 200, saved.text
    spec = saved.json()
    url = "/api/v1/specs/" + spec["bundle"]["spec_id"]
    approved = client.post(url + "/approve", json=expectation(spec), headers=headers(client))
    assert approved.status_code == 200, approved.text
    created = client.post(url + "/implementations", json=expectation(spec), headers=headers(client))
    assert created.status_code == 200, created.text
    return client, spec, created.json()


def proposed(verified):
    bundle = verified[0][1]["bundle"]
    program = bundle["domain"]["calculations"][0]["calculations"]
    program = json.loads(json.dumps(program))
    program[0]["result"]["rounding"] = "half_up"
    return analysis.Analysis(
        summary="합성 계산 반올림 변경",
        quotes=[mail()["body"]],
        requests=["half_up 반올림"],
        questions=[],
        unsupported=[],
        suggestions=[
            dict(
                section="domain_calculations",
                object_id="API-summary",
                field="calculations",
                value_json=json.dumps(program),
                rationale="고정 합성 계산 정책 변경",
            )
        ],
    )


def owner_reviews(verified):
    bundle = SpecBundle.model_validate(verified[0][1]["bundle"])
    rows = [r.model_dump(mode="json") for r in reviews(bundle)]
    case = next(c for c in bundle.acceptance_cases if c.id == "TC-summary-normal")
    row = next(r for r in rows if r["case_id"] == case.id)
    row["replacements"] = [
        {"step_index": 1, "expect": {"kind": "exact", "status": 200, "body": {"ratio": "0.13"}}}
    ]
    return rows


def test_mail_calculation_review_gate_compile_and_atomic_regeneration(
    connected, pool, settings, monkeypatch
):
    client, _, verified = connected
    original = verified[0][1]
    old_source = client.get("/api/v1/implementations/" + verified[0][2]["id"] + "/source").content
    row = request_change(connected, pool, settings, monkeypatch)
    root = "/api/v1/changes/" + row["id"]
    settings.openai_api_key = SecretStr("synthetic-key")
    monkeypatch.setattr(analysis, "run", lambda *args: (proposed(verified), []))
    response = client.post(
        root + "/analyse",
        headers=headers(client),
        json={"expected_version": row["version"], "consent_external_analysis": True},
    )
    assert response.status_code == 202, response.text
    assert worker.run_once(pool, settings)
    row = client.get(root).json()
    assert row["state"] == "needs_input", row
    assert row["analysis"]["acceptance_review"]["pending_case_ids"]
    with pool.connection() as conn:
        proposal = conn.execute(
            "SELECT proposal FROM feedback_change WHERE id=%s", (row["id"],)
        ).fetchone()["proposal"]
    assert proposal["acceptance_cases"] == original["bundle"]["acceptance_cases"]
    decision = dict(
        expected_version=row["version"],
        target_hash=row["proposal_hash"],
        decision="approve",
        note="원문과 계산 검토를 확인합니다.",
        acknowledge_unverified_acceptance=True,
    )
    assert client.post(root + "/decide", headers=headers(client), json=decision).status_code == 409
    bad = proposed(verified).model_dump(mode="json")
    program = json.loads(bad["suggestions"][0]["value_json"])
    program[0]["result"]["unit"] = {"money": 1}
    bad["suggestions"][0]["value_json"] = json.dumps(program)
    assert (
        client.put(
            root + "/proposal",
            headers=headers(client),
            json=dict(expected_version=row["version"], analysis=bad),
        ).status_code
        == 422
    )
    response = client.put(
        root + "/proposal",
        headers=headers(client),
        json=dict(
            expected_version=row["version"],
            analysis=proposed(verified).model_dump(mode="json"),
            acceptance_reviews=owner_reviews(verified),
        ),
    )
    assert response.status_code == 200, response.text
    row = response.json()
    assert row["state"] == "awaiting_decision"
    assert row["proposal_hash"] != decision["target_hash"]
    assert (
        client.post(
            root + "/decide",
            headers=headers(client),
            json={**decision, "expected_version": row["version"]},
        ).status_code
        == 409
    )
    row = client.post(
        root + "/decide",
        headers=headers(client),
        json={**decision, "expected_version": row["version"], "target_hash": row["proposal_hash"]},
    ).json()
    assert row["state"] == "approved"
    approved_version = row["version"]
    with monkeypatch.context() as patch:

        def failure(*args, **kwargs):
            from fastapi import HTTPException

            raise HTTPException(503, "synthetic queue failure")

        patch.setattr(implementations, "request_verification", failure)
        assert (
            client.post(
                root + "/implement",
                headers=headers(client),
                json=dict(expected_version=approved_version),
            ).status_code
            == 503
        )
    spec_url = "/api/v1/specs/" + original["bundle"]["spec_id"]
    assert client.get(spec_url).json()["bundle"] == original["bundle"]
    response = client.post(
        root + "/implement", headers=headers(client), json=dict(expected_version=approved_version)
    )
    assert response.status_code == 200, response.text
    row = response.json()
    assert row["state"] == "validating"
    content = client.get("/api/v1/implementations/" + row["implementation_id"] + "/source").content
    files, _ = inspect_package(content, hashlib.sha256(content).hexdigest())
    new = client.get(spec_url).json()
    assert (
        new["bundle"]["domain"]["calculations"][0]["calculations"][0]["result"]["rounding"]
        == "half_up"
    )
    assert next(c for c in new["bundle"]["acceptance_cases"] if c["id"] == "TC-summary-normal")[
        "execution"
    ]["steps"][-1]["expect"]["body"] == {"ratio": "0.13"}
    with zipfile.ZipFile(io.BytesIO(client.get(spec_url + "/design").content)) as archive:
        for name in archive.namelist():
            assert archive.read(name) == files["design/revised/" + name]
    assert (
        client.get("/api/v1/implementations/" + verified[0][2]["id"] + "/source").content
        == old_source
    )
    assert (
        client.get(spec_url + "/versions/" + str(original["bundle"]["spec_version"])).json()[
            "bundle"
        ]
        == original["bundle"]
    )
    assert (
        client.post(
            root + "/implement",
            headers=headers(client),
            json=dict(expected_version=approved_version),
        ).json()["implementation_id"]
        == row["implementation_id"]
    )
