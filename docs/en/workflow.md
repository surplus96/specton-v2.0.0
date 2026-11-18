# Design, generation, and customer change workflow

[![한국어](../assets/lang-ko.svg)](../ko/workflow.md) [![English](../assets/lang-en.svg)](../en/workflow.md)

Specton tracks an owned project, an approved design, executable specification versions, implementation candidates, and verification results. A customer change creates a new version and candidate; review and adoption update the project baseline.

## 1. Analyze requirements and approve the design

Create a project under **My projects** and submit a requirements document. Analysis uses requirement tables in Excel, CSV, HWP, or HWPX and the selected domain pack. Answer extraction or interpretation questions against the source. Review functions, entities, relationships, and findings before final approval.

Outputs are the function specification, ERD, DDL, and RTM. Approval binds the run ID, revision, design model, and artifact hashes. Linking this approved run to the project establishes the design baseline for the executable specification.

## 2. Derive and review executable contracts

Connect approved tables, columns, keys, and relationships to screens, APIs, and storage bindings. Structural derivation creates insert/list/update drafts and leaves requirement coverage as `needs_review`. This stage does not establish complete business implementation.

Review the following specification sections:

| Area | Review |
|---|---|
| Requirement scope | Included functionality, deferral reasons, source links |
| Roles, APIs, screens | Who invokes each operation and where it appears |
| Business contracts | Transitions, field guards, multi-record changes, calculations and aggregates |
| Acceptance cases | Setup data, call sequence, successful responses, boundary and failure expectations |
| Open questions | Policies that cannot be determined from the source |

AI completion produces reviewable proposals. Readiness and handoff reports separate structural bindings, executable evidence, and remaining acceptance work. Complete the [execution contracts](business-contracts.md), then approve the current version and hash.

## 3. Generate a candidate and run verification

Generate a source ZIP from the approved specification. It includes the database/API/customer UI, account tools, approved specification, original and regenerated designs, and file manifest. Generation alone does not mark verification as passed.

A separate worker checks source/contract consistency and runs isolated PostgreSQL, HTTP, and browser checks. Results are tied to the candidate source hash. Prose-only acceptance conditions remain `not_run`. For a failure, inspect the stage, error, and linked requirement; specification corrections require a new version.

## 4. Preview and adopt the customer application

Prepare an isolated preview from browser-verified source. Inspect the generated domain's records, edits, relationship selectors, commands, and calculation results. Preview access is owner-controlled and expires; it is separate from a production service.

Compare changed files, design/spec consistency, verification results, and unverified requirements. Adoption validates the current baseline and comparison hash, then updates the project's implementation baseline. It does not deploy to production.

## 5. Apply a Gmail change request

For a project with an adopted baseline, configure [Gmail](gmail-feedback.md). Collect messages using the saved search filter, quote the requested change, and run AI impact analysis.

Review existing and proposed values, direct and related impacts, and questions. Command/calculation changes require human review of every executable acceptance case. Approve the reviewed proposal and request implementation/verification to create a new specification version, regenerated design artifacts, and candidate.

After verification and preview, compare and adopt the new candidate. Successful adoption moves the change to `applied`. A failure while creating the specification/source and registering verification rolls back that database transaction; the adopted baseline is retained.

## 6. Deliver the customer application

Use the adopted ZIP and source hash for [installation, account setup, and backup/recovery](deployment.md). The customer app uses its own database and accounts. Isolated same-schema transfer checks are distinct from production migration.

Acceptance covers installation, role access, included business success/failure cases, unverified/deferred requirements, and backup recovery. Maintain automated verification and customer acceptance as separate results.

---

[Documentation](README.md) · [Project](../../README.en.md)
