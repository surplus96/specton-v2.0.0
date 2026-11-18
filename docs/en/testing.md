# Testing and reproducible verification

[![한국어](../assets/lang-ko.svg)](../ko/testing.md) [![English](../assets/lang-en.svg)](../en/testing.md)

## Distinct evidence levels

| Check | Meaning |
|---|---|
| Unit/contract tests | Fixed parser, type, reference, and generator cases |
| SQL sandbox | Allowed DDL execution and rollback |
| Executable API acceptance | Actual responses match approved inputs/expectations |
| Chromium checks | Fixed generated-UI browser scenarios |
| Isolated preview | Human inspection with synthetic data |
| Business acceptance | Separate review of included business requirements |

Passing one level does not imply passing the next or satisfying every original requirement. Keep structural checks separate from unexecuted prose acceptance. Report skipped, failed, and unexecuted checks.

## Baseline checks without external calls

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv run python scripts/check_docs.py
uv run python -m specton.packs.build --check
uv run python -m specton.evaluation.baseline --repeats 1
npm --prefix frontend run lint
npm --prefix frontend run check:api
npm --prefix frontend test
npm --prefix frontend run build
```

Default pytest excludes `db` and `llm`. Native/Docker checks may skip based on environment; this is not complete integration coverage. [ci.yml](../../.github/workflows/ci.yml) defines CI. Documentation checks include language-file parity and repository links.

## Database checks

Some tests read connection settings from environment variables rather than `.env`. Explicitly configure a separate test database, never production:

```bash
export SPECTON_APP_DATABASE_URL=postgresql://specton:specton@127.0.0.1:5432/specton_app
export SPECTON_SANDBOX_DATABASE_URL=postgresql://specton_sandbox:specton_sandbox@127.0.0.1:5432/specton_sandbox
uv run python -m specton.persistence.migrate upgrade
uv run pytest --require-db -m 'db and not native_pdf and not llm and not docker_browser'
```

These passwords are local examples; match your configuration if changed. `--require-db` fails on connection errors and skipped mandatory DB tests. Prepare images/renderers before selecting Docker/PDF integrations.

## Generated-app and feedback integration example

```bash
docker build -f docker/implementation/Dockerfile -t specton-generated-runtime:calculation-v1 .
docker build -f docker/browser/Dockerfile -t specton-browser:generated-ui-v1 .
docker pull postgres:18
export SPECTON_TEST_WORKER_RUNTIME="$(docker image inspect specton-generated-runtime:calculation-v1 --format '{{.Id}}')"
export SPECTON_TEST_WORKER_POSTGRES="$(docker image inspect postgres:18 --format '{{.Id}}')"
export SPECTON_TEST_BROWSER_IMAGE="$(docker image inspect specton-browser:generated-ui-v1 --format '{{.Id}}')"
export SPECTON_TEST_FEEDBACK_CONTRACT_DOCKER=1
uv run pytest -m docker_browser tests/integration/test_feedback_contract_docker.py
```

This exercises calculation changes for fixed inventory/maintenance contracts and a negative control retaining stale expectations. Tests using synthetic Google/OpenAI responses are separate from real external integration tests. Delivery and platform-browser tests require their documented environment variables and source-ZIP prerequisites; do not run all Docker tests without preparing them.

## Generation, change, and delivery checks

| Coverage | Tests |
|---|---|
| Domain-driven structural generation | [test_domain_generation.py](../../tests/unit/test_domain_generation.py) |
| Command compilation and atomicity | [test_atomic_command_compilation.py](../../tests/unit/test_atomic_command_compilation.py) |
| Calculation, unit, and precision contracts | [test_calculation_contract.py](../../tests/unit/test_calculation_contract.py) |
| Specification/design consistency | [test_change_consistency.py](../../tests/unit/test_change_consistency.py) |
| Gmail command-change execution | [test_feedback_command_runtime.py](../../tests/integration/test_feedback_command_runtime.py) |
| Gmail calculation changes and negative controls | [test_feedback_contract_docker.py](../../tests/integration/test_feedback_contract_docker.py) |
| Transfer rollback and retry | [test_data_transfer.py](../../tests/integration/test_data_transfer.py) |
| Customer identity and delivery package | [test_customer_delivery_docker.py](../../tests/integration/test_customer_delivery_docker.py) |

For a real browser E2E, follow the [workflow](workflow.md): analysis → design approval → spec approval → generation/verification → preview/adoption → Gmail ingestion/change approval → regeneration/re-verification/re-adoption. Inventory and maintenance use separate projects and approved designs. Distinguish actual Google/Gmail/OpenAI execution from automated checks using synthetic responses.

## Executable cases

Each case begins with an empty isolated database. Steps use declared API IDs, roles, inputs, and request keys to seed data and verify stored or unstored results through later reads. Successful status/full bodies and failed status/error codes are compared. JSON types and list order are part of the contract. A mismatch stops subsequent steps; unknown APIs or evidence from another source cannot establish a pass.

## Synthetic fixtures and model evaluation

[Baseline fixtures](../../tests/fixtures/baseline/README.en.md) measure deterministic CSV parsing, normalization, and artifact generation—not model semantics, browser behavior, or large entity-model performance. [Specification fixtures](../../tests/fixtures/specification/README.en.md) validate format and do not substitute for real approved baselines.

Real model tests require explicit `uv run pytest -m llm`. Use authorized synthetic data and credentials; record cost, input/pack/prompt/model versions, and failure denominators. Keep evaluation answers separate from model inputs and few-shot examples. Private customer documents and local recording results do not belong in the published repository.

Report commands, environment, commit/content hashes, and pass/fail/skip scope for new results. Historical test counts are not guarantees for the current build.

---

[Documentation](README.md) · [Project](../../README.en.md)
