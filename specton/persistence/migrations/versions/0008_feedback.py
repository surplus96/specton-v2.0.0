"""Gmail collection and approved feedback implementation."""

from alembic import op

from specton.persistence.migrations import SchemaVersionError
from specton.persistence.migrations.feedback_schema import SQL

revision = "0008_feedback"
down_revision = "0007_adoption"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise SchemaVersionError("고객 피드백 이력을 삭제하지 않습니다. 백업 복구를 사용하세요.")
