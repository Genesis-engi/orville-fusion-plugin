"""Background task helpers for the Fusion add-in."""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from typing import Any


class TaskRunner:
    """Runs blocking work off the Fusion UI thread and posts queue events."""

    def __init__(self, event_queue: "queue.Queue[dict[str, Any]]", fire_event: Callable[[], None]) -> None:
        self.event_queue = event_queue
        self.fire_event = fire_event
        self.stop_event = threading.Event()
        self._threads: list[threading.Thread] = []

    def submit(self, event_name: str, fn: Callable[[], Any]) -> None:
        thread = threading.Thread(target=self._run, args=(event_name, fn), daemon=True)
        self._threads.append(thread)
        thread.start()

    def stop(self) -> None:
        self.stop_event.set()

    def _run(self, event_name: str, fn: Callable[[], Any]) -> None:
        if self.stop_event.is_set():
            return
        try:
            payload = fn()
            self.event_queue.put({"event": event_name, "payload": payload})
        except Exception as exc:  # noqa: BLE001 - must cross thread boundary as data.
            self.event_queue.put(
                {
                    "event": "task_error",
                    "payload": {
                        "message": str(exc),
                        "type": exc.__class__.__name__,
                        "details": getattr(exc, "to_dict", lambda: None)(),
                    },
                }
            )
        finally:
            self.fire_event()
