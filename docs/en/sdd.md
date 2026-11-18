# From approved design to an executable application

[![한국어](../assets/lang-ko.svg)](../ko/sdd.md) [![English](../assets/lang-en.svg)](../en/sdd.md)

## Inputs and generation scope

SDD means Spec-Driven Development. Specton connects approved function specifications, ERDs, DDL, RTMs, and design state to a project baseline, then constructs an executable specification. Screens, roles, APIs, storage mappings, business rules, and acceptance expectations require review and approval; design drafts alone do not establish them.

The primary path is **domain-independent contract compilation**. It uses the design's tables, keys, and relationships rather than injecting fixed order, return, or equipment tables. Earlier master-data, inventory, and commerce templates and `templates/legacy/` remain for compatibility with approved packages.

| Contract | Supported behavior |
|---|---|
| Record operations | Create/list/update, composite keys and relationships, explicit transitions |
| Field invariants | Typed comparisons and all/any groups; final-value validation |
| Multi-record commands | Declared lock targets, guards, calculations, writes and returns in one transaction |
| Calculations and aggregates | Decimal precision, rounding, units, empty/division policies, declared filters and bounds |
| Basic UI | Forms, lists, row editing, search, pagination, reference selectors, loading/errors |
| Customer authentication | Separate customer accounts/sessions and API role checks |
| Acceptance cases | Actual API inputs, expected responses, requirement links, normal/boundary/failure cases |

Scheduling, external actions, row ownership, schema-changing data migration, and finished visual design are listed in [supported behavior and constraints](roadmap.md). Pack approval or sentence-level diagnostics do not prove execution readiness.

## Structural derivation and business implementation

The input path uses an actually approved platform design snapshot and its four artifacts. Uploading four arbitrary external design files without an approved baseline is not a supported generation path.

`derive` proposes insert/list/update APIs, screens, and storage bindings from normalized tables, keys, and relationships. Coverage remains `needs_review`; business policies and executable expectations require separate review. Specifications that already contain commands/calculations are refined without overwriting them through structural derivation.

See [business execution contracts](business-contracts.md) for models/operators and the [workflow](workflow.md) for the complete user sequence.

## Executable specification

[SpecBundle](../../specton/contracts/specification.py) defines the types. Current extensions include `spec-v0.9` and the `executable-design-v11` generator. These format versions are separate from a project's specification revision number.

- `baseline`: actual approved design, artifacts, model, and project references.
- `requirements`: included/deferred scope and rationale; unsupported requirements are retained.
- `roles`, `use_cases`, `apis`, `screens`: access, flows, input/output, and screen bindings.
- `entities`, `storage_bindings`, `domain`, `invariants`: storage, operations, commands, calculations, and conditions.
- `questions`: uncertainty to resolve before approval.
- `acceptance_cases`: prose or executable requirement-level cases. Prose remains `not_run` until execution evidence exists.

Users review stable IDs, provenance, assumptions, and expectations in preparation files. `scripts/validate_test_preparation.py` checks saved specs, design state, and preparation files offline; it does not approve or run applications.

## User workflow

1. Connect a finally approved run to the project and open executable specification review.
2. Draft from the approved design; review included/deferred requirements, APIs, screens, and storage.
3. If needed, consent to external processing and request an AI proposal. Review and save it.
4. Complete business rules and normal/boundary/failure expectations; inspect unresolved readiness findings.
5. Approve the current version/hash, then generate or retrieve its source.
6. Request isolated verification and inspect API/browser results for that source.
7. Prepare and open a preview from browser-verified source; exercise the actual UI.
8. Compare candidates, artifact consistency, and unverified items before adoption.

## AI proposal boundaries

AI output is a proposal. Even small-spec completion requires server validation and user approval. Large existing contracts use bounded edits to existing display/explanatory fields plus unanswered questions rather than regenerating the entire JSON document. Executable contracts and acceptance expectations remain on the server. This path does not automatically establish new APIs, commands, or calculations. Protected-field changes and unknown targets are rejected.

## Atomicity, retries, and precision

Commands validate declared rows and conditions before running in one database transaction. An intermediate failure rolls back all writes and request records. Repeating a successful request key returns its stored result; failed requests can be retried with corrected inputs. The compiler checks supported lock, key, and write structures.

Quantities, amounts, and calculations use explicit Decimal policies. Units, scale, rounding, filters, maximum rows, and empty-result behavior need review when ambiguous. Specifications cannot execute arbitrary Python, JavaScript, or SQL.

## Source, design, and evidence consistency

A source ZIP includes the approved spec, original design, regenerated `design/revised/` documents, backend/frontend contracts, file manifests, and installation/operations tools. Verification recompiles contracts and regenerates document bytes from the approved spec. Rewriting a tampered file's hash does not make it valid.

ERD and DDL can correctly remain identical when only display or policy changes. Original approved artifacts stay in history; revised designs belong to new spec versions. Verification, adoption, production deployment, and acceptance of all customer business requirements are separate outcomes.

---

[Documentation](README.md) · [Project](../../README.en.md)
