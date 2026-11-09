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
