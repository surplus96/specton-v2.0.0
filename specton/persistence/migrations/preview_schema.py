"""Browser evidence binding and expiring preview resources."""

TABLES = frozenset({"implementation_preview"})
BROWSER_SQL = """
ALTER TABLE implementation_verification ADD COLUMN browser_image text;
ALTER TABLE implementation_verification ADD COLUMN browser_suite_hash text;
"""
SQL = """
CREATE TABLE implementation_preview (
 id uuid PRIMARY KEY, implementation_id uuid NOT NULL REFERENCES implementation_source,
 verification_id uuid NOT NULL REFERENCES implementation_verification,
 requested_by uuid NOT NULL REFERENCES app_user, request_key uuid NOT NULL,
 source_hash text NOT NULL, resource_key uuid NOT NULL UNIQUE,
 status text NOT NULL DEFAULT 'queued' CHECK(status IN
 ('queued','starting','ready','closing','recovering','closed','failed')),
 created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL,
 lease_token uuid, lease_until timestamptz, deadline timestamptz, executor_host text,
 cancel_requested boolean NOT NULL DEFAULT false,
 app_port integer CHECK(app_port BETWEEN 1024 AND 65535), access_token text,
 html text, html_hash text, error_code text,
 UNIQUE(implementation_id,request_key)
);
CREATE UNIQUE INDEX preview_active ON implementation_preview(implementation_id)
 WHERE status IN ('queued','starting','ready','closing','recovering');
"""
