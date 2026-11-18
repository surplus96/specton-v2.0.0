"""CI가 DB 미실행을 통과로 오인하지 않도록 명시적 필수 DB 모드를 제공한다."""

import psycopg
import pytest

from specton.config import Settings


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--require-db", action="store_true", help="앱/샌드박스 DB가 없으면 실패")


def pytest_sessionstart(session: pytest.Session) -> None:
    if not session.config.getoption("--require-db"):
        return
    settings = Settings(_env_file=None)
    for name, url in (
        ("app", settings.app_database_url),
        ("sandbox", settings.sandbox_database_url),
    ):
        try:
            with psycopg.connect(str(url), connect_timeout=3) as conn:
                conn.execute("SELECT 1").fetchone()
        except psycopg.OperationalError:
            raise pytest.UsageError(f"필수 {name} DB에 연결할 수 없습니다") from None


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]):
    report = yield
    if (
        item.config.getoption("--require-db")
        and item.get_closest_marker("db")
        and report.skipped
        and not item.get_closest_marker("native_pdf")
    ):
        report.outcome = "failed"
        report.longrepr = f"필수 DB 테스트가 건너뛰어졌습니다: {item.nodeid}"
    return report
