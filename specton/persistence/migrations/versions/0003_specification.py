"""실행 명세의 불변 수정 이력과 승인."""

from alembic import op

from specton.persistence.migrations import SchemaVersionError
from specton.persistence.migrations.spec_schema import SQL

revision = "0003_specification"
down_revision = "0002_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise SchemaVersionError("실행 명세 이력을 삭제하지 않습니다. 백업 복구를 사용하세요.")
