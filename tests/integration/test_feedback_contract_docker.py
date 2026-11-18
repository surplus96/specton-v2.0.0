"""Reviewed mail changes produce actual numeric differences; stale oracles fail."""

import hashlib
import json
import os
from pathlib import Path

import pytest
from calculation_support import calculation_case
from feedback_contract_support import QUOTE, reviews, suggestion

from specton.feedback.analysis import propose
from specton.implementation.package import generate
from specton.implementation.verify import docker, verify

pytestmark = [
    pytest.mark.docker_browser,
    pytest.mark.skipif(
        os.environ.get("SPECTON_TEST_FEEDBACK_CONTRACT_DOCKER") != "1", reason="explicit Docker run"
    ),
]


@pytest.mark.parametrize(
    "domain,update_oracle", [("inventory", True), ("maintenance", True), ("inventory", False)]
)
def test_reviewed_rounding_change_and_stale_oracle(domain, update_oracle, tmp_path):
    base, state, artifacts = calculation_case(domain)
    changed, details = propose(
        base, suggestion(base), QUOTE, reviews(base, change_average=update_oracle)
    )
    assert not details["acceptance_review"]["pending_case_ids"]
    source = generate(changed, state, artifacts)
    images = [
        docker(["image", "inspect", tag, "--format", "{{.Id}}"]).decode().strip()
        for tag in (
            "specton-generated-runtime:calculation-v1",
            "postgres:18",
            os.environ.get("SPECTON_TEST_BROWSER_IMAGE", "specton-browser:generated-ui-v1"),
        )
    ]
    report = verify(
        source, hashlib.sha256(source).hexdigest(), images[0], images[1], browser_image=images[2]
    )
    output = Path(os.environ.get("SPECTON_TEST_FEEDBACK_CONTRACT_REPORT_DIR", str(tmp_path)))
    output.mkdir(parents=True, exist_ok=True)
    label = domain + ("-reviewed" if update_oracle else "-stale-oracle")
    (output / (label + ".zip")).write_bytes(source)
    (output / (label + "-report.json")).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    assert report["cleanup_complete"]
    assert report["business_acceptance"] == "not_run"
    if update_oracle:
        assert report["status"] == "smoke_passed", report
        assert report["executable_acceptance"]["status"] == "passed"
        assert report["browser_acceptance"] == "passed"
    else:
        assert report["status"] == "failed"
        assert report["browser_acceptance"] == "not_run"
        assert any(
            s.get("reason") == "BODY_MISMATCH"
            for c in report["executable_acceptance"]["cases"]
            for s in c["steps"]
        )
