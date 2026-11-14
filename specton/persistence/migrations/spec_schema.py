"""0003_specification의 동결 SQL."""

TABLES = frozenset({"spec_document", "spec_revision", "spec_approval", "spec_object"})
SQL = """
CREATE TABLE spec_document (
    id uuid PRIMARY KEY, baseline_id uuid UNIQUE NOT NULL REFERENCES design_baseline,
    current_version integer NOT NULL CHECK(current_version > 0)
);
CREATE TABLE spec_revision (
    spec_id uuid NOT NULL REFERENCES spec_document, version integer NOT NULL CHECK(version > 0),
    payload jsonb NOT NULL, spec_hash text NOT NULL,
    created_by uuid NOT NULL REFERENCES app_user, created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(spec_id,version), UNIQUE(spec_id,spec_hash)
);
CREATE TABLE spec_approval (
    spec_id uuid NOT NULL, version integer NOT NULL, spec_hash text NOT NULL,
    actor_id uuid NOT NULL REFERENCES app_user, created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(spec_id,version),
    FOREIGN KEY(spec_id,version) REFERENCES spec_revision(spec_id,version)
);
CREATE TABLE spec_object (
    spec_id uuid NOT NULL REFERENCES spec_document, stable_id text NOT NULL, kind text NOT NULL,
    source_key text, retired_version integer,
    PRIMARY KEY(spec_id,stable_id)
);
"""
