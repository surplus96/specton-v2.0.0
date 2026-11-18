# Installation and local development

[![한국어](../assets/lang-ko.svg)](../ko/getting-started.md) [![English](../assets/lang-en.svg)](../en/getting-started.md)

## Prerequisites

Use Python 3.12 or 3.13, uv, Node.js 22.13.0+, npm, and PostgreSQL 18 through Docker. Run commands from the repository root and retain `uv.lock` and `frontend/package-lock.json`. Document analysis requires an OpenAI API key and an accessible model. Health checks and tests without external calls can run without a key.

## Install

```bash
cp .env.example .env
uv sync --locked
npm --prefix frontend ci
docker compose up -d --wait db
uv run python -m specton.persistence.migrate upgrade
uv run python -m specton.persistence.migrate check
```

Set `SPECTON_OPENAI_API_KEY` in `.env`. Model defaults and limits are defined in [config.py](../../specton/config.py); override them with models available to your account. Real document analysis incurs API usage charges.

Start the API and web server in separate terminals:

```bash
uv run uvicorn specton.api.main:app --host 127.0.0.1 --port 8000 --reload
```

```bash
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open `http://localhost:5173`. The health endpoint is `http://localhost:8000/health`. Vite proxies API requests through the same origin. Use the same `localhost` hostname in the browser and Google configuration. Resolve any existing PostgreSQL listener on port 5432 before starting the database.

## Sign in and create a design

Projects, executable specifications, and change requests require Google sign-in. Register the login callback in [Google/Gmail setup](gmail-feedback.md) and configure the OAuth client ID and secret in `.env`. Gmail access requires separate consent.

1. Sign in under **My projects** and create a project.
2. Upload the [synthetic inventory CSV](../../examples/requirements/inventory.csv) or [synthetic maintenance CSV](../../examples/requirements/maintenance.csv) under **New task** and select the matching pack.
3. Answer extraction or analysis questions when requested. Review findings and the design before final approval.
4. Download the function specification, ERD, DDL, and RTM. Connect the approved run to the project.
5. To generate an app, review and approve the executable specification and acceptance expectations using the [SDD workflow](sdd.md).

These small synthetic inputs contain no customer documents. AI output can change the questions and resulting design. Uploading a document alone does not complete application generation or business acceptance.

## Enable feedback, verification, and previews

The basic API/web setup does not start a separate verification worker. Prepare the Gmail token encryption key described in [Gmail setup](gmail-feedback.md), then build the following images. These tags are names used by the local helper; they do not restrict generation to inventory.

```bash
docker build -f docker/implementation/Dockerfile -t specton-generated-runtime:inventory-ledger-v1 .
docker build -f docker/browser/Dockerfile -t specton-browser:generated-ui-v1 .
docker pull postgres:18
docker info --format '{{.ID}}'
```

Set `SPECTON_PREVIEW_WORKER_HOST` in `.env` to the Docker daemon ID from the last command. The API and worker must share a Docker host and loopback network. Gracefully stop any API/Vite processes you started manually before using the helper:

```bash
uv run python scripts/feedback_dev.py start
uv run python scripts/feedback_dev.py status
# Stop only processes started by this helper
uv run python scripts/feedback_dev.py stop
```

The helper starts the API, frontend, feedback worker, and verification worker. It refuses occupied ports instead of terminating unrelated processes. Logs and process records stay in ignored `var/feedback-dev/`. Prepare the database, settings, and images first. This is a local development helper, not a production process manager.

## Input and rendering limits

Excel/CSV and requirement tables in HWP/HWPX are supported. PDF upload and OCR are not supported. PDF **output** requires Pango, Korean fonts, WeasyPrint, and Mermaid CLI/Chromium for ERDs. Local PDF output is disabled by default; the [container setup](deployment.md) includes rendering dependencies.

## Troubleshooting

| Symptom | Check |
|---|---|
| Healthy API but failed analysis | API key, model access, limits, network |
| OAuth callback failure | Public origin, both redirect URIs, cookies |
| Database version mismatch | `migrate check`; back up before `migrate upgrade` |
| Queued analysis or verification | Relevant worker and `var/feedback-dev/` logs |
| Disabled preview | Passed browser verification, daemon ID, same host |
| No collected mail | Connection, saved query, actual Gmail matches |

---

[Documentation](README.md) · [Project](../../README.en.md)
