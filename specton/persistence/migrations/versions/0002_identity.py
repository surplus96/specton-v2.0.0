"""지속 사용자·로그인 세션·프로젝트·승인 기준 버전."""

from alembic import op

from specton.persistence.migrations import SchemaVersionError
from specton.persistence.migrations.identity_schema import SQL

revision = "0002_identity"
down_revision = "0001_platform"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise SchemaVersionError("사용자·프로젝트 데이터를 삭제하지 않습니다. 백업 복구를 사용하세요.")
