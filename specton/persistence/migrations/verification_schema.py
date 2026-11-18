"""Durable verification requests; active attempts are unique per source."""

TABLES = frozenset({"implementation_verification"})
SQL = """
CREATE TABLE implementation_verification (
    id uuid PRIMARY KEY,
    implementation_id uuid NOT NULL REFERENCES implementation_source,
    requested_by uuid NOT NULL REFERENCES app_user,
    request_key uuid NOT NULL,
    source_hash text NOT NULL, spec_hash text NOT NULL,
    status text NOT NULL DEFAULT 'queued' CHECK(status IN
      ('queued','running','cancelling','recovering','smoke_passed','failed','cancelled')),
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz, finished_at timestamptz,
    lease_token uuid, lease_until timestamptz, deadline timestamptz,
    resource_key uuid NOT NULL UNIQUE,
    runtime_image text, postgres_image text, suite_hash text, executor_host text,
    cancel_requested boolean NOT NULL DEFAULT false,
    report jsonb, report_hash text, error_code text,
    UNIQUE(implementation_id,request_key)
);
CREATE UNIQUE INDEX verification_active ON implementation_verification(implementation_id)
    WHERE status IN ('queued','running','cancelling','recovering');
CREATE INDEX verification_queue ON implementation_verification(created_at)
    WHERE status IN ('queued','running','cancelling','recovering');
"""
