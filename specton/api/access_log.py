"""OAuth callback의 일회용 code/state를 Uvicorn 접근 로그에서 제거한다."""

import logging


class OAuthQueryFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) == 5:
            path = args[2]
            if isinstance(path, str) and path.split("?", 1)[0] == "/api/v1/auth/google/callback":
                record.args = (*args[:2], "/api/v1/auth/google/callback", *args[3:])
        return True


def install_oauth_log_filter() -> None:
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, OAuthQueryFilter) for item in logger.filters):
        logger.addFilter(OAuthQueryFilter())
