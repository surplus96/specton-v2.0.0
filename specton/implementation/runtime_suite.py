"""Bind all trusted API verification code to the worker job and prepared image."""

import hashlib

from specton.implementation.package import TEMPLATES, json_bytes


def suite_files() -> dict[str, str]:
    return {
        name: hashlib.sha256((TEMPLATES / "runtime" / (name + ".txt")).read_bytes()).hexdigest()
        for name in ("probe.py", "acceptance_runner.py")
    }


def suite_hash() -> str:
    return hashlib.sha256(json_bytes(suite_files())).hexdigest()
