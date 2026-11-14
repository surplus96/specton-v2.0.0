"""Google 로그인 단계에서 명세 스키마로 이전할 때 사용자·프로젝트를 보존한다."""

from uuid import uuid4

import pytest

from specton.persistence.db import apply_schema
from specton.persistence.migrate import current_version
from specton.persistence.migrations import HEAD, SchemaVersionError

pytestmark = pytest.mark.db


def test_identity_upgrade_keeps_account_and_project(pool):
    user, project = uuid4(), uuid4()
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO app_user(id,google_subject,email) VALUES(%s,'google','a@example.com')",
            (user,),
        )
        conn.execute(
            "INSERT INTO project(id,owner_id,name) VALUES(%s,%s,'preserved')", (project, user)
        )
        conn.execute(
            "DROP TABLE implementation_adoption,"
            "implementation_preview,implementation_verification,implementation_source,"
            "spec_approval,spec_object,spec_revision,spec_document"
        )
        conn.execute("UPDATE alembic_version SET version_num='0002_identity'")
    apply_schema(pool)
    assert current_version(pool) == HEAD
    with pool.connection() as conn:
        assert conn.execute(
            "SELECT owner_id,name FROM project WHERE id=%s", (project,)
        ).fetchone() == {"owner_id": user, "name": "preserved"}
        assert (
            conn.execute("SELECT google_subject FROM app_user WHERE id=%s", (user,)).fetchone()[
                "google_subject"
            ]
            == "google"
        )


@pytest.mark.parametrize(
    "change",
    [
        "ALTER TABLE spec_revision DROP CONSTRAINT spec_revision_spec_id_fkey",
        "ALTER TABLE spec_object ENABLE ROW LEVEL SECURITY",
    ],
)
def test_specification_schema_drift_is_rejected(pool, change):
    with pool.connection() as conn:
        conn.execute(change.encode())
    with pytest.raises(SchemaVersionError):
        apply_schema(pool)
    assert current_version(pool) == HEAD
