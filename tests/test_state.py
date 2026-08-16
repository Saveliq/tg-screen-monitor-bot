from bot.state import StateStore


def test_state_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    store = StateStore(path)
    store.upsert(123, 456)

    loaded = StateStore(path)
    viewer = loaded.get(123)
    assert viewer is not None
    assert viewer.message_id == 456
    assert viewer.enabled is True
