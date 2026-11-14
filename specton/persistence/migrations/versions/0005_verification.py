"""Durable isolated verification queue."""

from alembic import op

from specton.persistence.migrations import SchemaVersionError
from specton.persistence.migrations.verification_schema import SQL

revision = "0005_verification"
down_revision = "0004_implementation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise SchemaVersionError("검증 이력을 삭제하지 않습니다. 백업 복구를 사용하세요.")
