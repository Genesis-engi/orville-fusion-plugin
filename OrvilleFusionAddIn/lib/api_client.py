"""Standard-library client for the Orville CAD API."""

from __future__ import annotations

import json
import mimetypes
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable, Iterable

BASE_URL = "https://www.ballistalabs.ai"
JSON_CONTENT_TYPE = "application/json"
MAX_IMAGES = 5
MAX_IMAGE_BYTES = 10 * 1024 * 1024
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif"}


class OrvilleAPIError(RuntimeError):
    """Raised when the Orville API returns a non-success response."""

    def __init__(
        self,
        status: int,
        message: str,
        *,
        code: str | None = None,
        request_id: str | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.request_id = request_id
        self.retry_after = retry_after

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "code": self.code,
            "message": self.message,
            "request_id": self.request_id,
            "retry_after": self.retry_after,
        }


class OrvilleClient:
    """Client for creating, polling, iterating, and downloading CAD jobs."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = BASE_URL,
        opener: Callable[..., Any] | None = None,
        timeout: int = 60,
    ) -> None:
        api_key = (api_key or "").strip()
        if not api_key:
            raise ValueError("An Orville API key is required.")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.opener = opener or urllib.request.urlopen
        self.timeout = timeout

    def create_job(
        self,
        prompt: str,
        *,
        image_paths: Iterable[str | os.PathLike[str]] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        return self._write_prompt(
            "POST",
            "/api/v1/cad/jobs",
            prompt,
            image_paths=image_paths,
            idempotency_key=idempotency_key,
        )

    def send_followup(
        self,
        job_id: str,
        prompt: str,
        *,
        image_paths: Iterable[str | os.PathLike[str]] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        quoted_job_id = urllib.parse.quote(job_id, safe="")
        return self._write_prompt(
            "POST",
            f"/api/v1/cad/jobs/{quoted_job_id}/messages",
            prompt,
            image_paths=image_paths,
            idempotency_key=idempotency_key,
        )

    def review_job(
        self,
        job_id: str,
        prompt: str,
        *,
        revision_id: str | None = None,
        viewer_state: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        prompt = (prompt or "").strip()
        if not prompt:
            raise ValueError("Prompt is required.")

        quoted_job_id = urllib.parse.quote(job_id, safe="")
        body: dict[str, Any] = {"prompt": prompt}
        if revision_id:
            body["revision_id"] = revision_id
        if viewer_state is not None:
            body["viewer_state"] = viewer_state

        return self._request_json(
            "POST",
            f"/api/v1/cad/jobs/{quoted_job_id}/review",
            body=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": JSON_CONTENT_TYPE,
                "Idempotency-Key": idempotency_key or str(uuid.uuid4()),
            },
        )

    def get_job(self, job_id: str) -> dict[str, Any]:
        quoted_job_id = urllib.parse.quote(job_id, safe="")
        return self._request_json("GET", f"/api/v1/cad/jobs/{quoted_job_id}")

    def list_jobs(
        self,
        *,
        limit: int = 20,
        cursor: str | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        params = {"limit": str(max(1, min(int(limit), 100)))}
        if cursor:
            params["cursor"] = cursor
        if query:
            params["q"] = query
        return self._request_json("GET", f"/api/v1/cad/jobs?{urllib.parse.urlencode(params)}")

    def list_messages(self, job_id: str) -> dict[str, Any]:
        quoted_job_id = urllib.parse.quote(job_id, safe="")
        return self._request_json("GET", f"/api/v1/cad/jobs/{quoted_job_id}/messages")

    def list_artifacts(self, job_id: str) -> dict[str, Any]:
        quoted_job_id = urllib.parse.quote(job_id, safe="")
        return self._request_json("GET", f"/api/v1/cad/jobs/{quoted_job_id}/artifacts")

    def billing_balance(self) -> dict[str, Any]:
        return self._request_json("GET", "/api/v1/billing/balance")

    def get_artifact_download_url(self, artifact_id: str) -> dict[str, Any]:
        quoted_artifact_id = urllib.parse.quote(artifact_id, safe="")
        return self._request_json(
            "GET",
            f"/api/v1/artifacts/{quoted_artifact_id}/download?redirect=false",
        )

    def download_artifact(
        self,
        artifact_id: str,
        destination_dir: str | os.PathLike[str],
        *,
        filename: str | None = None,
    ) -> Path:
        download = self.get_artifact_download_url(artifact_id)
        signed_url = download.get("url")
        if not signed_url:
            raise OrvilleAPIError(500, "Artifact download response did not include a signed URL.")

        target_name = filename or download.get("filename") or f"{artifact_id}.step"
        target_path = unique_path(Path(destination_dir), sanitize_filename(target_name))
        request = urllib.request.Request(str(signed_url), method="GET")

        with self.opener(request, timeout=self.timeout) as response:
            body = response.read()

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(body)
        return target_path

    def poll_until_terminal(
        self,
        job_id: str,
        *,
        on_update: Callable[[dict[str, Any]], None] | None = None,
        stop: Callable[[], bool] | None = None,
        default_interval_seconds: int = 60,
    ) -> dict[str, Any]:
        while True:
            if stop and stop():
                raise RuntimeError("Polling stopped.")
            job = self.get_job(job_id)
            if on_update:
                on_update(job)
            if job.get("status") in {"completed", "failed"}:
                return job

            delay = job.get("poll_after_seconds") or default_interval_seconds
            delay = max(1, int(delay))
            for _ in range(delay):
                if stop and stop():
                    raise RuntimeError("Polling stopped.")
                time.sleep(1)

    def _write_prompt(
        self,
        method: str,
        path: str,
        prompt: str,
        *,
        image_paths: Iterable[str | os.PathLike[str]] | None,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        prompt = (prompt or "").strip()
        if not prompt:
            raise ValueError("Prompt is required.")

        normalized_images = validate_images(image_paths or [])
        headers = {"Idempotency-Key": idempotency_key or str(uuid.uuid4())}

        if normalized_images:
            body, content_type = encode_multipart({"prompt": prompt}, [("images", p) for p in normalized_images])
            headers["Content-Type"] = content_type
        else:
            body = json.dumps({"prompt": prompt}).encode("utf-8")
            headers["Content-Type"] = JSON_CONTENT_TYPE

        return self._request_json(method, path, body=body, headers=headers)

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        response_body, status, response_headers = self._request(method, path, body=body, headers=headers)
        if not response_body:
            return {"request_id": get_header(response_headers, "X-Request-Id")}
        try:
            data = json.loads(response_body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise OrvilleAPIError(status, "Orville returned invalid JSON.") from exc
        if isinstance(data, dict) and "request_id" not in data:
            request_id = get_header(response_headers, "X-Request-Id")
            if request_id:
                data["request_id"] = request_id
        return data

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None,
        headers: dict[str, str] | None,
    ) -> tuple[bytes, int, Any]:
        request_headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": JSON_CONTENT_TYPE,
            "User-Agent": "orville-fusion-plugin/0.1",
        }
        request_headers.update(headers or {})
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        request = urllib.request.Request(url, data=body, headers=request_headers, method=method)

        try:
            with self.opener(request, timeout=self.timeout) as response:
                return response.read(), get_status(response), response.headers
        except urllib.error.HTTPError as exc:
            body_bytes = exc.read()
            request_id = get_header(exc.headers, "X-Request-Id")
            retry_after = parse_retry_after(get_header(exc.headers, "Retry-After"))
            code = None
            message = exc.reason or "Orville API request failed."
            try:
                payload = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
                error = payload.get("error") if isinstance(payload, dict) else None
                if isinstance(error, dict):
                    code = error.get("code")
                    message = error.get("message") or message
                request_id = payload.get("request_id") or request_id if isinstance(payload, dict) else request_id
            except json.JSONDecodeError:
                pass
            raise OrvilleAPIError(
                exc.code,
                message,
                code=code,
                request_id=request_id,
                retry_after=retry_after,
            ) from exc
        except urllib.error.URLError as exc:
            raise OrvilleAPIError(0, f"Could not reach Orville API: {exc.reason}") from exc


def validate_images(paths: Iterable[str | os.PathLike[str]]) -> list[Path]:
    images = [Path(p).expanduser() for p in paths]
    if len(images) > MAX_IMAGES:
        raise ValueError(f"Attach at most {MAX_IMAGES} images.")

    for image in images:
        suffix = image.suffix.lower()
        if suffix not in IMAGE_EXTENSIONS:
            raise ValueError(f"Unsupported image type: {image.name}")
        if not image.exists():
            raise ValueError(f"Image does not exist: {image}")
        if image.stat().st_size > MAX_IMAGE_BYTES:
            raise ValueError(f"Image exceeds 10 MB: {image.name}")
    return images


def encode_multipart(fields: dict[str, str], files: list[tuple[str, Path]]) -> tuple[bytes, str]:
    boundary = f"----OrvilleFusion{uuid.uuid4().hex}"
    chunks: list[bytes] = []

    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("ascii"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )

    for field_name, path in files:
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("ascii"),
                (
                    f'Content-Disposition: form-data; name="{field_name}"; '
                    f'filename="{path.name}"\r\n'
                ).encode("utf-8"),
                f"Content-Type: {content_type}\r\n\r\n".encode("ascii"),
                path.read_bytes(),
                b"\r\n",
            ]
        )

    chunks.append(f"--{boundary}--\r\n".encode("ascii"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def sanitize_filename(filename: str) -> str:
    name = Path(filename or "artifact.step").name
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in name).strip("._")
    if not cleaned:
        cleaned = "artifact.step"
    if not cleaned.lower().endswith((".step", ".stp")):
        cleaned += ".step"
    return cleaned


def unique_path(directory: Path, filename: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    for index in range(1, 1000):
        candidate = directory / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"Could not find a free filename for {filename}.")


def parse_retry_after(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return max(0, int(value))
    except ValueError:
        return None


def get_status(response: Any) -> int:
    if hasattr(response, "getcode"):
        return int(response.getcode())
    return int(getattr(response, "status", 200))


def get_header(headers: Any, key: str) -> str | None:
    if not headers:
        return None
    if hasattr(headers, "get"):
        return headers.get(key) or headers.get(key.lower())
    return None
