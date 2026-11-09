from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from fieldshift.api.app import app, _worker_retry_at


class TestDurableWorkerAPI(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_worker_endpoint_rejects_missing_or_wrong_token(self) -> None:
        with patch.dict(os.environ, {"FIELD_SHIFT_WORKER_SECRET": "worker-secret-for-tests"}), patch(
            "fieldshift.api.app.supabase_auth.claim_worker_job"
        ) as claim:
            missing = self.client.post("/api/internal/worker/tick", json={})
            wrong = self.client.post(
                "/api/internal/worker/tick",
                json={},
                headers={"x-fieldshift-worker": "wrong-token"},
            )
        self.assertEqual(missing.status_code, 401)
        self.assertEqual(wrong.status_code, 401)
        claim.assert_not_called()

    def test_worker_returns_idle_when_no_job_is_available(self) -> None:
        with patch.dict(os.environ, {"FIELD_SHIFT_WORKER_SECRET": "worker-secret-for-tests"}), patch(
            "fieldshift.api.app.supabase_auth.claim_worker_job", return_value=None
        ) as claim:
            response = self.client.post(
                "/api/internal/worker/tick",
                json={},
                headers={"x-fieldshift-worker": "worker-secret-for-tests"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "idle")
        self.assertFalse(response.json()["processed"])
        claim.assert_called_once_with("worker-secret-for-tests")

    def test_worker_processes_one_reconciliation_and_reschedules_pending_data(self) -> None:
        job = {
            "id": "628a9906-127d-46c7-af5b-b0e979e2ac42",
            "run_id": "11111111-2222-4333-8444-555555555555",
            "job_type": "reconcile_run",
            "attempts": 2,
            "payload": {
                "request_payload": {
                    "field": {"lat": 24.75, "lon": 90.41, "area_ha": 0.4},
                    "start_date": "2026-08-01",
                    "end_date": "2026-08-31",
                    "priority_choices": ["water", "soil"],
                }
            },
        }
        result = {
            "run": {
                "status": "preliminary_ready",
                "is_final": False,
                "status_message": "One provider is still processing.",
                "evidence_window": {"start_date": "2026-08-01", "end_date": "2026-08-31"},
            },
            "evidence": {
                "items": [
                    {
                        "name": "NASA POWER Daily weather",
                        "source_key": "nasa_power_daily_weather",
                        "source_type": "weather",
                        "required": True,
                        "status": "available",
                    },
                    {
                        "name": "NASA SMAP",
                        "source_key": "nasa_smap",
                        "source_type": "satellite",
                        "status": "pending",
                        "retry_after_seconds": 3600,
                    },
                ]
            },
        }
        with patch.dict(os.environ, {"FIELD_SHIFT_WORKER_SECRET": "worker-secret-for-tests"}), patch(
            "fieldshift.api.app.supabase_auth.claim_worker_job", return_value=job
        ), patch("fieldshift.api.app.create_analysis", return_value=result) as create, patch(
            "fieldshift.api.app.supabase_auth.save_worker_analysis",
            return_value={"job_status": "retrying", "revision": 2, "next_retry_at": "2026-11-09T11:00:00+00:00"},
        ) as save:
            response = self.client.post(
                "/api/internal/worker/tick",
                json={"trigger": "unit-test"},
                headers={"x-fieldshift-worker": "worker-secret-for-tests"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["processed"])
        self.assertEqual(response.json()["status"], "retrying")
        create.assert_called_once_with(job["payload"]["request_payload"])
        self.assertEqual(save.call_args.kwargs["job_id"], job["id"])
        self.assertEqual(save.call_args.kwargs["run_id"], job["run_id"])
        self.assertIsNotNone(save.call_args.kwargs["retry_at"])

    def test_worker_retry_policy_uses_provider_retry_after(self) -> None:
        result = {
            "evidence": {
                "items": [
                    {"status": "pending", "retry_after_seconds": 7200},
                    {"status": "available"},
                ]
            }
        }
        retry_at = _worker_retry_at(result, attempt=1)
        self.assertIsNotNone(retry_at)

    def test_worker_does_not_schedule_retry_when_sources_are_settled(self) -> None:
        result = {"evidence": {"items": [{"status": "available"}, {"status": "unavailable"}]}}
        self.assertIsNone(_worker_retry_at(result, attempt=1))


if __name__ == "__main__":
    unittest.main()
