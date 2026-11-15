"""Gmail connections, durable work, quoted feedback and immutable review events."""

TABLES = frozenset(
    {
        "gmail_oauth",
        "gmail_connection",
        "feedback_message",
        "feedback_change",
        "feedback_job",
        "feedback_event",
        "feedback_revision",
    }
)
SQL = """
CREATE TABLE gmail_oauth (
 state_hash text PRIMARY KEY, owner_id uuid NOT NULL REFERENCES app_user,
 session_hash text NOT NULL, nonce text NOT NULL, verifier text NOT NULL,
 expires_at timestamptz NOT NULL, consumed boolean NOT NULL DEFAULT false
);
CREATE TABLE gmail_connection (
 id uuid PRIMARY KEY, owner_id uuid NOT NULL UNIQUE REFERENCES app_user,
 google_subject text NOT NULL, email text NOT NULL,
 state text NOT NULL CHECK(state IN ('active','reauth_required','disconnected')),
 encrypted_token text, generation integer NOT NULL DEFAULT 1 CHECK(generation>0),
 query text NOT NULL DEFAULT 'newer_than:30d', automatic boolean NOT NULL DEFAULT false,
 history_id text, last_sync_at timestamptz, next_sync_at timestamptz NOT NULL DEFAULT now(),
 error_code text, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE feedback_message (
 id uuid PRIMARY KEY, connection_id uuid NOT NULL REFERENCES gmail_connection,
 gmail_id text NOT NULL, thread_id text NOT NULL, subject text NOT NULL,
 sender text NOT NULL, received_at timestamptz NOT NULL, body text NOT NULL,
 content_hash text NOT NULL, attachments jsonb NOT NULL, deleted_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(connection_id,gmail_id)
);
CREATE TABLE feedback_change (
 id uuid PRIMARY KEY, project_id uuid NOT NULL REFERENCES project,
 message_id uuid NOT NULL REFERENCES feedback_message,
 request_key uuid NOT NULL, request_hash text NOT NULL, title text NOT NULL,
 quote text NOT NULL, instruction text NOT NULL,
 state text NOT NULL CHECK(state IN (
 'received','analysing','needs_input','awaiting_decision','approved',
 'validating','applied','rejected','failed')),
 version integer NOT NULL DEFAULT 1 CHECK(version>0),
 base_adoption_id uuid NOT NULL REFERENCES implementation_adoption,
 spec_id uuid NOT NULL REFERENCES spec_document, spec_version integer NOT NULL,
 spec_hash text NOT NULL, analysis jsonb, proposal jsonb, proposal_hash text,
 approved_hash text, implementation_id uuid REFERENCES implementation_source,
 verification_id uuid REFERENCES implementation_verification,
 created_by uuid NOT NULL REFERENCES app_user, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,request_key), UNIQUE(implementation_id)
);
CREATE TABLE feedback_job (
 id uuid PRIMARY KEY, owner_id uuid NOT NULL REFERENCES app_user,
 kind text NOT NULL CHECK(kind IN ('sync','analyse')),
 connection_id uuid REFERENCES gmail_connection, change_id uuid REFERENCES feedback_change,
 generation integer NOT NULL,
 state text NOT NULL CHECK(state IN ('queued','running','succeeded','failed','cancelled')),
 attempt integer NOT NULL DEFAULT 0, lease_token uuid, lease_until timestamptz,
 next_at timestamptz NOT NULL DEFAULT now(), error_code text,
 result jsonb, created_at timestamptz NOT NULL DEFAULT now(),
 CHECK((kind='sync' AND connection_id IS NOT NULL AND change_id IS NULL)
 OR (kind='analyse' AND change_id IS NOT NULL AND connection_id IS NULL))
);
CREATE UNIQUE INDEX feedback_sync_active ON feedback_job(connection_id)
 WHERE kind='sync' AND state IN ('queued','running');
CREATE UNIQUE INDEX feedback_analysis_active ON feedback_job(change_id)
 WHERE kind='analyse' AND state IN ('queued','running');
CREATE INDEX feedback_queue ON feedback_job(next_at,created_at) WHERE state='queued';
CREATE TABLE feedback_event (
 id uuid PRIMARY KEY, change_id uuid NOT NULL REFERENCES feedback_change,
 actor_id uuid NOT NULL REFERENCES app_user, action text NOT NULL,
 target_hash text, note text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
"""

SQL += """
CREATE TABLE feedback_revision (
 change_id uuid NOT NULL REFERENCES feedback_change, version integer NOT NULL CHECK(version>0),
 payload jsonb NOT NULL, payload_hash text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(change_id,version)
);
"""
