from bot.config import _user_ids


def test_user_ids_parses_commas_and_semicolons():
    assert _user_ids("1, 2;3") == frozenset({1, 2, 3})
