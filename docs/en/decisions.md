# Design decision rationale

[![한국어](../assets/lang-ko.svg)](../ko/decisions.md) [![English](../assets/lang-en.svg)](../en/decisions.md)

Design rationale for contracts, agents, persistence, and verification boundaries. ADR identifiers connect code references; API schemas and contract models define request/response and execution formats.

| Reference | Topic | Current rationale |
|---|---|---|
| ADR-0001 | Change review | Record purpose, impact, and verification evidence. |
| ADR-0002 | Scope | Distinguish document design, executable apps, and business acceptance. |
| ADR-0003 | Input | Preserve table structure and original locations. |
| ADR-0004 | Document engines | HWP/HWPX tables and WeasyPrint/Mermaid output; PDF input is unsupported. |
| ADR-0005 | Frontend | Use React, custom CSS, and React Flow. |
| ADR-0006 | Unspecified priority | Do not infer Must or exclusion without evidence. |
| ADR-0007 | LLM execution | Configurable models, call/token/time bounds, and structured output. |
| ADR-0008 | Perspective review | Separate combined/parallel strategy from perspective configuration. |
| ADR-0009 | Contracts/packs | Pydantic, OpenAPI, and manifest/lock boundaries. |
| ADR-0010 | Finding severity | Separate importance from automatic fixability. |
| ADR-0011 | Identity/retention | Session, ownership, and source-access boundaries. |
| ADR-0012 | Runner | Checkpoints and DB leases support resume and deduplication. |
| ADR-0013 | Deployment | DB/API/web Compose with same-origin proxying. |
| ADR-0014 | Evaluation | Separate development examples and answers; qualify independence. |
| ADR-0015 | Conditional review | Conditional extraction/analysis review and explicit final approval. |
| ADR-0016 | IDs/keys | Separate stable internal IDs from business keys; do not invent persistence keys. |
| ADR-0017 | Migrations | Use explicit Alembic revisions instead of rewriting baseline SQL. |
| ADR-0018 | Owned projects | Connect Google users, actually approved runs, and project baselines. |
| ADR-0019 | Inventory policy | Legacy inventory profiles also require approved policy, idempotency, and ledger evidence. |
| ADR-0020 | Verification worker | A separate trusted worker validates source and image hashes. |
| ADR-0021 | Preview | Fixed browser verification with owner mediation and expiry. |
| ADR-0022 | Adoption | Record selections bound to comparison, verification, and current-baseline hashes. |
| ADR-0023 | Gmail feedback | Separate read consent, source quotations, and user-approved regeneration. |

## Execution system design principles

Compile design-derived IR rather than hardcoding domain workflows. Commands provide atomic rollback and idempotent results; calculations specify exact values, units, and precision. Review executable acceptance expectations separately from AI proposals. Regenerate revised designs as new spec versions while preserving originals. Customer authentication is separate from platform authentication.

Large-spec AI completion retains protected contracts on the server and merges bounded edits. Data transfer is limited to supported same-schema isolated rehearsals. See [architecture](architecture.md), [SDD](sdd.md), [feedback](gmail-feedback.md), and [deployment](deployment.md).

## Legacy references in frozen material

Comments in pack YAML and fixed fixtures may retain old references to preserve approval hashes. Historical `docs/NN` references map to current guides as follows.

| Old numbers | Current topic |
|---|---|
| 01, 03, 04, 05 | [Architecture, contracts, agents](architecture.md) |
| 02 | [Requirements](requirements.md) |
| 06 | [API](api.md) |
| 07, 12, 20, 23 | [Testing/evaluation](testing.md) |
| 08, 13 | [Development/contract changes](contributing.md) |
| 09 | [Frontend](frontend.md) |
| 10 | [I/O and packs](domain-packs.md) |
| 11 | [Deployment/security](deployment.md) |
| 14 | [Support/constraints](roadmap.md) |

---

[Documentation](README.md) · [Project](../../README.en.md)
