from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from fieldshift.api import analysis_worker


class TestAnalysisWorker(unittest.TestCase):
    def test_retry_after_uses_slowest_pending_provider(self) -> None:
        items = [
            {"status": "pending", "retry_after_seconds": 900},
            {"status": "retrying", "retry_after_seconds": 7200},
            {"status": "available"},
        ]
        self.assertEqual(analysis_worker._retry_after_seconds(items), 7200)

    def test_partial_source_with_retry_after_is_rechecked(self) -> None:
        self.assertEqual(
            analysis_worker._retry_after_seconds([{"status": "partial", "retry_after_seconds": 1800}]),
            1800,
        )

    def test_partial_source_without_retry_after_is_not_retried(self) -> None:
        self.assertIsNone(analysis_worker._retry_after_seconds([{"status": "partial"}]))

    def test_source_records_do_not_store_raw_provider_error_text(self) -> None:
        sources = analysis_worker._source_records([{
            "name": "NASA POWER",
            "source_key": "nasa_power_daily_weather",
            "status": "pending",
            "error": "Provider request failed with an internal response body",
        }])
        self.assertEqual(sources[0]["status"], "pending")
        self.assertEqual(sources[0]["last_error_code"], "PROVIDER_PENDING")
        self.assertNotIn("internal response body", str(sources[0]))

    def test_optional_pending_smap_keeps_a_preliminary_result_available(self) -> None:
        engine_result = {
            "run": {
                "status": "final_with_gaps",
                "is_final": True,
                "status_message": "The engine returned a result with gaps.",
                "evidence_window": {"start_date": "2026-08-01", "end_date": "2026-08-31"},
            },
            "evidence": {
                "items": [
                    {"source_key": "nasa_power_daily_weather", "name": "NASA POWER", "required": True, "status": "available"},
                    {
                        "source_key": "nasa_smap",
                        "name": "NASA SMAP",
                        "required": False,
                        "status": "pending",
                        "retry_after_seconds": 3600,
                    },
                ]
            },
        }
        with patch(
            "fieldshift.api.analysis_worker._rest_json",
            return_value={"run_id": "11111111-2222-4333-8444-555555555555", "job_status": "retrying"},
        ) as save:
            analysis_worker._save_result("job-1", engine_result, "w" * 56)

        payload = save.call_args.kwargs["payload"]
        self.assertEqual(payload["p_run"]["status"], "preliminary_ready")
        self.assertEqual(payload["p_result"]["result_kind"], "preliminary")
        saved_run = payload["p_result"]["result_payload"]["run"]
        self.assertEqual(saved_run["status"], "preliminary_ready")
        self.assertFalse(saved_run["is_final"])
        self.assertIn("Optional evidence is still processing", saved_run["status_message"])
        self.assertEqual(engine_result["run"]["status"], "final_with_gaps")
        self.assertEqual(payload["p_retry_at"] is not None, True)

    def test_pending_required_power_keeps_run_waiting_for_data(self) -> None:
        engine_result = {
            "run": {"status": "preliminary_ready", "is_final": False},
            "evidence": {"items": [
                {"source_key": "nasa_power_daily_weather", "name": "NASA POWER", "required": True,
                 "status": "pending", "retry_after_seconds": 900},
                {"source_key": "nasa_smap", "name": "NASA SMAP", "required": False, "status": "available"},
            ]},
        }
        with patch(
            "fieldshift.api.analysis_worker._rest_json",
            return_value={"run_id": "11111111-2222-4333-8444-555555555555", "job_status": "retrying"},
        ) as save:
            analysis_worker._save_result("job-1", engine_result, "w" * 56)
        payload = save.call_args.kwargs["payload"]
        self.assertEqual(payload["p_run"]["status"], "waiting_for_data")
        self.assertFalse(payload["p_result"]["result_payload"]["run"]["is_final"])
        self.assertIn("Required evidence is still pending", payload["p_run"]["status_message"])

    def test_final_result_without_pending_providers_remains_final(self) -> None:
        engine_result = {
            "run": {
                "status": "final_ready",
                "is_final": True,
                "status_message": "All required evidence is available.",
                "evidence_window": {"start_date": "2026-08-01", "end_date": "2026-08-31"},
            },
            "evidence": {"items": [{"source_key": "nasa_power", "name": "NASA POWER", "status": "available"}]},
        }
        with patch(
            "fieldshift.api.analysis_worker._rest_json",
            return_value={"run_id": "11111111-2222-4333-8444-555555555555", "job_status": "succeeded"},
        ) as save:
            analysis_worker._save_result("job-1", engine_result, "w" * 56)

        payload = save.call_args.kwargs["payload"]
        self.assertEqual(payload["p_run"]["status"], "final_ready")
        self.assertEqual(payload["p_result"]["result_kind"], "final")
        self.assertTrue(payload["p_result"]["result_payload"]["run"]["is_final"])


    def test_source_records_persist_shared_archive_provenance(self) -> None:
        sources = analysis_worker._source_records([{
            "name": "NASA SMAP",
            "source_key": "nasa_smap",
            "status": "available",
            "archive_cache_status": "verified",
            "archive_object_key": "satellite-point-cache/v1/smap/abc.json",
            "archive_sha256": "a" * 64,
        }])
        self.assertEqual(sources[0]["provenance"]["archive_cache_status"], "verified")
        self.assertEqual(sources[0]["provenance"]["archive_sha256"], "a" * 64)

    def test_saved_provider_task_ids_are_loaded_from_active_run_sources(self) -> None:
        expected = {
            "nasa_smap": "appeears-smap-task",
            "nasa_hls": "appeears-hls-task",
        }
        with patch(
            "fieldshift.api.analysis_worker._rest_json",
            return_value=[
                {"source_key": "nasa_smap", "provider_task_id": "appeears-smap-task"},
                {"source_key": "nasa_hls", "provider_task_id": "appeears-hls-task"},
                {"source_key": "nasa_modis_mod16", "provider_task_id": None},
            ],
        ) as load:
            result = analysis_worker._load_provider_task_ids("run-123", "w" * 56)

        self.assertEqual(result, expected)
        query = load.call_args.kwargs["query"]
        self.assertIn("provider_task_id=not.is.null", query)
        self.assertIn("run_id=eq.run-123", query)

    def test_worker_injects_saved_provider_task_ids_into_engine_retry(self) -> None:
        engine_result = {
            "run": {"status": "waiting_for_data", "is_final": False},
            "evidence": {"items": []},
        }
        request_payload = {
            "start_date": "2026-06-20",
            "end_date": "2026-06-30",
            "field": {"lat": 24.75},
        }
        with (
            patch(
                "fieldshift.api.analysis_worker._settings",
                return_value=("https://fieldshift.example.supabase.co", "publishable", "anon-jwt", "w" * 56),
            ),
            patch("fieldshift.api.analysis_worker._claim_job", return_value={
                "id": "job-123", "run_id": "run-123", "attempts": 5,
            }),
            patch("fieldshift.api.analysis_worker._load_run", return_value={
                "request_payload": request_payload,
            }),
            patch("fieldshift.api.analysis_worker._load_provider_task_ids", return_value={
                "nasa_smap": "smap-task-123", "nasa_hls": "hls-task-456",
            }),
            patch("fieldshift.api.product.create_analysis", return_value=engine_result) as create,
            patch("fieldshift.api.analysis_worker._save_result", return_value={
                "run_id": "run-123", "status": "waiting_for_data", "revision": 2, "job_status": "retrying",
            }),
        ):
            result = analysis_worker.process_one("w" * 56)

        payload = create.call_args.args[0]
        self.assertEqual(payload["_provider_task_ids"], {
            "nasa_smap": "smap-task-123", "nasa_hls": "hls-task-456",
        })
        self.assertTrue(payload["_allow_live_smap"])
        self.assertNotIn("_provider_task_ids", request_payload)
        self.assertNotIn("_allow_live_smap", request_payload)
        self.assertEqual(result["run_id"], "run-123")
        self.assertEqual(result["status"], "waiting_for_data")

    def test_first_worker_attempt_only_checks_smap_cache(self) -> None:
        engine_result = {
            "run": {"status": "preliminary_ready", "is_final": False},
            "evidence": {"items": []},
        }
        request_payload = {
            "start_date": "2016-01-01",
            "end_date": "2025-12-31",
            "field": {"lat": 24.75, "lon": 90.41},
        }
        with (
            patch(
                "fieldshift.api.analysis_worker._settings",
                return_value=("https://fieldshift.example.supabase.co", "publishable", "anon-jwt", "w" * 56),
            ),
            patch("fieldshift.api.analysis_worker._claim_job", return_value={
                "id": "job-initial", "run_id": "run-initial", "attempts": 1,
            }),
            patch("fieldshift.api.analysis_worker._load_run", return_value={
                "request_payload": request_payload,
            }),
            patch("fieldshift.api.analysis_worker._load_provider_task_ids", return_value={}),
            patch("fieldshift.api.product.create_analysis", return_value=engine_result) as create,
            patch("fieldshift.api.analysis_worker._save_result", return_value={
                "run_id": "run-initial", "status": "preliminary_ready", "revision": 1, "job_status": "retrying",
            }),
        ):
            result = analysis_worker.process_one("w" * 56)

        payload = create.call_args.args[0]
        self.assertFalse(payload["_allow_live_smap"])
        self.assertNotIn("_allow_live_smap", request_payload)
        self.assertEqual(result["status"], "preliminary_ready")

    def test_worker_api_uses_publishable_key_and_anon_jwt_role_context(self) -> None:
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'{"ok":true}'
        with patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "https://fieldshift.example.supabase.co",
                "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_example",
                "SUPABASE_ANON_KEY": "legacy-anon-jwt",
                "FIELDSHIFT_WORKER_TOKEN": "w" * 56,
            },
        ), patch("fieldshift.api.analysis_worker.urllib.request.urlopen", return_value=response) as urlopen:
            result = analysis_worker._rest_json("rpc/claim_analysis_run_job", method="POST", payload={}, timeout=5)
        self.assertEqual(result, {"ok": True})
        request = urlopen.call_args.args[0]
        self.assertEqual(request.headers.get("Apikey"), "sb_publishable_example")
        self.assertEqual(request.headers.get("Authorization"), "Bearer legacy-anon-jwt")
        self.assertEqual(request.headers.get("X-fieldshift-worker"), "w" * 56)

    def test_worker_settings_reject_missing_anon_jwt(self) -> None:
        with (
            patch.dict(
                os.environ,
                {
                    "SUPABASE_URL": "https://fieldshift.example.supabase.co",
                    "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_example",
                    "SUPABASE_ANON_KEY": "",
                    "FIELDSHIFT_WORKER_TOKEN": "w" * 56,
                },
            ),
            self.assertRaises(analysis_worker.WorkerAPIError),
        ):
            analysis_worker._settings()

    def test_transient_errors_retry_but_validation_errors_do_not(self) -> None:
        self.assertTrue(analysis_worker._is_retryable_worker_error(TimeoutError("network")))
        self.assertTrue(analysis_worker._is_retryable_worker_error(ConnectionError("network")))
        self.assertTrue(analysis_worker._is_retryable_worker_error(
            analysis_worker.WorkerAPIError("upstream error", status_code=503)
        ))
        self.assertFalse(analysis_worker._is_retryable_worker_error(
            analysis_worker.WorkerAPIError("unauthorized", status_code=401)
        ))
        self.assertFalse(analysis_worker._is_retryable_worker_error(ValueError("invalid request")))


if __name__ == "__main__":
    unittest.main()
