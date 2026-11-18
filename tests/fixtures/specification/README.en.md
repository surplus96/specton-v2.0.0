# Executable specification format example

[![한국어](../../../docs/assets/lang-ko.svg)](README.md) [![English](../../../docs/assets/lang-en.svg)](README.en.md)

`item-create-v0.1.json` is a synthetic **early-format** example of item creation and quantity constraints. Baseline UUIDs and hashes are test values, not real project approvals. This file cannot perform actual source generation or approval.

```bash
uv run python -m specton.specification tests/fixtures/specification/item-create-v0.1.json
```

Success returns `ready_for_review: true` and the spec hash. Unanswered questions or required trace gaps return exit code 1; file/contract errors return 2. Syntax/reference validation does not establish support for every current generator feature or executable acceptance.

Current domain, command, calculation, and acceptance contracts are described in [SDD](../../../docs/en/sdd.md), with separate synthetic fixtures in `tests/domain_support.py`, `tests/command_support.py`, and `tests/calculation_support.py`. Preserve this initial fixture rather than rewriting it as a current approved specification.
