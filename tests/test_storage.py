from server.app.storage import LatestFrameStore


def test_latest_frame_roundtrip(tmp_path):
    store = LatestFrameStore(tmp_path)
    meta = store.save(
        b"\xff\xd8fakejpeg",
        width=1920,
        height=1080,
        jpeg_quality=90,
        client_name="PC-1",
        client_time="2026-01-01T00:00:00+00:00",
    )
    assert store.read_image() == b"\xff\xd8fakejpeg"
    assert store.read_meta() == meta
