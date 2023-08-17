from unittest.mock import patch

from drc_cmis.connections import get_session, use_cmis_connection_pool


def test_no_wrapped_block(requests_mock):
    requests_mock.get("https://example.com")

    with patch("requests.Session.close") as mock_close:
        session = get_session()
        r = session.get("https://example.com")

        assert r.status_code == 200
        mock_close.assert_not_called()

    # clean up manually
    session.close()


def test_decorator(requests_mock):
    requests_mock.get("https://example.com/1")
    requests_mock.get("https://example.com/2")

    with patch("requests.Session.close") as mock_close:
        session = get_session()

        @use_cmis_connection_pool
        def do_calls():
            r1 = session.get("https://example.com/1")
            r2 = session.get("https://example.com/2")
            return r1, r2

        r1, r2 = do_calls()

        assert r1.status_code == 200
        assert r2.status_code == 200
        mock_close.assert_called()


def test_context_manager(requests_mock):
    requests_mock.get("https://example.com/1")
    requests_mock.get("https://example.com/2")

    with patch("requests.Session.close") as mock_close:
        with use_cmis_connection_pool() as session:
            r1 = session.get("https://example.com/1")
            r2 = session.get("https://example.com/2")

        assert r1.status_code == 200
        assert r2.status_code == 200
        mock_close.assert_called_once()


def test_nested_blocks(requests_mock):
    with use_cmis_connection_pool() as session1:
        with use_cmis_connection_pool() as session2:
            assert session1 is session2
        # after inner block exits, the session should still be the same object
        session3 = get_session()
        assert session3 is session1

    # after outer block exits, we should get a new instance with a fresh conn pool
    session4 = get_session()
    assert session4 is not session1
    assert session4 is not session2
    assert session4 is not session3


def test_session_is_thread_local():
    session1 = get_session()
    session2 = get_session()

    assert session1 is session2


def test_closed_session_is_new_instance():
    session1 = get_session()

    with use_cmis_connection_pool() as session:
        assert session is session1

    session2 = get_session()
    assert session2 is not session1
