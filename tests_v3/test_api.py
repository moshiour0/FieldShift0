from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("FIELD_SHIFT_LIVE_NASA", "0")
from fastapi.testclient import TestClient

from fieldshift.api.app import app


class TestAPI(unittest.TestCase):
    def test_health(self):
        c = TestClient(app)
        r = c.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["engine"], "3.0.0")

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
