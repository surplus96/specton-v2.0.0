"""0002_identity의 동결된 SQL과 검증용 표 목록."""

TABLES = frozenset(
    {"app_user", "login_session", "oauth_attempt", "project", "project_run", "design_baseline"}
)
SQL = """
    CREATE TABLE app_user (
        id uuid PRIMARY KEY, google_subject text UNIQUE NOT NULL, email text NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE login_session (
        token_hash text PRIMARY KEY, user_id uuid NOT NULL REFERENCES app_user,
        csrf_hash text NOT NULL, expires_at timestamptz NOT NULL
    );
    CREATE TABLE oauth_attempt (
        state_hash text PRIMARY KEY, browser_hash text NOT NULL, nonce text NOT NULL,
        verifier text NOT NULL, expires_at timestamptz NOT NULL
    );
    CREATE TABLE project (
        id uuid PRIMARY KEY, owner_id uuid NOT NULL REFERENCES app_user,
        name text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX project_owner ON project(owner_id, created_at DESC, id);
    CREATE TABLE project_run (
        run_id uuid PRIMARY KEY REFERENCES run, project_id uuid NOT NULL REFERENCES project
    );
    CREATE TABLE design_baseline (
        id uuid PRIMARY KEY, project_id uuid NOT NULL REFERENCES project,
        run_id uuid NOT NULL REFERENCES run, revision integer NOT NULL,
        approval_id uuid NOT NULL REFERENCES approval, model_hash text NOT NULL,
        version integer NOT NULL CHECK(version > 0),
        artifact_hashes jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE(project_id,run_id,revision), UNIQUE(project_id,version)
    );
    """
