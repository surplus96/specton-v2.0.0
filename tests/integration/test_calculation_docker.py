"""Verify sealed command packages with independent oracles on offline Docker networks."""

import hashlib
import json
import os
from pathlib import Path

import pytest
from calculation_support import calculation_case

from specton.contracts.specification import SpecBundle
from specton.implementation.package import generate
from specton.implementation.verify import docker, verify

pytestmark = [
    pytest.mark.docker_browser,
    pytest.mark.skipif(
        os.environ.get("SPECTON_TEST_CALCULATIONS_DOCKER") != "1",
        reason="explicit command Docker run required",
    ),
]


@pytest.mark.parametrize(
    "domain,wrong", [("inventory", False), ("maintenance", False), ("inventory", True)]
)
def test_calculation_package_and_independent_failure_oracle(domain, wrong, tmp_path):
    bundle, state, artifacts = calculation_case(domain)
    if wrong:
        data = bundle.model_dump(mode="json")
        case = next(c for c in data["acceptance_cases"] if c["id"] == "TC-summary-normal")
        step = next(s for s in case["execution"]["steps"] if s["api_id"] == "API-summary")
        step["expect"]["body"]["total"] = "99.00"
        bundle = SpecBundle.model_validate(data)
    content = generate(bundle, state, artifacts)
    images = [
        docker(["image", "inspect", tag, "--format", "{{.Id}}"]).decode().strip()
        for tag in (
            "specton-generated-runtime:calculation-v1",
            "postgres:18",
            os.environ.get("SPECTON_TEST_BROWSER_IMAGE", "specton-browser:generated-ui-v1"),
        )
    ]
    report = verify(
        content, hashlib.sha256(content).hexdigest(), images[0], images[1], browser_image=images[2]
    )
    root = Path(os.environ.get("SPECTON_TEST_CALCULATIONS_REPORT_DIR", str(tmp_path)))
    root.mkdir(parents=True, exist_ok=True)
    label = domain + ("-wrong-oracle" if wrong else "")
    (root / (label + ".zip")).write_bytes(content)
    (root / (label + "-report.json")).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    assert report["cleanup_complete"] is True
    assert report["business_acceptance"] == "not_run"
    evidence = report["executable_acceptance"]
    assert len(evidence["cases"]) == 6
    if wrong:
        assert report["status"] == "failed"
        assert report["browser_acceptance"] == "not_run"
        assert evidence["cases"][3]["status"] == "failed"
        assert any(s.get("reason") == "BODY_MISMATCH" for s in evidence["cases"][3]["steps"])
    else:
        assert report["status"] == "smoke_passed", report
        assert report["browser_acceptance"] == "passed"
        assert evidence["status"] == "passed"
