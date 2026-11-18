# Deployment, security, and customer delivery

[![한국어](../assets/lang-ko.svg)](../ko/deployment.md) [![English](../assets/lang-en.svg)](../en/deployment.md)

## Platform configurations

The local HTTP override requires Docker Compose 2.24.4 or later. `compose.local.yml` replaces production port bindings with ports `80`, `5194`, and `5196` on `127.0.0.1` only; it does not expose production port `443`.

`docker-compose.yml` provides the development DB. `compose.deploy.yml` includes DB, API, web, and migration tooling; `compose.local.yml` overrides local HTTP behavior. Deployment images include PDF renderers. **The deployment Compose file does not automatically provision feedback or generated-app verification workers.** Follow [local setup](getting-started.md) for the tested complete SDD/Gmail development flow. Production worker hosting, Docker/network boundaries, and secrets need separate deployment design.

```bash
cp .env.deploy.example .env.deploy
# Set real secrets, public origin, and image tags in the local file first.
# Include compose.local.yml when testing over local HTTP.

docker compose -f compose.deploy.yml --env-file .env.deploy build
docker compose -f compose.deploy.yml --env-file .env.deploy up -d --wait db
docker compose -f compose.deploy.yml --env-file .env.deploy run --rm migrate
docker compose -f compose.deploy.yml --env-file .env.deploy up -d --no-build api web
```

Retain and deploy the tested image digests. HTTPS origins require Secure session cookies; disable them only for local HTTP. API/DB services remain internal while Caddy serves the web/API through one origin. `docker compose down -v` removes database/file volumes and is not a routine restart command.

The API image pins its ERD renderer in `docker/api/mermaid-package.json` and `mermaid-package-lock.json`. It declares CLI, Mermaid, and Puppeteer versions and installs official npm packages from the lockfile. After an update, run `docker build --target check .` to verify real PDF and ERD rendering, and keep Mermaid aligned with the frontend. See [dependency security](dependency-security.md) for remaining advisories and exposure boundaries.

## Data, secrets, and execution boundaries

- Do not commit real `.env*` secrets, customer uploads, Gmail tokens/bodies, sessions, logs, or database dumps. Include only example environment files.
- Separate platform and SQL-sandbox databases/accounts. Validate DDL through allowed ASTs, restricted permissions, timeouts, and rollback.
- A separate worker tests generated apps using pinned images and restricted containers, networking, and resources. Generated app containers do not receive the Docker socket.
- Previews use an owner-checked expiring proxy. Do not use production data.
- Documents, email, and model output are untrusted data, not directly evaluated code.

## Platform database changes

Add new Alembic revisions and run `upgrade`/`check`. Do not rewrite existing revisions or use `stamp` to conceal a mismatch. Verify migrations against a backup copy first; retain a recovery path using the previous image and backup. Downgrades do not always preserve data.

## Delivery package layout

| Path | Contents |
|---|---|
| `spec/` | Approved specification and baseline design snapshot |
| `design/` | Original approved functions/ERD/DDL/RTM |
| `design/revised/` | Current executable design and traceability |
| `backend/`, `frontend/` | Runtime contracts, server, and customer UI |
| `delivery.json`, `build-manifest.json` | Scope, roles, file hashes, template version |
| `verify_delivery.py`, `backend/manage.py` | Integrity, DB initialization, accounts |
| `OPERATIONS.md`, `ATOMIC_COMMANDS.md`, `CALCULATIONS.md` | Operations, command, and calculation guides |

## Install a generated customer app

The source ZIP is independent of the platform. `design/` preserves the approved original and `design/revised/` contains executable design documents. Check the source SHA-256 against its origin, then run `verify_delivery.py`. Prepare an empty database and restricted account separate from the platform.

```bash
# Inside the extracted generated ZIP
python -m venv .venv
.venv/bin/pip install --require-hashes -r backend/requirements.txt
npm --prefix frontend ci --ignore-scripts --no-audit --no-fund
npm --prefix frontend run build
.venv/bin/python backend/manage.py init-db
.venv/bin/python backend/manage.py roles
.venv/bin/python backend/manage.py set-user operator --role ROLE_FROM_APPROVED_SPEC
.venv/bin/uvicorn serve:app --app-dir backend --host 127.0.0.1 --port 8080 --no-access-log
```

Inject DB/origin settings from the package's `.env.example` into the process environment first; customer tooling does not automatically load that file. Use a real approved role ID with `set-user`; enter passwords interactively. There is no default account or public signup. Customer accounts are separate from Google/Gmail accounts.

Generated `OPERATIONS.md`, `ATOMIC_COMMANDS.md`, and `CALCULATIONS.md` belong to the template's delivery contract. Preserve versioned template bytes for old-package verification. Bilingual repository development guides are separate from generated-ZIP document languages and product UI localization.

## Backup, transfer, and acceptance

Use `pg_dump` and `pg_restore --single-transaction` into a separate empty database to test recovery of the same app/schema. Revoke restored sessions and verify login, roles, row counts, and important values. Backups contain account hashes and require restricted access.

`specton/implementation/data_transfer.py` is a same-schema isolated transfer-rehearsal module. It does not automatically migrate arbitrary schema/type changes, production databases containing authentication tables, or switch services. Adoption is not deployment. Delivery requires separate installation, identity, permission, business, failure/recovery, and environment acceptance.

---

[Documentation](README.md) · [Project](../../README.en.md)
