from server.app.state import StateStore


def test_state_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    store = StateStore(path)
    store.enable(123)
    store.set_message_id(123, 456)
    restored = StateStore(path)
    viewer = restored.get(123)
    assert viewer is not None
    assert viewer.enabled is True
    assert viewer.message_id == 456
    restored.disable(123)
    assert restored.enabled_viewers == []
