# Google sign-in and Gmail change requests

[![한국어](../assets/lang-ko.svg)](../ko/gmail-feedback.md) [![English](../assets/lang-en.svg)](../en/gmail-feedback.md)

## OAuth configuration

Google sign-in identifies platform users and project ownership. Gmail requests separate read access. Both features use one web OAuth client, but **both callbacks must be registered**.

| Google Cloud field | Local value |
|---|---|
| Authorized JavaScript origin | `http://localhost:5173` |
| Sign-in redirect URI | `http://localhost:5173/api/v1/auth/google/callback` |
| Gmail redirect URI | `http://localhost:5173/api/v1/integrations/gmail/callback` |

Do not put a path or trailing `/` in the JavaScript origin. The Gmail callback does not replace the login callback. Configure the consent screen/test users and enable the Gmail API. For deployment, use an HTTPS origin and matching callbacks.

Configure `SPECTON_PUBLIC_ORIGIN`, `SPECTON_GOOGLE_CLIENT_ID`, and `SPECTON_GOOGLE_CLIENT_SECRET` using `.env.example`. Generate a Gmail token encryption key once and keep it in secret configuration:

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set the result as `SPECTON_GMAIL_TOKEN_KEY`. Retain it across restarts; changing it requires reconnecting existing accounts. Set `SPECTON_FEEDBACK_ANALYSIS_ENABLED=true` only when enabling AI analysis. A daily limit and per-request external-processing consent also apply.

## Connect and collect

1. Sign in, open **Customer mail**, and grant read access through **Connect Gmail**.
2. Enter a narrow test query, such as `subject:Specton-demo newer_than:7d -in:drafts`.
3. Save the collection scope and choose whether to synchronize periodically.
4. Send a synthetic request to the connected address and select **Sync now**.
5. Once the job completes, refresh the inbox and inspect subject, sender, and body.
6. Synchronize again and verify that the same Gmail message is not duplicated.

The query filters ingestion within the app; it does not limit Google's permission to particular messages. A successful connection or sync does not imply matching mail exists. If the list is empty, check the same query in Gmail and inspect spam/trash. Specton does not send, delete, or mark mail as read. Collection and analysis are separate jobs.

## Apply an approved change

The project needs an approved spec and an adopted implementation baseline.

1. Open collected mail, choose the project, and quote the request verbatim when registering a change.
2. Consent to the external AI payload and request impact analysis.
3. Review the summary, direct/related targets, unsupported items, and questions. Saving new answers invalidates prior approval evidence and requires renewed analysis/review.
4. Compare existing values with proposals and save the reviewed changes.
5. Enter a rationale and acknowledgement, then approve the change proposal.
6. Generate and request verification of the approved change. This step creates the new spec version and candidate.
7. Inspect automated verification and the isolated UI, then compare against the existing candidate.
8. Review spec/design/source consistency, changed files, and unverified business items before adoption. Confirm **Applied** and the audit history.

Proposal approval and candidate generation are distinct. Failure to create/register verification rolls back the new spec/source transaction; retry using the approved proposal. Duplicate requests and stale baselines/hashes are checked.

## Allowed contract changes

Supported changes include existing screen names/text, permitted role/requirement fields, and bounded policy edits to existing commands/calculations. This is not an automatic path for adding tables, APIs, inputs, lock targets, or write structures.

Changing a command/calculation policy requires human review of **every executable acceptance case**. AI does not change expectations. Permitted successful-response expectation edits are saved with per-step rationale; failed checks, inputs, permissions, or trace links cannot be removed or weakened to obtain a pass. Failed re-verification provides no adoption evidence.

## Revised artifacts and verification evidence

| Target | Change handling |
|---|---|
| Approval baseline | Preserve original design and specification history |
| Executable specification | Bind reviewed changes and approval evidence to a new version |
| Design documents | Generate functions/ERD/DDL/RTM and the executable spec under `design/revised/` |
| Implementation source | Recompile backend/frontend contracts from the new specification |
| Verification | Check design consistency, APIs, and browser behavior against the new source hash |
| Implementation baseline | Successful comparison/adoption marks the request applied |

ERD/DDL can remain unchanged when a screen name or calculation policy leaves storage unchanged. See [business execution contracts](business-contracts.md) for supported edits and expectation review. Same-schema transfer/failure-recovery checks are a separate [delivery procedure](deployment.md); adopting a Gmail candidate does not migrate production data.

## State and operations

A representative flow is `received → analysing → needs_input / awaiting_decision → approved → validating → reviewable → applied`. Consult the [feedback API](../../specton/api/feedback.py) for exact transitions. Analysis/verification failures remain distinct from successful completion; the UI supports refresh and retry.

Tokens are encrypted at rest. Disconnecting Gmail stops collection. OAuth state, refresh tokens, daily limits, and job leases are managed by [integrations](../../specton/integrations/) and the [worker](../../specton/feedback/worker.py). Email instructions do not automatically authorize tool execution or external disclosure.

---

[Documentation](README.md) · [Project](../../README.en.md)
