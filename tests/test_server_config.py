from server.app.config import parse_user_ids


def test_parse_user_ids():
    assert parse_user_ids("123, 456,123") == frozenset({123, 456})
