"""Browser evidence and isolated preview lifecycle."""

from alembic import op

from specton.persistence.migrations import SchemaVersionError
from specton.persistence.migrations.preview_schema import BROWSER_SQL, SQL

revision = "0006_preview"
down_revision = "0005_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(BROWSER_SQL)
    op.execute(SQL)


def downgrade() -> None:
    raise SchemaVersionError("검증·미리보기 이력을 삭제하지 않습니다. 백업 복구를 사용하세요.")
