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
