"""0004_implementation: 코드 묶음 생성 기록. 검증 통과·채택과 구분한다."""

TABLES = frozenset({"implementation_source"})
SQL = """
CREATE TABLE implementation_source (
    id uuid PRIMARY KEY, spec_id uuid NOT NULL, spec_version integer NOT NULL,
    spec_hash text NOT NULL, template_version text NOT NULL,
    source_hash text NOT NULL, source_zip bytea NOT NULL,
    created_by uuid NOT NULL REFERENCES app_user,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY(spec_id,spec_version) REFERENCES spec_approval(spec_id,version),
    UNIQUE(spec_id,spec_version,template_version)
);
"""
