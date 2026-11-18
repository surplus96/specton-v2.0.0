import hashlib
import importlib.machinery
import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest
from acceptance_support import scenarios
from domain_support import case
from pydantic import ValidationError

from specton.contracts.specification import SpecBundle
from specton.implementation.acceptance_evidence import case_results, require_passed
from specton.implementation.domain import compile_domain
from specton.implementation.package import generate
from specton.implementation.requirement_results import requirement_results
from specton.implementation.verify import inspect_package
from specton.specification.readiness import canonical_bytes, spec_hash


def runner():
    loader = importlib.machinery.SourceFileLoader(
        "acceptance_test_runner",
        "specton/implementation/templates/runtime/acceptance_runner.py.txt",
    )
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module.run_cases


def test_version_binding_old_canonical_bytes_and_package():
    draft, state, artifacts = case()
    old = json.loads(canonical_bytes(draft))
    assert all("execution" not in c for c in old["acceptance_cases"])
    spec = scenarios(draft)
    src = generate(spec, state, artifacts)
    files, manifest = inspect_package(src, hashlib.sha256(src).hexdigest())
    assert manifest["template_version"] == "executable-design-v11"
    assert len(json.loads(files["backend/contract.json"])["executable_cases"]) == 4
    changed = spec.model_dump(mode="json")
    changed["acceptance_cases"][-1]["execution"]["steps"][-1]["expect"]["status"] = 401
    changed["acceptance_cases"][-1]["execution"]["steps"][-1]["expect"]["code"] = "AUTH_REQUIRED"
    assert spec_hash(SpecBundle.model_validate(changed)) != spec_hash(spec)
    for path in Path("var/test-results/domain-readiness").glob("*.zip"):
        content = path.read_bytes()
        inspect_package(content, hashlib.sha256(content).hexdigest())


@pytest.mark.parametrize(
    "mutation",
    [
        "old_version",
        "browser",
        "unknown_api",
        "wrong_case",
        "missing_key",
        "read_body",
        "url",
        "wrong_error",
        "too_many",
    ],
)
def test_invalid_or_unbounded_execution_is_rejected(mutation):
    draft, _, _ = case()
    data = scenarios(draft).model_dump(mode="json")
    item = data["acceptance_cases"][-1]
    step = item["execution"]["steps"][0]
    if mutation == "old_version":
        data["schema_version"] = "spec-v0.6"
    if mutation == "browser":
        item["tier"] = "browser"
    if mutation == "unknown_api":
        step["api_id"] = "API-unknown"
    if mutation == "wrong_case":
        item["use_case_ids"] = []
    if mutation == "missing_key":
        step["request_key"] = None
    if mutation == "read_body":
        item["execution"]["steps"][-1]["body"] = {}
    if mutation == "url":
        step["url"] = "https://example.com"
    if mutation == "wrong_error":
        item["execution"]["steps"][-1]["expect"]["code"] = "RULE_VIOLATION"
    if mutation == "too_many":
        item["execution"]["steps"] *= 40
    with pytest.raises(ValidationError):
        SpecBundle.model_validate(data)


def test_runner_isolates_cases_detects_bad_oracle_and_never_reports_prose_passed():
    draft, state, _ = case()
    spec = scenarios(draft)
    config = compile_domain(spec, state)
    cases = config["executable_cases"][:1]
    ops = {o["id"]: o for o in config["domain"]["operations"]}
    resets = []
    index = 0

    def request(op, step):
        nonlocal index
        index += 1
        # Deliberately wrong server output for the independently authored final assertion.
        return 200, step["expect"]["body"] if index < 6 else []

    result = runner()(cases, ops, request, lambda: resets.append(True))
    assert result["status"] == "failed" and len(resets) == 2
    assert result["cases"][0]["steps"][-1]["reason"] == "BODY_MISMATCH"
    mapped = requirement_results(spec, [], result)
    statuses = {t["id"]: t["status"] for row in mapped["items"] for t in row["acceptance_cases"]}
    assert statuses[cases[0]["id"]] == "failed"
    assert all(statuses[t.id] == "not_run" for t in spec.acceptance_cases if not t.execution)


def test_pass_requires_every_approved_step_and_matching_identity():
    draft, state, _ = case()
    spec = scenarios(draft)
    config = compile_domain(spec, state)

    def request(op, step):
        e = step["expect"]
        return e["status"], e.get("body", {"detail": e.get("code")})

    result = runner()(
        config["executable_cases"],
        {o["id"]: o for o in config["domain"]["operations"]},
        request,
        lambda: None,
    )
    require_passed(spec, result)
    for mutate in ("missing_step", "wrong_api", "duplicate_case", "wrong_req", "no_report"):
        bad = deepcopy(result)
        if mutate == "missing_step":
            bad["cases"][0]["steps"].pop()
        if mutate == "wrong_api":
            bad["cases"][0]["steps"][0]["api_id"] = "API-wrong"
        if mutate == "duplicate_case":
            bad["cases"].append(bad["cases"][0])
        if mutate == "wrong_req":
            bad["cases"][0]["req_ids"] = ["REQ-other"]
        if mutate == "no_report":
            bad = None
        with pytest.raises(ValueError):
            require_passed(spec, bad)
    assert all(v["status"] == "not_run" for v in case_results(spec, None).values())


def test_model_proposal_cannot_replace_existing_oracle():
    from specton.specification.completion import validate_proposal

    spec = scenarios(case()[0])
    changed = spec.model_dump(mode="json")
    changed["acceptance_cases"][-1]["execution"]["category"] = "normal"
    with pytest.raises(ValueError, match="실행 인수"):
        validate_proposal(spec, SpecBundle.model_validate(changed))


def test_worker_rejects_scenario_omission_before_any_writes():
    from types import SimpleNamespace

    from specton.implementation.jobs import finish

    spec = scenarios(case()[0])
    conn = SimpleNamespace(
        execute=lambda *args: SimpleNamespace(
            fetchone=lambda: {"payload": spec.model_dump(mode="json")}
        )
    )
    job = dict(
        implementation_id="synthetic",
        source_hash="source",
        spec_hash=spec_hash(spec),
        runtime_image="runtime",
        postgres_image="postgres",
        suite_hash="suite",
    )
    report = {
        **job,
        "status": "smoke_passed",
        "business_acceptance": "not_run",
        "browser_acceptance": "not_run",
        "cleanup_complete": True,
        "checks": [{"status": "passed"}],
    }
    with pytest.raises(ValueError, match="실행 인수"):
        finish(conn, job, report)


def test_transport_error_stops_later_cases_and_redacts_exception():
    draft, state, _ = case()
    config = compile_domain(scenarios(draft), state)
    calls = []

    def request(op, step):
        calls.append(op["id"])
        raise TimeoutError("sensitive-internal-value")

    result = runner()(
        config["executable_cases"],
        {o["id"]: o for o in config["domain"]["operations"]},
        request,
        lambda: None,
    )
    assert len(calls) == 1
    assert [c["status"] for c in result["cases"]] == ["failed", "not_run", "not_run", "not_run"]
    assert "sensitive-internal-value" not in json.dumps(result)
