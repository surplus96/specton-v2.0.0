"""기존 플랫폼 스키마의 검증된 기준 버전. 원본 SQL은 동결한다."""

from alembic import op

from specton.persistence.migrations import SchemaVersionError
from specton.persistence.migrations.baseline import install_baseline

revision = "0001_platform"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    install_baseline(op.get_bind())


def downgrade() -> None:
    raise SchemaVersionError(
        "기준 버전의 downgrade는 실행·승인 데이터를 삭제하므로 지원하지 않습니다. "
        "이전 애플리케이션은 기존 표를 그대로 사용할 수 있습니다. 복구는 검증한 백업을 사용하세요."
    )
