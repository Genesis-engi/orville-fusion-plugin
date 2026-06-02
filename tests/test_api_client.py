from __future__ import annotations

import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "OrvilleFusionAddIn"))

from lib.api_client import OrvilleAPIError, OrvilleClient, sanitize_filename, validate_images


class FakeHeaders(dict):
    def get(self, key, default=None):
        return super().get(key, super().get(str(key).lower(), default))


class FakeResponse:
    def __init__(self, payload=b"{}", status=200, headers=None):
        self.payload = payload
        self.status = status
        self.headers = FakeHeaders(headers or {})

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.payload

    def getcode(self):
        return self.status


class FakeOpener:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class ApiClientTests(unittest.TestCase):
    def test_create_job_uses_json_without_images(self):
        opener = FakeOpener(
            FakeResponse(
                json.dumps({"id": "cadjob_123", "status": "queued"}).encode("utf-8"),
                status=202,
                headers={"X-Request-Id": "req_1"},
            )
        )
        client = OrvilleClient("gcad_test", opener=opener)

        response = client.create_job("Create a bracket.", idempotency_key="idem-1")

        request = opener.requests[0]
        self.assertEqual(response["id"], "cadjob_123")
        self.assertEqual(request.full_url, "https://www.ballistalabs.ai/api/v1/cad/jobs")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer gcad_test")
        self.assertEqual(request.get_header("Idempotency-key"), "idem-1")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(json.loads(request.data.decode("utf-8")), {"prompt": "Create a bracket."})

    def test_create_job_uses_multipart_with_images(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "ref.png"
            image.write_bytes(b"fake-png")
            opener = FakeOpener(FakeResponse(json.dumps({"id": "cadjob_123", "status": "queued"}).encode("utf-8")))
            client = OrvilleClient("gcad_test", opener=opener)

            client.create_job("Use this sketch.", image_paths=[image], idempotency_key="idem-2")

        request = opener.requests[0]
        body = request.data
        self.assertTrue(request.get_header("Content-type").startswith("multipart/form-data; boundary="))
        self.assertIn(b'name="prompt"', body)
        self.assertIn(b"Use this sketch.", body)
        self.assertIn(b'name="images"; filename="ref.png"', body)
        self.assertIn(b"fake-png", body)

    def test_http_errors_preserve_api_error_details(self):
        payload = json.dumps(
            {
                "error": {"code": "job_already_running", "message": "CAD job already has an active run"},
                "request_id": "req_payload",
            }
        ).encode("utf-8")
        error = urllib.error.HTTPError(
            "https://www.ballistalabs.ai/api/v1/cad/jobs",
            409,
            "Conflict",
            FakeHeaders({"Retry-After": "30"}),
            io.BytesIO(payload),
        )
        client = OrvilleClient("gcad_test", opener=FakeOpener(error))

        with self.assertRaises(OrvilleAPIError) as exc_info:
            client.create_job("Create a bracket.", idempotency_key="idem-3")

        error = exc_info.exception
        self.assertEqual(error.status, 409)
        self.assertEqual(error.code, "job_already_running")
        self.assertEqual(error.message, "CAD job already has an active run")
        self.assertEqual(error.request_id, "req_payload")
        self.assertEqual(error.retry_after, 30)

    def test_review_job_uses_review_endpoint(self):
        opener = FakeOpener(
            FakeResponse(
                json.dumps(
                    {
                        "job_id": "cadjob_123",
                        "revision_id": "rev_1",
                        "review": {"message": "Looks manufacturable."},
                    }
                ).encode("utf-8")
            )
        )
        client = OrvilleClient("gcad_test", opener=opener)

        response = client.review_job(
            "cadjob_123",
            "Check manufacturability.",
            revision_id="rev_1",
            viewer_state={"camera": {"target": [0, 0, 0]}},
            idempotency_key="idem-review",
        )

        request = opener.requests[0]
        self.assertEqual(response["review"]["message"], "Looks manufacturable.")
        self.assertEqual(
            request.full_url,
            "https://www.ballistalabs.ai/api/v1/cad/jobs/cadjob_123/review",
        )
        self.assertEqual(request.get_header("Idempotency-key"), "idem-review")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(
            json.loads(request.data.decode("utf-8")),
            {
                "prompt": "Check manufacturability.",
                "revision_id": "rev_1",
                "viewer_state": {"camera": {"target": [0, 0, 0]}},
            },
        )

    def test_list_jobs_uses_recent_jobs_endpoint(self):
        opener = FakeOpener(
            FakeResponse(
                json.dumps(
                    {
                        "jobs": [{"id": "cadjob_123", "title": "Mounting plate", "status": "completed"}],
                        "next_cursor": None,
                        "request_id": "req_1",
                    }
                ).encode("utf-8")
            )
        )
        client = OrvilleClient("gcad_test", opener=opener)

        response = client.list_jobs(limit=20, query="mounting plate")

        request = opener.requests[0]
        self.assertEqual(response["jobs"][0]["id"], "cadjob_123")
        self.assertEqual(
            request.full_url,
            "https://www.ballistalabs.ai/api/v1/cad/jobs?limit=20&q=mounting+plate",
        )

    def test_validate_images_rejects_bad_extension(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "ref.bmp"
            image.write_bytes(b"fake")

            with self.assertRaisesRegex(ValueError, "Unsupported image type"):
                validate_images([image])

    def test_sanitize_filename(self):
        cases = {
            "../part.step": "part.step",
            "weird name!.stp": "weird_name_.stp",
            "artifact": "artifact.step",
            "...": "artifact.step",
        }
        for input_name, expected in cases.items():
            with self.subTest(input_name=input_name):
                self.assertEqual(sanitize_filename(input_name), expected)


if __name__ == "__main__":
    unittest.main()
