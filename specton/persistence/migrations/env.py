"""온라인·트랜잭션 기반 이전. 비밀값을 Alembic 설정/로그에 복사하지 않는다."""

from alembic import context

from specton.persistence.migrate import migration_connection
from specton.persistence.migrations.baseline import (
    verify_baseline,
    verify_identity,
    verify_implementation,
    verify_specification,
)

if context.is_offline_mode():
    raise RuntimeError("기준 구조 확인에는 DB 연결이 필요합니다. 백업 사본에서 온라인 실행하세요.")

with migration_connection(context.config) as connection:
    context.configure(
        connection=connection,
        version_table="alembic_version",
        version_table_schema=connection.info["migration_schema"],
        transactional_ddl=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()
        # 이미 버전이 등록된 DB의 임의 변경도 반복 upgrade로 덮지 않는다.
        verify_baseline(connection)
        if context.get_context().get_current_revision() in {
            "0002_identity",
            "0003_specification",
            "0004_implementation",
        }:
            verify_identity(connection)
        if context.get_context().get_current_revision() in {
            "0003_specification",
            "0004_implementation",
        }:
            verify_specification(connection)
        if context.get_context().get_current_revision() == "0004_implementation":
            verify_implementation(connection)
