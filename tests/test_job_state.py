from __future__ import annotations

import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "OrvilleFusionAddIn"))

from lib.job_state import JobState, StateStore


class JobStateTests(unittest.TestCase):
    def test_state_store_round_trips_job_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            store = StateStore(tmp_path / "state.json")
            state = JobState()
            state.apply_job_response(
                {
                    "id": "cadjob_123",
                    "status": "completed",
                    "latest_revision_id": "rev_1",
                    "explanation": "Done.",
                    "artifacts": [{"id": "art_1", "filename": "part.step", "kind": "step"}],
                    "request_id": "req_1",
                }
            )
            state.record_download("art_1", "part.step", str(tmp_path / "part.step"))

            store.save(state)
            loaded = store.load()

        self.assertEqual(loaded.current_job_id, "cadjob_123")
        self.assertEqual(loaded.status, "completed")
        self.assertEqual(loaded.latest_revision_id, "rev_1")
        self.assertEqual(loaded.artifacts[0]["id"], "art_1")
        self.assertEqual(loaded.downloads["art_1"].filename, "part.step")

    def test_state_store_missing_file_returns_empty_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            loaded = StateStore(Path(tmp) / "missing.json").load()

        self.assertIsNone(loaded.current_job_id)
        self.assertEqual(loaded.artifacts, [])
        self.assertEqual(loaded.downloads, {})

    def test_state_store_clear_removes_saved_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StateStore(Path(tmp) / "state.json")
            state = JobState(current_job_id="cadjob_123", status="completed")

            store.save(state)
            store.clear()
            loaded = store.load()

        self.assertIsNone(loaded.current_job_id)
        self.assertIsNone(loaded.status)


if __name__ == "__main__":
    unittest.main()
