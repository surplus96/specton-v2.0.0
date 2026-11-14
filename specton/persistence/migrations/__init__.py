"""플랫폼 스키마의 버전 이력. LangGraph 표와 생성 앱 DB는 관리하지 않는다."""

HEAD = "0003_specification"


class SchemaVersionError(RuntimeError):
    """운영자가 명시적으로 이전 또는 복구해야 하는 스키마 상태."""
