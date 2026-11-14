import hashlib

import pytest

from specton.implementation.jobs import finish, public
from specton.implementation.package import json_bytes


def test_read_rejects_altered_evidence():
    original = {"status": "failed"}
    with pytest.raises(ValueError, match="해시"):
        public(
            {
                "report": {"status": "smoke_passed"},
                "report_hash": hashlib.sha256(json_bytes(original)).hexdigest(),
            }
        )


@pytest.mark.parametrize(
    "change",
    [
        {"source_hash": "wrong"},
        {"suite_hash": "wrong"},
        {"cleanup_complete": False},
        {"business_acceptance": "passed"},
        {"checks": []},
        {"checks": [{"status": "failed"}]},
    ],
)
def test_worker_rejects_unbound_or_incomplete_pass(change):
    job = dict(
        source_hash="source",
        spec_hash="spec",
        runtime_image="runtime",
        postgres_image="postgres",
        suite_hash="suite",
    )
    report = {
        **job,
        "status": "smoke_passed",
        "cleanup_complete": True,
        "business_acceptance": "not_run",
        "browser_acceptance": "not_run",
        "checks": [{"status": "passed"}],
        **change,
    }
    with pytest.raises(ValueError):
        finish(None, job, report)  # validation must happen before database writes


@pytest.mark.parametrize(
    "change",
    [
        {"browser_image": "different"},
        {"browser_suite_hash": "different"},
        {"browser": {"status": "passed", "checks": [{"status": "failed"}]}},
    ],
)
def test_browser_pass_requires_bound_image_suite_and_checks(change):
    job = dict(
        source_hash="s",
        spec_hash="spec",
        runtime_image="r",
        postgres_image="p",
        suite_hash="suite",
        browser_image="browser",
        browser_suite_hash="browser-suite",
    )
    report = {
        **job,
        "status": "smoke_passed",
        "cleanup_complete": True,
        "business_acceptance": "not_run",
        "browser_acceptance": "passed",
        "checks": [{"status": "passed"}],
        "browser": {"status": "passed", "checks": [{"status": "passed"}]},
        **change,
    }
    with pytest.raises(ValueError):
        finish(None, job, report)
