# Development environment and contract changes

[![한국어](../assets/lang-ko.svg)](../ko/contributing.md) [![English](../assets/lang-en.svg)](../en/contributing.md)

## Local development

Follow [setup](getting-started.md) for services and [testing](testing.md) for checks. Dependencies are locked by `uv.lock` and `frontend/package-lock.json`.

## Related files by change type

| Change | Related implementation and verification |
|---|---|
| API requests/responses | Pydantic models, routes, OpenAPI, frontend API types, contract checks |
| Platform database | New Alembic revision, migration/schema checks, read/write paths |
| Execution contracts/generator | Compiler, runtime/UI templates, package manifest, acceptance/compatibility checks |
| Domain packs | Source/input files, version/provenance/lock, generated files and pack checks |
| Screens | API states/errors, user flows, Vitest/build/browser checks |
| Developer documentation | Paired Korean/English documents and relative links |

Approved hashes and pinned templates form part of version compatibility. Execution changes require new specification/source/verification links. Packs own business vocabulary; contracts and generators own executable operations.

## Regenerate API types

```bash
npm --prefix frontend run gen:api
npm --prefix frontend run check:api
```

Update `docs/api/openapi.json` before generation. Do not edit `frontend/src/api/schema.d.ts` directly. Follow the [API guide](api.md) for contract changes.

## Documentation and change checks

```bash
uv run python scripts/check_docs.py
git diff --check
```

`docs/ko/` and `docs/en/` use matching filenames and cover equivalent functionality. Code or contract changes additionally require relevant unit/integration checks. Change descriptions state behavior, compatibility/data impact, and checks actually executed with their results.

Use `.env.example` for configuration; keep real keys, customer documents, and runtime data in Git-ignored locations. Record architectural choices and constraints in [design decisions](decisions.md).

---

[Documentation](README.md) · [Project](../../README.en.md)
