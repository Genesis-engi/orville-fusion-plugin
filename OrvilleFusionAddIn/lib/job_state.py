"""Local non-secret state for the Orville Fusion add-in."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .api_client import sanitize_filename


@dataclass
class DownloadRecord:
    artifact_id: str
    filename: str
    path: str


@dataclass
class JobState:
    current_job_id: str | None = None
    status: str | None = None
    latest_revision_id: str | None = None
    explanation: str | None = None
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    downloads: dict[str, DownloadRecord] = field(default_factory=dict)
    request_id: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "JobState":
        downloads = {
            key: DownloadRecord(**record)
            for key, record in (payload.get("downloads") or {}).items()
            if isinstance(record, dict)
        }
        return cls(
            current_job_id=payload.get("current_job_id"),
            status=payload.get("status"),
            latest_revision_id=payload.get("latest_revision_id"),
            explanation=payload.get("explanation"),
            artifacts=list(payload.get("artifacts") or []),
            downloads=downloads,
            request_id=payload.get("request_id"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def apply_job_response(self, job: dict[str, Any]) -> None:
        self.current_job_id = job.get("id") or self.current_job_id
        self.status = job.get("status") or self.status
        self.latest_revision_id = job.get("latest_revision_id") or self.latest_revision_id
        self.explanation = job.get("explanation") or self.explanation
        self.artifacts = list(job.get("artifacts") or self.artifacts or [])
        self.request_id = job.get("request_id") or self.request_id

    def record_download(self, artifact_id: str, filename: str, path: str) -> None:
        self.downloads[artifact_id] = DownloadRecord(
            artifact_id=artifact_id,
            filename=sanitize_filename(filename),
            path=path,
        )


class StateStore:
    """Atomically reads and writes non-secret job state."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)

    def load(self) -> JobState:
        if not self.path.exists():
            return JobState()
        with self.path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            return JobState()
        return JobState.from_dict(payload)

    def save(self, state: JobState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(state.to_dict(), handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()
