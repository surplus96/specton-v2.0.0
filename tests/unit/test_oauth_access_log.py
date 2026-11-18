import logging

from specton.api.access_log import OAuthQueryFilter, install_oauth_log_filter


def test_oauth_code_and_state_are_removed_from_access_message():
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("client", "GET", "/api/v1/auth/google/callback?code=secret&state=other", "1.1", 303),
        None,
    )
    assert OAuthQueryFilter().filter(record)
    assert "secret" not in record.getMessage() and "other" not in record.getMessage()
    assert "/api/v1/auth/google/callback" in record.getMessage()


def test_filter_install_is_idempotent():
    install_oauth_log_filter()
    install_oauth_log_filter()
    assert (
        sum(isinstance(f, OAuthQueryFilter) for f in logging.getLogger("uvicorn.access").filters)
        == 1
    )
