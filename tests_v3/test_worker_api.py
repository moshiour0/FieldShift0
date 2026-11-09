from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from fieldshift.api.analysis_worker import WorkerAPIError
from fieldshift.api.app import app


class TestDurableWorkerAPI(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_worker_endpoint_rejects_missing_or_wrong_token(self) -> None:
        with patch.dict(os.environ, {"FIELDSHIFT_WORKER_TOKEN": "worker-secret-for-tests"}), patch(
            "fieldshift.api.app.process_analysis_worker_one"
        ) as process:
            missing = self.client.post("/api/internal/worker/tick")
            wrong = self.client.post(
                "/api/internal/worker/tick",
                headers={"x-fieldshift-worker": "wrong-token"},
            )
        self.assertEqual(missing.status_code, 401)
        self.assertEqual(wrong.status_code, 401)
        process.assert_not_called()

    def test_worker_returns_idle_when_no_job_is_available(self) -> None:
        with patch.dict(os.environ, {"FIELDSHIFT_WORKER_TOKEN": "worker-secret-for-tests"}), patch(
            "fieldshift.api.app.process_analysis_worker_one",
            return_value={"processed": False, "message": "No queued analysis job is ready."},
        ) as process:
            response = self.client.post(
                "/api/internal/worker/tick",
                headers={"x-fieldshift-worker": "worker-secret-for-tests"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertFalse(response.json()["processed"])
        process.assert_called_once_with("worker-secret-for-tests")

    def test_worker_returns_processed_result(self) -> None:
        expected = {
            "processed": True,
            "run_id": "11111111-2222-4333-8444-555555555555",
            "status": "retrying",
            "revision": 2,
            "job_status": "retrying",
            "next_retry_at": "2026-11-09T11:00:00+00:00",
        }
        with patch.dict(os.environ, {"FIELDSHIFT_WORKER_TOKEN": "worker-secret-for-tests"}), patch(
            "fieldshift.api.app.process_analysis_worker_one",
            return_value=expected,
        ) as process:
            response = self.client.post(
                "/api/internal/worker/tick",
                headers={"x-fieldshift-worker": "worker-secret-for-tests"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, **expected})
        process.assert_called_once_with("worker-secret-for-tests")

    def test_worker_translates_safe_processing_errors_to_503(self) -> None:
        with patch.dict(os.environ, {"FIELDSHIFT_WORKER_TOKEN": "worker-secret-for-tests"}), patch(
            "fieldshift.api.app.process_analysis_worker_one",
            side_effect=WorkerAPIError("The analysis worker could not complete this job."),
        ) as process:
            response = self.client.post(
                "/api/internal/worker/tick",
                headers={"x-fieldshift-worker": "worker-secret-for-tests"},
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "The analysis worker could not complete this job.")
        process.assert_called_once_with("worker-secret-for-tests")


if __name__ == "__main__":
    unittest.main()
