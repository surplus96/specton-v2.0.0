# Generic business execution contracts

[![한국어](../assets/lang-ko.svg)](../ko/business-contracts.md) [![English](../assets/lang-en.svg)](../en/business-contracts.md)

The generator compiles identifiers from the approved design and declarative execution contracts. It does not select fixed order, return, or equipment functionality from a domain name. Domain packs support terminology, types, and design interpretation; execution contracts define storage, authorization, transactions, and calculations.

## Contract layers

| Layer | Main model | Responsibility |
|---|---|---|
| Approved specification | [SpecBundle](../../specton/contracts/specification.py) | Design baseline, requirements, roles, APIs, screens, storage bindings, acceptance cases |
| Domain operations | [DomainPlan](../../specton/contracts/domain.py) | Record operations, requirement coverage, commands and calculations |
| Multi-record commands | [AtomicCommand](../../specton/contracts/commands.py) | Target rows, locks, pre/postconditions, writes, return values |
| Calculations/aggregates | [Calculation models](../../specton/contracts/calculations.py) | Exact numbers, units, operations, filters, aggregate policies |
| Executable acceptance | [Acceptance models](../../specton/contracts/acceptance.py) | API call sequences and response expectations |

Calculation-capable contracts use `spec-v0.9` / `domain-ir-v3`; the source template is `executable-design-v11`. Structural derivation can start with a `spec-v0.6` draft. These versions are independent of the repository name `v2.0.0` and project specification revisions.

## Record operations and guards

Supported operations are `insert`, `list`, `update`, and `transition`. API, field, table, and column bindings plus primary/foreign keys are validated against the approved structure. Comparisons use `eq`, `ne`, `lt`, `le`, `gt`, and `ge`. Typed field guards and explicit state transitions are reviewed as business policy.

Contract-driven record screens support search, pagination, edits, and relationship selectors. Delete operations, scheduled jobs, and external service calls are outside this record-operation set.

## Atomic multi-record commands

Declare read/update/insert targets, input bindings, pre/postconditions, calculations, writes, and return values in one command. The compiler validates targets, keys, columns, and roles. The runtime locks targets, checks conditions, and executes one PostgreSQL transaction.

An intermediate failure rolls back all writes and the request record. Replaying a successful request key returns the stored result. Failed commands can be retried with corrected input; concurrency and idempotency conflicts require explicit verification. Commands do not accept arbitrary SQL, Python, JavaScript, or external side effects.

Implementation: [compiler](../../specton/implementation/commands.py), [runtime](../../specton/implementation/templates/runtime/commands.py.txt). Checks: [atomic commands](../../tests/integration/test_atomic_commands.py), [Docker execution](../../tests/integration/test_atomic_commands_docker.py).

## Exact calculations and aggregates

| Area | Support |
|---|---|
| Operators | Addition, subtraction, multiplication, division, absolute value |
| Numbers | Decimal, precision/scale, `half_even`, `half_up`, and `down` rounding |
| Units | Compatibility checks across inputs, columns, literals, and results |
| Aggregates | Single-table `count`, `sum`, `average`, `min`, and `max` |
| Scope | Declared comparison filters, start/end bounds, maximum row count |
| Exceptions | Nulls, empty results, and division-by-zero policies |

A query is bounded to 10,000 rows, 16 aggregates, and 32 subsequent calculations. Results bind to API responses and screens; calculated values can also feed command writes. Arbitrary joins, grouped analytics, and executable statistical languages are outside this aggregate contract.

Implementation: [compiler](../../specton/implementation/calculations.py), [runtime](../../specton/implementation/templates/runtime/calculations.py.txt). Checks: [contracts](../../tests/unit/test_calculation_contract.py), [runtime](../../tests/integration/test_calculation_runtime.py).

## Executable acceptance and handoff readiness

Acceptance cases specify API IDs, roles, inputs, request keys, and response expectations. Checks compare successful status/full body or failure status/error code, and use subsequent reads to verify persistence. Prose-only cases are not marked automatically passed.

Readiness checks unresolved questions and missing API/screen/acceptance links. Handoff readiness additionally reports executable evidence and business-contract review obligations. The [preparation validator](../../scripts/validate_test_preparation.py) compares saved specifications and approved design snapshots offline; it neither runs nor approves an application.

## Contract updates through Gmail

Existing commands allow bounded changes to pre/postconditions, write values, and calculation policies. Existing aggregate queries allow bounded changes to filters, time-window boundaries, row limits, aggregates, and calculations. Targets, inputs, columns, calculation IDs, and item structure are preserved; new lock targets, tables, or APIs cannot be added through this path.

All executable acceptance cases require review because changed calculations can affect downstream reads. AI does not edit expectations. The owner records rationale for permitted successful-response value changes. Negative/security checks, response status, inputs/steps, and response fields/row counts cannot be removed or weakened. A new design/source is generated and actually re-verified.

Implementation: [change contracts](../../specton/feedback/contracts.py). Checks: [Gmail calculation changes](../../tests/integration/test_feedback_calculations.py), [multi-domain changes](../../tests/integration/test_feedback_contract_docker.py).

---

[Documentation](README.md) · [Project](../../README.en.md)
