# Supported behavior and constraints

[![한국어](../assets/lang-ko.svg)](../ko/roadmap.md) [![English](../assets/lang-en.svg)](../en/roadmap.md)

This document defines current implementation behavior and execution conditions. See [testing](testing.md) for verification and the [workflow](workflow.md) for usage.

## Support matrix

| Area | Implemented behavior | Conditions and constraints |
|---|---|---|
| Analysis/design | Requirement tables, clarification/review/approval, function specification/ERD/DDL/RTM | Excel/CSV/HWP/HWPX tables; no PDF input/OCR |
| Domain interpretation | Common/inventory/maintenance packs, approved types/keys/relationships | Vocabulary additions do not implement new business operations |
| Specification derivation | Approved-design screen/API/storage bindings, AI completion, readiness/handoff reports | Structural drafts require review; policies and acceptance expectations must be resolved |
| Generic generation | Insert/list/update, transitions, typed field guards | Approved contracts with supported types, keys, and bindings |
| Atomic commands | Multi-record conditions/calculations/writes, full rollback, idempotent responses | One transaction over declared DB targets; no external side effects |
| Calculations/aggregates | Decimal, units, rounding, single-table filters/aggregates/calculations | Explicit null/empty/zero-division/row-limit policies |
| Automated verification | Source integrity, design consistency, SQL/HTTP/executable API acceptance/Chromium | Separate worker/Docker; prose acceptance is not automatically passed |
| Preview/adoption | Owner-isolated preview, comparison/adoption history | Verification evidence and comparison hashes; separate from deployment |
| Gmail changes | API ingestion/deduplication, impact analysis, approved regeneration/retests | Permitted edits to existing screens/roles/fields/commands/calculations; no general schema change |
| Design regeneration | Spec consistency with functions/ERD/DDL/RTM | Original approval retained; unchanged structure can retain ERD/DDL bytes |
| Data transfer | Isolated same-schema transfer and failure-recovery checks | No arbitrary schema/type conversion or production switchover |
| Customer UI/auth | Contract-driven basic screens, customer accounts, server sessions, API roles | Separate from platform Google login; no row ownership/customer SSO/MFA |
| Delivery | Independent source ZIP, file checks, DB initialization/account/operations tools | Customer-environment installation, business, and recovery acceptance required |

## Execution environment boundaries

`compose.deploy.yml` provisions the platform database, API, and web server. Feedback and generated-app verification workers run separately. A local service helper and customer ZIP are provided; production worker orchestration, scaling, observability, and automatic deployment are outside the base Compose configuration.

Generated UI exposes the business contracts through functional screens. Interpreting a separate visual specification to generate branding, layouts, and component design is not included. Scheduled jobs, external-system actions, and tenant-specific row isolation also require additional execution contracts.

## Interpreting states

| State | Meaning |
|---|---|
| Design approved | The user approved that design revision |
| Specification approved | Execution contracts and included/deferred scope approved |
| Verification passed | Evidence from the checks executed against that source |
| Candidate adopted | The candidate is the project implementation baseline |
| Business accepted | Separate confirmation of included customer/operational conditions |

Reports retain executed cases alongside `not_run`, failed, and deferred scope. Automated verification and adoption do not establish complete business acceptance. Assess each customer's support against the approved contracts and actual execution cases.

---

[Documentation](README.md) · [Project](../../README.en.md)
