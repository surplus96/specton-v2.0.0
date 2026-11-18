"""Opt-in real HTTP/DB/Chromium acceptance and deliberately wrong oracle regression."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest
from acceptance_support import scenarios
from domain_support import case

from specton.contracts.specification import SpecBundle
from specton.implementation.package import generate
from specton.implementation.verify import verify

pytestmark = [
    pytest.mark.docker_browser,
    pytest.mark.skipif(
        os.environ.get("SPECTON_TEST_ACCEPTANCE_DOCKER") != "1",
        reason="explicit Docker acceptance run required",
    ),
]


@pytest.mark.parametrize(
    "domain,wrong_oracle",
    [("booking", False), ("maintenance", False), ("maintenance", True), ("booking", "structural")],
)
def test_approved_scenarios_and_independent_failure_oracle(domain, wrong_oracle, tmp_path):
    draft, state, artifacts = case(domain)
    spec = scenarios(draft)
    if wrong_oracle is True:
        data = spec.model_dump(mode="json")
        target = next(t for t in data["acceptance_cases"] if t["execution"])
        target["execution"]["steps"][-1]["expect"]["body"][0]["amount"] = "99.00"
        spec = SpecBundle.model_validate(data)
    elif wrong_oracle == "structural":
        data = spec.model_dump(mode="json")
        rule = data["invariants"][0]
        amount = rule["comparisons"][0]["left"]
        rule["comparisons"].append(
            dict(operator="ne", left=amount, right=dict(kind="number", value="1"))
        )
        boundary = next(
            t
            for t in data["acceptance_cases"]
            if t["execution"] and t["execution"]["category"] == "boundary"
        )
        for step in boundary["execution"]["steps"]:
            if step["body"] and step["body"].get("amount") == "1.00":
                step["body"]["amount"] = "0.99"
            expected = step["expect"].get("body")
            rows = (
                expected
                if isinstance(expected, list)
                else [expected]
                if isinstance(expected, dict)
                else []
            )
            for row in rows:
                if row.get("amount") == "1.00":
                    row["amount"] = "0.99"
        spec = SpecBundle.model_validate(data)
    content = generate(spec, state, artifacts)
    images = [
        subprocess.check_output(
            ["docker", "image", "inspect", tag, "--format", "{{.Id}}"], text=True
        ).strip()
        for tag in (
            "specton-generated-runtime:inventory-ledger-v1",
            "postgres:18",
            "specton-browser:generated-ui-v1",
        )
    ]
    report = verify(
        content, hashlib.sha256(content).hexdigest(), images[0], images[1], browser_image=images[2]
    )
    out = Path(os.environ.get("SPECTON_TEST_ACCEPTANCE_REPORT_DIR", str(tmp_path)))
    out.mkdir(parents=True, exist_ok=True)
    label = domain + (
        "-structural-failure"
        if wrong_oracle == "structural"
        else "-wrong-oracle"
        if wrong_oracle
        else ""
    )
    (out / (label + ".zip")).write_bytes(content)
    (out / (label + "-report.json")).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    assert report["cleanup_complete"] is True
    assert report["business_acceptance"] == "not_run"
    evidence = report["executable_acceptance"]
    assert len(evidence["cases"]) == 4
    if wrong_oracle == "structural":
        assert report["status"] == "failed" and report["browser_acceptance"] == "not_run"
        assert evidence["status"] == "passed"
    elif wrong_oracle:
        assert report["status"] == "failed" and report["browser_acceptance"] == "not_run"
        assert evidence["cases"][0]["steps"][-1]["reason"] == "BODY_MISMATCH"
        assert [c["status"] for c in evidence["cases"]] == ["failed", "passed", "passed", "passed"]
    else:
        assert report["status"] == "smoke_passed" and report["browser_acceptance"] == "passed"
        assert evidence["status"] == "passed"
        assert sum(len(c["steps"]) for c in evidence["cases"]) == 22
        assert {
            c["status"]
            for r in report["requirements"]["items"]
            for c in r["acceptance_cases"]
            if c["execution_kind"] == "api"
        } == {"passed"}
