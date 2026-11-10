from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("FIELD_SHIFT_LIVE_NASA", "0")
from fastapi.testclient import TestClient

from fieldshift.api import product
from fieldshift.api.app import app


class TestAPI(unittest.TestCase):
    def test_health(self):
        c = TestClient(app)
        r = c.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["engine"], "3.0.0")

    def test_worker_status_uses_the_same_token_aliases_as_worker_execution(self):
        c = TestClient(app)
        base_env = {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test",
            "SUPABASE_ANON_KEY": "anon_test",
            "FIELDSHIFT_WORKER_TOKEN": "",
            "FIELD_SHIFT_WORKER_SECRET": "x" * 48,
        }
        with patch.dict(os.environ, base_env, clear=False):
            response = c.get("/api/status")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["analysis_state"]["active_execution_durable_across_instances"])

        base_env["FIELD_SHIFT_WORKER_SECRET"] = "too-short"
        with patch.dict(os.environ, base_env, clear=False):
            response = c.get("/api/status")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["analysis_state"]["active_execution_durable_across_instances"])

    def test_account_runs_requires_a_supabase_session(self):
        c = TestClient(app)
        response = c.get("/api/account/runs")
        self.assertEqual(response.status_code, 401)

    def test_account_runs_uses_the_verified_user_id_as_owner_filter(self):
        c = TestClient(app)
        user_id = "2b8e3e0d-7b39-4f73-83b9-90ee5d979fca"
        with patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test",
            },
        ), patch("fieldshift.api.app.supabase_auth.get_user", return_value={"id": user_id}), patch(
            "fieldshift.api.app.supabase_auth.rest_select", return_value=[]
        ) as rest_select:
            response = c.get("/api/account/runs", headers={"Authorization": "Bearer test-user-token"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"runs": []})
        self.assertEqual(rest_select.call_args.kwargs["filters"]["user_id"], f"eq.{user_id}")

    def test_saved_run_recheck_requires_a_supabase_session(self):
        c = TestClient(app)
        response = c.post("/api/account/runs/628a9906-127d-46c7-af5b-b0e979e2ac42/recheck")
        self.assertEqual(response.status_code, 401)

    def test_saved_run_recheck_uses_the_verified_owner_session(self):
        c = TestClient(app)
        user_id = "2b8e3e0d-7b39-4f73-83b9-90ee5d979fca"
        run_id = "628a9906-127d-46c7-af5b-b0e979e2ac42"
        result = {
            "run_id": run_id,
            "status": "waiting_for_data",
            "stage": "queued",
            "job_status": "queued",
            "already_queued": False,
            "available_at": "2026-11-09T10:00:00+00:00",
        }
        with patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test",
            },
        ), patch(
            "fieldshift.api.app.supabase_auth.get_user",
            return_value={"id": user_id},
        ), patch(
            "fieldshift.api.app.supabase_auth.request_analysis_run_recheck",
            return_value=result,
        ) as recheck:
            response = c.post(
                f"/api/account/runs/{run_id}/recheck",
                headers={"Authorization": "Bearer owner-access-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["queued"])
        self.assertFalse(response.json()["already_queued"])
        self.assertEqual(response.json()["run"]["id"], run_id)
        self.assertEqual(recheck.call_args.kwargs["access_token"], "owner-access-token")
        self.assertEqual(recheck.call_args.kwargs["run_id"], run_id)

    def test_saved_run_recheck_rejects_invalid_run_id_before_rpc(self):
        c = TestClient(app)
        with patch("fieldshift.api.app.supabase_auth.request_analysis_run_recheck") as recheck:
            response = c.post(
                "/api/account/runs/not-a-uuid/recheck",
                headers={"Authorization": "Bearer token"},
            )
        self.assertEqual(response.status_code, 404)
        recheck.assert_not_called()

    def test_analysis_queue_requires_sign_in(self):
        c = TestClient(app)
        response = c.post("/api/analysis/queue", json={"client_request_id": "not-a-uuid"})
        self.assertEqual(response.status_code, 401)

    def test_signed_in_analysis_is_accepted_into_the_durable_queue(self):
        c = TestClient(app)
        user_id = "2b8e3e0d-7b39-4f73-83b9-90ee5d979fca"
        client_request_id = "c5db7057-0bfb-4b54-855b-6f4db53c2c7a"
        queued = {
            "run_id": "628a9906-127d-46c7-af5b-b0e979e2ac42",
            "status": "queued",
            "already_queued": False,
        }
        payload = {
            "client_request_id": client_request_id,
            "field": {"lat": 24.75, "lon": 90.41, "area_ha": 0.4},
            "start_date": "2026-11-01",
            "end_date": "2026-11-30",
            "priority_choices": ["water", "soil"],
        }
        with patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test",
            },
        ), patch("fieldshift.api.app.supabase_auth.get_user", return_value={"id": user_id}), patch(
            "fieldshift.api.app.supabase_auth.queue_analysis_request", return_value=queued
        ) as queue_call:
            response = c.post(
                "/api/analysis/queue",
                headers={"Authorization": "Bearer valid-user-token"},
                json=payload,
            )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["run"]["id"], queued["run_id"])
        self.assertTrue(response.json()["queued"])
        self.assertEqual(queue_call.call_args.kwargs["access_token"], "valid-user-token")
        self.assertEqual(queue_call.call_args.kwargs["client_request_id"], client_request_id)
        self.assertNotIn("client_request_id", queue_call.call_args.kwargs["request_payload"])

    def test_live_analysis_read_routes_never_expose_process_local_run_ids(self):
        c = TestClient(app)
        paths = [
            "/api/analysis/run_private_123",
            "/api/analysis/run_private_123/strategies",
            "/api/analysis/run_private_123/strategies/strategy_1",
            "/api/analysis/run_private_123/scenarios",
            "/api/analysis/run_private_123/evidence/evidence_1",
            "/api/analysis/run_private_123/report",
        ]
        with patch("fieldshift.api.app.get_analysis") as get_live_analysis:
            for path in paths:
                response = c.get(path)
                self.assertEqual(response.status_code, 404, path)
            get_live_analysis.assert_not_called()

    def test_live_what_if_uses_only_the_client_snapshot_without_session(self):
        c = TestClient(app)
        with patch("fieldshift.api.app.what_if", return_value={"ok": True}) as what_if_call:
            response = c.post(
                "/api/analysis/run_private_123/what-if",
                json={"scenario": "dry", "field": {"id": "caller_field"}},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})
        what_if_call.assert_called_once_with(
            "run_private_123",
            {"scenario": "dry", "field": {"id": "caller_field"}},
        )

    def test_public_demo_analysis_read_remains_available(self):
        c = TestClient(app)
        demo = {
            "run": {"id": "demo_mymensingh_v3"},
            "strategies": [{"id": "strategy_1"}],
            "scenarios": [],
            "evidence": {"items": []},
        }
        with patch("fieldshift.api.app.get_analysis", return_value=demo) as get_demo:
            response = c.get("/api/analysis/demo_mymensingh_v3")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), demo)
        get_demo.assert_called_once_with("demo_mymensingh_v3")

    def test_live_analysis_is_not_retained_in_the_process_global_run_cache(self):
        raw = {"run_id": "run_private_123"}
        with patch.dict(product._RUNS, {}, clear=True), patch(
            "fieldshift.api.product._run_engine", return_value=raw
        ), patch(
            "fieldshift.api.product._make_product_response", return_value={"ok": True}
        ) as make_response:
            result = product.create_analysis({"field": {"lat": 24.75, "lon": 90.41}})
            self.assertEqual(result, {"ok": True})
            self.assertNotIn("run_private_123", product._RUNS)
            self.assertNotIn("_product_field", raw)
            self.assertEqual(make_response.call_args.args[1], {"lat": 24.75, "lon": 90.41})

    def test_live_what_if_uses_the_callers_field_snapshot_not_another_run_cache(self):
        field = {
            "id": "caller_field",
            "location": {"lat": 24.75, "lon": 90.41},
            "area_ha": 0.4,
            "land_type": "medium highland",
            "previous_crop": "Rice",
            "soil_inputs": {"pH": 6.2},
            "soil_data_source": "farmer-reported",
            "constraints": {
                "water_available_mm_season": 900,
                "irrigation_reliability": 0.8,
                "budget_bdt_ha": 100000,
                "labour_available_person_days_ha": 120,
            },
        }
        payload = {
            "scenario": "dry",
            "field": field,
            "priorities": {"water": 1.0},
            "evidence_window": {"start_date": "2025-01-01", "end_date": "2025-01-31"},
        }
        with patch(
            "fieldshift.api.product.get_analysis",
            side_effect=AssertionError("must not load another live run"),
        ), patch(
            "fieldshift.api.product.create_analysis", return_value={"ok": True}
        ) as create_call:
            result = product.what_if("run_other_user_123", payload)
        self.assertEqual(result, {"ok": True})
        created = create_call.call_args.args[0]
        self.assertEqual(created["field"]["field_id"], "caller_field")
        self.assertEqual(created["field"]["lat"], 24.75)
        self.assertEqual(created["field"]["soil"], {"pH": 6.2})
        self.assertEqual(created["field"]["farmer"]["water_available_mm_season"], 720.0)
        self.assertEqual(created["start_date"], "2025-01-01")
        self.assertEqual(created["end_date"], "2025-01-31")

    def test_auth_config_is_safe_when_not_configured(self):
        c = TestClient(app)
        with patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_PUBLISHABLE_KEY": ""}):
            response = c.get("/api/auth/config")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["configured"])
        self.assertNotIn("service_role", response.text.lower())

    def test_demo_endpoint_returns_valid_run(self):
        c = TestClient(app)
        r = c.get("/api/v3/demo")
        self.assertEqual(r.status_code, 200)
        payload = r.json()
        self.assertEqual(payload["engine_version"], "3.0.0")
        self.assertTrue(payload["validation"]["passed"])


if __name__ == "__main__":
    unittest.main()
