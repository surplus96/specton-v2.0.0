"""Immutable implementation adoption history."""

from alembic import op

from specton.persistence.migrations import SchemaVersionError
from specton.persistence.migrations.adoption_schema import SQL

revision = "0007_adoption"
down_revision = "0006_preview"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise SchemaVersionError("채택 이력을 삭제하지 않습니다. 백업 복구를 사용하세요.")
