from __future__ import annotations

import unittest

from fieldshift.v3.run_lifecycle import classify_run_readiness, source_key_for


class TestRunLifecycle(unittest.TestCase):
    def test_source_key_for_current_core_weather_name(self) -> None:
        self.assertEqual(source_key_for("NASA POWER Daily weather"), "nasa_power_daily_weather")

    def test_pending_supplemental_source_keeps_run_preliminary(self) -> None:
        result = classify_run_readiness([
            {"name": "NASA POWER Daily weather", "status": "available"},
            {"name": "NASA SMAP", "status": "pending"},
        ])
        self.assertEqual(result["status"], "preliminary_ready")
        self.assertFalse(result["is_final"])
        self.assertTrue(result["prediction_eligible"])
        self.assertEqual(result["pending_sources"], ["NASA SMAP"])

    def test_missing_core_weather_never_becomes_final(self) -> None:
        result = classify_run_readiness([
            {"name": "NASA POWER Daily weather", "status": "unavailable"},
            {"name": "Synthetic fallback weather", "status": "fallback"},
        ])
        self.assertEqual(result["status"], "preliminary_ready")
        self.assertFalse(result["is_final"])
        self.assertFalse(result["prediction_eligible"])
        self.assertIn("NASA POWER Daily weather", result["missing_required_sources"])

    def test_settled_optional_gaps_become_final_with_gaps(self) -> None:
        result = classify_run_readiness([
            {"name": "NASA POWER Daily weather", "status": "available"},
            {"name": "NASA SMAP", "status": "not_configured"},
            {"name": "NASA GPM IMERG", "status": "partial"},
        ])
        self.assertEqual(result["status"], "final_with_gaps")
        self.assertTrue(result["is_final"])
        self.assertTrue(result["prediction_eligible"])
        self.assertCountEqual(result["gap_sources"], ["NASA SMAP", "NASA GPM IMERG"])

    def test_all_requested_sources_ready_becomes_final_ready(self) -> None:
        result = classify_run_readiness([
            {"name": "NASA POWER Daily weather", "status": "available"},
            {"name": "NASA SMAP", "status": "available"},
            {"name": "NASA GPM IMERG", "status": "available"},
        ])
        self.assertEqual(result["status"], "final_ready")
        self.assertTrue(result["is_final"])
        self.assertEqual(result["gap_sources"], [])

    def test_missing_core_without_result_waits_for_data(self) -> None:
        result = classify_run_readiness(
            [{"name": "NASA POWER Daily weather", "status": "pending"}],
            result_available=False,
        )
        self.assertEqual(result["status"], "waiting_for_data")
        self.assertFalse(result["is_final"])
        self.assertFalse(result["prediction_eligible"])

    def test_ready_evidence_without_computed_result_stays_running(self) -> None:
        result = classify_run_readiness(
            [{"name": "NASA POWER Daily weather", "status": "available"}],
            result_available=False,
        )
        self.assertEqual(result["status"], "running")
        self.assertFalse(result["is_final"])
        self.assertFalse(result["prediction_eligible"])

    def test_unknown_source_state_is_not_silently_accepted(self) -> None:
        result = classify_run_readiness([
            {"name": "NASA POWER Daily weather", "status": "available"},
            {"name": "Future dataset", "status": "future_state"},
        ])
        self.assertEqual(result["status"], "final_with_gaps")
        self.assertEqual(result["gap_sources"], ["Future dataset"])


if __name__ == "__main__":
    unittest.main()
