from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Viewer:
    chat_id: int
    enabled: bool = True
    message_id: int | None = None


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._viewers: dict[int, Viewer] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        for item in raw.get("viewers", []):
            try:
                viewer = Viewer(
                    chat_id=int(item["chat_id"]),
                    enabled=bool(item.get("enabled", True)),
                    message_id=(int(item["message_id"]) if item.get("message_id") is not None else None),
                )
            except (KeyError, TypeError, ValueError):
                continue
            self._viewers[viewer.chat_id] = viewer

    def _save(self) -> None:
        payload = {"viewers": [asdict(v) for v in self._viewers.values()]}
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self.path)

    @property
    def enabled_viewers(self) -> list[Viewer]:
        return [Viewer(**asdict(v)) for v in self._viewers.values() if v.enabled]

    def get(self, chat_id: int) -> Viewer | None:
        viewer = self._viewers.get(chat_id)
        return Viewer(**asdict(viewer)) if viewer else None

    def enable(self, chat_id: int) -> Viewer:
        viewer = self._viewers.get(chat_id)
        if viewer is None:
            viewer = Viewer(chat_id=chat_id)
            self._viewers[chat_id] = viewer
        viewer.enabled = True
        self._save()
        return Viewer(**asdict(viewer))

    def disable(self, chat_id: int) -> None:
        viewer = self._viewers.get(chat_id)
        if viewer is None:
            viewer = Viewer(chat_id=chat_id, enabled=False)
            self._viewers[chat_id] = viewer
        else:
            viewer.enabled = False
        self._save()

    def set_message_id(self, chat_id: int, message_id: int | None) -> None:
        viewer = self._viewers.get(chat_id)
        if viewer is None:
            viewer = Viewer(chat_id=chat_id)
            self._viewers[chat_id] = viewer
        viewer.message_id = message_id
        self._save()
