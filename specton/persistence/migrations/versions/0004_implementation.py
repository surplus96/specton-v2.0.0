"""승인 명세에 묶인 생성 소스."""

from alembic import op

from specton.persistence.migrations import SchemaVersionError
from specton.persistence.migrations.implementation_schema import SQL

revision = "0004_implementation"
down_revision = "0003_specification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise SchemaVersionError("생성 이력을 삭제하지 않습니다. 백업 복구를 사용하세요.")
