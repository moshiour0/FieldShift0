from __future__ import annotations

import unittest
from unittest.mock import patch

from fieldshift.api import supabase_auth


class TestSupabaseAuth(unittest.TestCase):
    def test_bearer_token_is_case_insensitive_and_rejects_malformed_headers(self) -> None:
        self.assertEqual(supabase_auth.bearer_token("bEaReR abc.def"), "abc.def")
        self.assertIsNone(supabase_auth.bearer_token("Basic abc"))
        self.assertIsNone(supabase_auth.bearer_token("Bearer"))
        self.assertIsNone(supabase_auth.bearer_token(None))

    def test_settings_only_exposes_publishable_key(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test",
                "SUPABASE_SERVICE_ROLE_KEY": "must-not-be-returned",
            },
        ):
            result = supabase_auth.settings()
        self.assertTrue(result["configured"])
        self.assertEqual(result["url"], "https://example.supabase.co")
        self.assertEqual(result["publishable_key"], "sb_publishable_test")
        self.assertNotIn("service_role", result)

    @patch.object(supabase_auth, "_request_json")
    def test_get_user_validates_token_with_auth_server(self, request_json) -> None:
        with patch.dict(
            "os.environ",
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test",
            },
        ):
            request_json.return_value = {
                "id": "2b8e3e0d-7b39-4f73-83b9-90ee5d979fca",
                "email": "farmer@example.com",
                "created_at": "2026-11-09T00:00:00Z",
            }
            user = supabase_auth.get_user("user-access-token")
        self.assertEqual(user["id"], "2b8e3e0d-7b39-4f73-83b9-90ee5d979fca")
        self.assertEqual(user["email"], "farmer@example.com")
        request_json.assert_called_once()
        self.assertEqual(request_json.call_args.args[0], "https://example.supabase.co/auth/v1/user")
        self.assertEqual(
            request_json.call_args.kwargs["headers"]["Authorization"],
            "Bearer user-access-token",
        )

    @patch.object(supabase_auth, "_request_json")
    def test_request_analysis_run_recheck_uses_owner_access_token(self, request_json) -> None:
        run_id = "628a9906-127d-46c7-af5b-b0e979e2ac42"
        request_json.return_value = {
            "run_id": run_id,
            "status": "waiting_for_data",
            "stage": "queued",
            "already_queued": False,
        }
        with patch.dict(
            "os.environ",
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test",
            },
        ):
            result = supabase_auth.request_analysis_run_recheck(
                access_token="owner-access-token",
                run_id=run_id,
            )

        self.assertEqual(result["run_id"], run_id)
        request_json.assert_called_once()
        self.assertEqual(
            request_json.call_args.args[0],
            "https://example.supabase.co/rest/v1/rpc/request_analysis_run_recheck",
        )
        self.assertEqual(request_json.call_args.kwargs["method"], "POST")
        self.assertEqual(
            request_json.call_args.kwargs["headers"]["Authorization"],
            "Bearer owner-access-token",
        )
        self.assertEqual(request_json.call_args.kwargs["payload"], {"p_run_id": run_id})

    @patch.object(supabase_auth, "save_completed_analysis")
    def test_persistence_builds_hashes_and_maps_source_statuses(self, save) -> None:
        save.return_value = {
            "run_id": "628a9906-127d-46c7-af5b-b0e979e2ac42",
            "already_saved": False,
        }
        response = {
            "run": {
                "status": "final_with_gaps",
                "is_final": True,
                "status_message": "One supplemental source is missing.",
                "engine_version": "3.0.0",
                "evidence_window": {
                    "start_date": "2026-08-01",
                    "end_date": "2026-08-31",
                },
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
                        "status": "not_configured",
                    },
                    {
                        "name": "Legacy error",
                        "source_key": "legacy_error",
                        "source_type": "satellite",
                        "status": "error",
                    },
                ]
            },
        }
        request_payload = {
            "client_request_id": "c5db7057-0bfb-4b54-855b-6f4db53c2c7a",
            "field": {"lat": 24.75, "lon": 90.41},
            "start_date": "2026-08-01",
            "end_date": "2026-08-31",
        }
        with patch("fieldshift.v3.google_drive.configured", return_value=True), patch(
            "fieldshift.v3.google_drive.put_object"
        ) as drive_put:
            result = supabase_auth.persist_product_analysis(
                access_token="user-access-token",
                request_payload=request_payload,
                response_payload=response,
            )
        self.assertEqual(result["run_id"], "628a9906-127d-46c7-af5b-b0e979e2ac42")
        call = save.call_args.kwargs
        self.assertEqual(call["run_record"]["status"], "final_with_gaps")
        self.assertEqual(call["run_record"]["client_request_id"], request_payload["client_request_id"])
        self.assertEqual(call["sources"][0]["status"], "available")
        self.assertEqual(call["sources"][1]["status"], "not_configured")
        self.assertEqual(call["sources"][2]["status"], "failed")
        self.assertEqual(call["result_record"]["result_kind"], "final_with_gaps")
        result_ref = call["result_record"]["result_payload"]
        self.assertEqual(result_ref["storage_provider"], "google_drive")
        self.assertTrue(result_ref["archive_object_key"].startswith("analysis-results/"))
        self.assertEqual(len(result_ref["archive_sha256"]), 64)
        self.assertEqual(drive_put.call_args.args[0], result_ref["archive_object_key"])
        self.assertEqual(len(call["run_record"]["request_sha256"]), 64)
        self.assertEqual(len(call["result_record"]["evidence_fingerprint"]), 64)


    def test_result_archive_requires_configured_private_google_drive(self) -> None:
        with (
            patch("fieldshift.v3.google_drive.configured", return_value=False),
            self.assertRaises(supabase_auth.SupabaseAPIError) as raised,
        ):
            supabase_auth.archive_result_payload(
                {"run": {"id": "run-1"}},
                storage_key="c5db7057-0bfb-4b54-855b-6f4db53c2c7a",
            )
        self.assertEqual(raised.exception.status_code, 503)

    def test_restore_result_payload_preserves_legacy_inline_result(self) -> None:
        legacy = {"run": {"id": "old-run"}, "evidence": {"items": []}}
        self.assertIs(supabase_auth.restore_result_payload(legacy), legacy)

    def test_restore_result_payload_reads_and_verifies_google_drive_object(self) -> None:
        import hashlib
        import json

        payload = {"run": {"id": "run-1"}, "evidence": {"items": []}}
        content = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
        ).encode("utf-8")
        digest = hashlib.sha256(content).hexdigest()
        reference = {
            "storage_provider": "google_drive",
            "archive_object_key": f"analysis-results/c5db7057-0bfb-4b54-855b-6f4db53c2c7a/{digest}.json",
            "archive_sha256": digest,
            "archive_size_bytes": len(content),
        }
        with patch("fieldshift.v3.google_drive.get_object", return_value=content) as drive_get:
            restored = supabase_auth.restore_result_payload(reference)
        self.assertEqual(restored, payload)
        drive_get.assert_called_once_with(reference["archive_object_key"])

    def test_restore_result_payload_rejects_tampered_drive_object(self) -> None:
        reference = {
            "storage_provider": "google_drive",
            "archive_object_key": f"analysis-results/c5db7057-0bfb-4b54-855b-6f4db53c2c7a/{'0' * 64}.json",
            "archive_sha256": "0" * 64,
            "archive_size_bytes": 5,
        }
        with (
            patch("fieldshift.v3.google_drive.get_object", return_value=b"false"),
            self.assertRaises(supabase_auth.SupabaseAPIError) as raised,
        ):
            supabase_auth.restore_result_payload(reference)
        self.assertEqual(raised.exception.status_code, 502)


if __name__ == "__main__":
    unittest.main()
