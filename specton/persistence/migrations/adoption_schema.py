"""Append-only implementation baseline decisions; latest sequence is the current baseline."""

TABLES = frozenset({"implementation_adoption"})
SQL = """
CREATE TABLE implementation_adoption (
 id uuid PRIMARY KEY, project_id uuid NOT NULL REFERENCES project,
 sequence integer NOT NULL CHECK(sequence>0), previous_id uuid,
 implementation_id uuid NOT NULL REFERENCES implementation_source,
 verification_id uuid NOT NULL REFERENCES implementation_verification,
 request_key uuid NOT NULL, request_hash text NOT NULL,
 record jsonb NOT NULL, record_hash text NOT NULL,
 created_by uuid NOT NULL REFERENCES app_user,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id), UNIQUE(project_id,sequence), UNIQUE(project_id,request_key),
 FOREIGN KEY(project_id,previous_id) REFERENCES implementation_adoption(project_id,id),
 CHECK((sequence=1 AND previous_id IS NULL) OR (sequence>1 AND previous_id IS NOT NULL))
);
"""
