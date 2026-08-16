from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ViewerState:
    chat_id: int
    message_id: int | None = None
    enabled: bool = True


class StateStore:
    def __init__(self, path: Path):
        self.path = path
        self._viewers: dict[int, ViewerState] = {}
        self.load()

    @property
    def viewers(self) -> list[ViewerState]:
        return [viewer for viewer in self._viewers.values() if viewer.enabled]

    def get(self, chat_id: int) -> ViewerState | None:
        return self._viewers.get(chat_id)

    def upsert(self, chat_id: int, message_id: int | None = None) -> ViewerState:
        viewer = self._viewers.get(chat_id)
        if viewer is None:
            viewer = ViewerState(chat_id=chat_id, message_id=message_id, enabled=True)
            self._viewers[chat_id] = viewer
        else:
            viewer.enabled = True
            if message_id is not None:
                viewer.message_id = message_id
        self.save()
        return viewer

    def disable(self, chat_id: int) -> None:
        viewer = self._viewers.get(chat_id)
        if viewer is not None:
            viewer.enabled = False
            self.save()

    def set_message_id(self, chat_id: int, message_id: int) -> None:
        viewer = self.upsert(chat_id)
        viewer.message_id = message_id
        self.save()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            for item in payload.get("viewers", []):
                viewer = ViewerState(
                    chat_id=int(item["chat_id"]),
                    message_id=int(item["message_id"]) if item.get("message_id") is not None else None,
                    enabled=bool(item.get("enabled", True)),
                )
                self._viewers[viewer.chat_id] = viewer
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            self._viewers = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "viewers": [
                {
                    "chat_id": viewer.chat_id,
                    "message_id": viewer.message_id,
                    "enabled": viewer.enabled,
                }
                for viewer in self._viewers.values()
            ]
        }
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)
