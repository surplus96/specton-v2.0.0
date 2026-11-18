# API contracts and versions

[![한국어](../assets/lang-ko.svg)](../ko/api.md) [![English](../assets/lang-en.svg)](../en/api.md)

The machine-readable contract is [OpenAPI](../api/openapi.json); implementations live in [API modules](../../specton/api/). This guide describes route groups and invariants rather than duplicating request/response fields. Local FastAPI `/docs` exposes detailed types.

| Route group | Purpose |
|---|---|
| `/health` | Server health |
| `/runs`, `/runs/{id}` | Create/list/inspect document runs |
| `/runs/{id}/events`, `/view`, `/resume`, `/cancel` | SSE, view data, human review/resume, cancellation |
| `/runs/{id}/artifacts/{kind}` | Revision-specific design artifacts |
| `/api/v1/auth/*` | Google login, current user, logout |
| `/api/v1/projects`, `/baselines/*` | Owned projects, run links, approved baselines |
| `/api/v1/specs/{spec_id}/*` | Spec versions, completion, derivation, approval, design, readiness |
| `/api/v1/implementations/{impl_id}/*` | Source archives, verification jobs, previews |
| `/api/v1/previews/{preview_id}/*` | Owner-mediated preview documents/RPC/closure |
| `/api/v1/projects/{project_id}/candidates`, `/adoptions` | Comparison, evidence, adoption |
| `/api/v1/integrations/gmail/*` | Separate consent, connection, scope, synchronization |
| `/api/v1/feedback`, `/feedback-jobs`, `/changes/*` | Mail, jobs, change proposals, review, regeneration |
| `/api/v1/packs`, `/capabilities` | Available packs and supported capabilities |

Shortened subpaths in the table are group descriptions, not literal concatenation rules. Consult OpenAPI for exact methods and paths.

## SDD and change-processing endpoints

| Method | Path | Behavior |
|---|---|---|
| `POST` | `/api/v1/projects/{project_id}/baselines` | Link an approved run as the design baseline |
| `POST` | `/api/v1/baselines/{baseline_id}/specs` | Create an executable specification |
| `POST` | `/api/v1/specs/{spec_id}/derive` | Derive screen/API/storage bindings |
| `POST` | `/api/v1/specs/{spec_id}/complete` | Propose AI specification completion |
| `GET` | `/api/v1/specs/{spec_id}/handoff` | Read handoff readiness and execution evidence |
| `POST` | `/api/v1/specs/{spec_id}/approve` | Approve the current specification |
| `GET` | `/api/v1/specs/{spec_id}/design` | Retrieve regenerated design |
| `POST` | `/api/v1/specs/{spec_id}/implementations` | Generate source from an approved specification |
| `POST` | `/api/v1/implementations/{impl_id}/verifications` | Request isolated verification |
| `POST` | `/api/v1/implementations/{impl_id}/previews` | Request a preview of verified source |
| `GET` | `/api/v1/projects/{project_id}/candidates/{candidate_id}/comparison` | Compare a candidate with the baseline |
| `POST` | `/api/v1/projects/{project_id}/adoptions` | Adopt a reviewed candidate |
| `POST` | `/api/v1/feedback/{message_id}/changes` | Create a change from a message |
| `POST` | `/api/v1/changes/{change_id}/analyse` | Analyze change impact |
| `PUT` | `/api/v1/changes/{change_id}/proposal` | Save reviewed changes and expectations |
| `POST` | `/api/v1/changes/{change_id}/decide` | Approve or reject a proposal |
| `POST` | `/api/v1/changes/{change_id}/implement` | Generate and verify an approved change |

## Authentication, concurrency, and errors

The platform uses session cookies and `X-CSRF-Token` for mutations. Projects, specs, messages, and candidates enforce ownership. Legacy anonymous runs and signed-in project access have distinct boundaries; knowing a run ID does not grant ownership.

Edits and approvals check current versions/content hashes. Idempotent commands use request keys. Authentication requirements, denied access, invalid input, stale versions/hashes, and pending verification remain distinguishable. Clients must not turn failures into empty successful responses.

SSE supports reconnecting with event identity. Questions and final approval follow the current run revision's resume contract. Cancellation/retry cannot reuse a different revision's results as success evidence.

## Updating a contract

1. Inspect Pydantic, route, and persistence-migration impact.
2. Update the relevant `docs/api/openapi.json` contract while preserving manual SSE, error, and shared-parameter definitions.
3. Regenerate types with `npm --prefix frontend run gen:api`.
4. Run `npm --prefix frontend run check:api` and Python contract/schema tests.

Do not overwrite hashes of approved specs, packs, or artifacts as a compatibility shortcut. Spec format, project spec version, design revision, and platform database revision are separate version axes.

---

[Documentation](README.md) · [Project](../../README.en.md)
