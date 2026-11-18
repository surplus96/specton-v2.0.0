# Capabilities and implementation traceability

[![한국어](../assets/lang-ko.svg)](../ko/requirements.md) [![English](../assets/lang-en.svg)](../en/requirements.md)

`REQ-01`–`REQ-27` identify platform requirements, not the per-run IDs generated from customer documents. This table maps current scope to implementation; it is not a report that every requirement passed business acceptance.

| ID | Feature | Contract/scope | Implementation |
|---|---|---|---|
| REQ-01 | Excel/CSV tables | Preserve source IDs, columns, sheets and rows | [Code](../../specton/ingest/) |
| REQ-02 | PDF input/OCR | Unsupported; uploads rejected | [Code](../../specton/ingest/) |
| REQ-03 | Pack selection | Approval, schema and hash checks | [Code](../../specton/packs/) |
| REQ-04 | Requirement analysis | FR/NFR, splitting, clarification | [Code](../../specton/nodes/a01_requirements.py) |
| REQ-05 | Human review | Keep/edit/split with revision-aware resume | [Code](../../specton/graph.py) |
| REQ-06 | Function design | Requirement links and priority evidence | [Code](../../specton/nodes/) |
| REQ-07 | Entities/attributes/CRUD | Valid references and source evidence | [Code](../../specton/nodes/a03_entities.py) |
| REQ-08 | Relationships | Direction, cardinality and optionality | [Code](../../specton/nodes/) |
| REQ-09 | Normalization | Code-derived IDs, names, N:M and FKs | [Code](../../specton/codegen/) |
| REQ-10 | ERD | Mermaid from a frozen model | [Code](../../specton/codegen/) |
| REQ-11 | DDL | Parsing, allowed syntax, isolated execution/rollback | [Code](../../specton/validate/) |
| REQ-12 | RTM | Requirement-function-entity/relationship joins | [Code](../../specton/codegen/rtm.py) |
| REQ-13 | Rule checks | References, names, keys, CRUD and DDL | [Code](../../specton/review/) |
| REQ-14 | Perspective reviews | A05–A08, combined/parallel modes | [Code](../../specton/review/) |
| REQ-15 | Finding validation/merge | Target/quote checks and fingerprints | [Code](../../specton/review/) |
| REQ-16 | Rework | Deterministic routing, conditional A09 and limits | [Code](../../specton/graph.py) |
| REQ-17 | Final approval | Blocking findings, SQL results and approval evidence | [Code](../../specton/api/) |
| REQ-18 | Exports | Four artifacts and optional PDF | [Code](../../specton/export/) |
| REQ-19 | Web UI | Progress, review, results and workspace | [Code](../../specton/api/) |
| REQ-20 | History/resume | Checkpoints, leases and version preservation | [Code](../../specton/persistence/) |
| REQ-21 | Trace integrity | Existing requirement IDs and provenance | [Code](../../specton/contracts/) |
| REQ-22 | Output/error handling | Structured validation and bounded retries | [Code](../../specton/llm/) |
| REQ-23 | Protection boundaries | Ownership, secrets, file and SQL scope | [Code](../../specton/api/) |
| REQ-24 | Reproducibility | Input, pack, model, code and report hashes | [Code](../../specton/evaluation/) |
| REQ-25 | Resources/cancellation | Upload, source-block, time and token limits | [Code](../../specton/runner.py) |
| REQ-26 | Pack/code separation | Shared domain-independent pipeline | [Code](../../specton/packs/) |
| REQ-27 | HWP/HWPX | Supported requirement tables and source positions | [Code](../../specton/ingest/) |

## Specification-driven generation, verification, and changes

| ID | Requirement | Guide |
|---|---|---|
| SDD-01 | Owned projects linked to actual approved designs | [Architecture](architecture.md) |
| SDD-02 | Spec drafting, questions, scope and approval | [SDD](sdd.md) |
| SDD-03 | Domain-driven DB/API/basic UI/customer identity | [SDD](sdd.md) |
| SDD-04 | Actual API acceptance, browser checks and previews | [Testing](testing.md) |
| SDD-05 | Adoption bound to comparison hashes and evidence | [API](api.md) |
| FB-01 | Separate Gmail consent, read ingestion and deduplication | [Gmail](gmail-feedback.md) |
| FB-02 | Source quotes, impact analysis, approved changes and rechecks | [Gmail](gmail-feedback.md) |
| OPS-01 | Delivery ZIP, separate customer login and backup/recovery | [Delivery](deployment.md) |

### Execution engine and delivery implementation references

These paths connect behavior to its implementation and reproducible checks. Test presence does not assert a pass in the current environment.

| ID | Capability | Implementation | Check |
|---|---|---|---|
| SDD-06 | Generic multi-record commands, full rollback, idempotency | [Code](../../specton/implementation/commands.py) | [Test](../../tests/integration/test_atomic_commands.py) |
| SDD-07 | Calculations/aggregates with units and precision policies | [Code](../../specton/implementation/calculations.py) | [Test](../../tests/unit/test_calculation_contract.py) |
| SDD-08 | Requirement-level executable acceptance and unexecuted cases | [Code](../../specton/implementation/requirement_results.py) | [Test](../../tests/unit/test_requirement_results.py) |
| SDD-09 | Regenerated functions/ERD/DDL/RTM and spec consistency | [Code](../../specton/specification/documents.py) | [Test](../../tests/unit/test_change_consistency.py) |
| SDD-10 | Specification, business contract, and handoff readiness | [Code](../../specton/specification/handoff.py) | [Test](../../tests/unit/test_handoff_readiness.py) |
| FB-03 | Existing command/calculation policy changes through Gmail | [Code](../../specton/feedback/contracts.py) | [Test](../../tests/integration/test_feedback_calculations.py) |
| OPS-02 | Same-schema transfer and mid-transfer rollback | [Code](../../specton/implementation/data_transfer.py) | [Test](../../tests/integration/test_data_transfer.py) |
| OPS-03 | Customer login, accounts, and delivery package checks | [Code](../../specton/implementation/delivery.py) | [Test](../../tests/integration/test_customer_delivery.py) |

## Shared acceptance principles

Do not turn omitted input, extraction errors, or failed reviews into success. Do not finalize unstated priorities or business policies. Reject stale answers/approval hashes and reproduce approved artifacts for the same version. Distinguish technical verification from business acceptance and retain deferral rationale. Actual tests live in `tests/unit/`, `tests/integration/`, and `tests/browser/`; see [testing](testing.md).

---

[Documentation](README.md) · [Project](../../README.en.md)
