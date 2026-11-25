"""Tests for the typing-rhythm accuracy threshold on POST /api/biometric/verify.

The Supabase admin client and the failure/alert hook are replaced with in-memory
fakes so the 70% accuracy decision can be exercised without the live project.
"""

import os
import unittest
from unittest import mock

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.biometrics import summarize, distance, validate_features

SCALES = {"mean_dwell": 120.0, "mean_flight": 250.0, "std_flight": 200.0, "count": 20.0}


class _Response:
    def __init__(self, data):
        self.data = data


class _Table:
    def __init__(self, admin, name, vector):
        self._admin = admin
        self._name = name
        self._vector = vector

    def select(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def maybe_single(self):
        return self

    def insert(self, data):
        self._admin.inserted.append((self._name, data))
        return self

    def execute(self):
        if self._name == "keystroke_templates":
            return _Response({"feature_vector": self._vector} if self._vector is not None else None)
        return _Response([])


class _Rpc:
    def __init__(self, admin, name, params):
        self._admin = admin
        self._name = name
        self._params = params

    def execute(self):
        self._admin.rpc_calls.append((self._name, self._params))
        return _Response([])


class FakeAdmin:
    def __init__(self, vector):
        self._vector = vector
        self.inserted = []
        self.rpc_calls = []

    def table(self, name):
        return _Table(self, name, self._vector)

    def rpc(self, name, params=None):
        return _Rpc(self, name, params)


class BiometricThresholdTests(unittest.TestCase):
    def setUp(self):
        import app.main as main

        self.main = main
        self.client = TestClient(main.app)
        self.vector = {"mean_dwell": 80.0, "mean_flight": 400.0, "std_flight": 100.0, "count": 36.0}
        self.admin = FakeAdmin(self.vector)
        self.failures = []
        self._patches = [
            mock.patch.object(main, "admin", self.admin),
            mock.patch.object(
                main,
                "record_failure_and_alert",
                lambda user, kind: self.failures.append((user["id"], kind)),
            ),
            # Pin the threshold so these tests are independent of the local .env
            # development value; configurability is covered separately below.
            mock.patch.object(main.settings, "biometric_accuracy_threshold", 0.70),
        ]
        for patcher in self._patches:
            patcher.start()
        main.app.dependency_overrides[main.current_user] = lambda: {
            "id": "user-1",
            "email": "user@example.com",
        }

    def tearDown(self):
        for patcher in self._patches:
            patcher.stop()
        self.main.app.dependency_overrides.pop(self.main.current_user, None)

    def _verify(self, features):
        samples = [{"features": sample} for sample in features] if isinstance(features, list) else [{"features": features}] * 3
        return self.client.post("/api/biometric/verify", json={"samples": samples})

    def _features_at(self, fraction):
        return {k: self.vector[k] + fraction * SCALES[k] for k in SCALES}

    def test_missing_enrollment_returns_409(self):
        self.admin._vector = None
        response = self._verify(dict(self.vector))
        self.assertEqual(response.status_code, 409)

    def test_verification_requires_three_samples(self):
        response = self.client.post(
            "/api/biometric/verify",
            json={"samples": [{"features": dict(self.vector)}] * 2},
        )
        self.assertEqual(response.status_code, 422)

    def test_exact_match_passes_with_full_accuracy(self):
        response = self._verify(dict(self.vector))
        self.assertEqual(response.status_code, 200)
        self.assertAlmostEqual(response.json()["accuracy"], 1.0, places=3)
        self.assertEqual(response.json()["required_accuracy"], 0.70)

    def test_seventy_percent_accuracy_passes_at_the_boundary(self):
        response = self._verify(self._features_at(0.30))
        self.assertEqual(response.status_code, 200)
        self.assertAlmostEqual(response.json()["accuracy"], 0.70, places=2)
        self.assertEqual(self.admin.rpc_calls[0][0], "reset_auth_failure")

    def test_three_sample_verification_scores_the_median_features(self):
        response = self._verify([
            self._features_at(0.0),
            self._features_at(0.30),
            self._features_at(0.60),
        ])
        self.assertEqual(response.status_code, 200)
        self.assertAlmostEqual(response.json()["accuracy"], 0.70, places=2)

    def test_below_seventy_percent_accuracy_fails(self):
        response = self._verify(self._features_at(0.40))
        self.assertEqual(response.status_code, 403)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "biometric_mismatch")
        self.assertIn("70%", detail["message"])
        self.assertAlmostEqual(detail["accuracy"], 0.60, places=2)
        self.assertEqual(detail["required_accuracy"], 0.70)
        self.assertEqual(self.failures, [("user-1", "biometric")])

    def test_failure_reports_actual_score_and_required_threshold(self):
        response = self._verify(self._features_at(0.50))
        self.assertEqual(response.status_code, 403)
        detail = response.json()["detail"]
        self.assertAlmostEqual(detail["accuracy"], 0.50, places=2)
        self.assertEqual(detail["required_accuracy"], 0.70)
        self.assertIn("50%", detail["message"])
        self.assertIn("70%", detail["message"])
        # A mismatch must never be reported as a missing/expired second factor,
        # which would otherwise trigger the step-up redirect.
        self.assertNotEqual(detail["code"], "biometric_required")

    def test_threshold_is_configurable(self):
        with mock.patch.object(self.main.settings, "biometric_accuracy_threshold", 0.60):
            # 65% fails the strict 70% default but passes the tolerant value.
            passed = self._verify(self._features_at(0.35))
            self.assertEqual(passed.status_code, 200)
            self.assertAlmostEqual(passed.json()["required_accuracy"], 0.60, places=2)
            failed = self._verify(self._features_at(0.50))
            self.assertEqual(failed.status_code, 403)
            self.assertEqual(failed.json()["detail"]["required_accuracy"], 0.60)

    def test_insufficient_features_fail_closed_with_400(self):
        response = self._verify({"mean_dwell": 80.0})
        self.assertEqual(response.status_code, 400)
        # Insufficient data must never be approved and must not reset failures.
        self.assertEqual(self.failures, [])
        self.assertEqual(self.admin.rpc_calls, [])

    def test_empty_features_fail_closed_with_400(self):
        response = self._verify({})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.failures, [])

    def test_non_numeric_features_fail_closed_with_400(self):
        response = self._verify({**self.vector, "mean_dwell": "fast"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.failures, [])

    def test_missing_profile_precedes_scoring(self):
        # Even with malformed probe data, a missing profile must return 409.
        self.admin._vector = None
        response = self._verify({})
        self.assertEqual(response.status_code, 409)


class BiometricsUnitTests(unittest.TestCase):
    def _sample(self, dwell, flight, std, count):
        return {
            "features": {
                "mean_dwell": dwell,
                "mean_flight": flight,
                "std_flight": std,
                "count": count,
            }
        }

    def test_summarize_returns_per_feature_median(self):
        vector = summarize([
            self._sample(80.0, 400.0, 100.0, 36.0),
            self._sample(100.0, 500.0, 120.0, 36.0),
        ])
        self.assertEqual(vector, {
            "mean_dwell": 90.0,
            "mean_flight": 450.0,
            "std_flight": 110.0,
            "count": 36.0,
        })

    def test_summarize_requires_two_samples(self):
        with self.assertRaises(HTTPException) as ctx:
            summarize([self._sample(80.0, 400.0, 100.0, 36.0)])
        self.assertEqual(ctx.exception.status_code, 400)

    def test_summarize_rejects_incomplete_sample(self):
        with self.assertRaises(HTTPException) as ctx:
            summarize([
                self._sample(80.0, 400.0, 100.0, 36.0),
                {"features": {"mean_dwell": 90.0}},
            ])
        self.assertEqual(ctx.exception.status_code, 400)

    def test_validate_features_rejects_missing_and_non_numeric(self):
        for bad in ({}, {"mean_dwell": 1.0}, {**({"mean_dwell": 1, "mean_flight": 2, "std_flight": 3, "count": None})}):
            with self.assertRaises(HTTPException) as ctx:
                validate_features(bad)
            self.assertEqual(ctx.exception.status_code, 400)

    def test_validate_features_normalizes_to_floats(self):
        vector = validate_features({"mean_dwell": 1, "mean_flight": 2, "std_flight": 3, "count": 4})
        self.assertEqual(vector, {"mean_dwell": 1.0, "mean_flight": 2.0, "std_flight": 3.0, "count": 4.0})

    def test_distance_is_zero_for_identical_vectors(self):
        vector = {"mean_dwell": 80.0, "mean_flight": 400.0, "std_flight": 100.0, "count": 36.0}
        self.assertEqual(distance(vector, dict(vector)), 0.0)

    def test_accuracy_formula_for_a_single_offset_feature(self):
        stored = {"mean_dwell": 80.0, "mean_flight": 400.0, "std_flight": 100.0, "count": 36.0}
        probe = dict(stored)
        # Half the dwell scale (120) -> 0.5 on one of four features -> distance 0.125.
        probe["mean_dwell"] = 80.0 + 0.5 * 120.0
        self.assertAlmostEqual(distance(stored, probe), 0.125, places=6)

    def test_distance_caps_each_feature_at_one(self):
        stored = {"mean_dwell": 80.0, "mean_flight": 400.0, "std_flight": 100.0, "count": 36.0}
        probe = {"mean_dwell": 80.0 + 100000.0, "mean_flight": 400.0 - 100000.0, "std_flight": 100.0 + 100000.0, "count": 36.0 + 100000.0}
        self.assertAlmostEqual(distance(stored, probe), 1.0, places=6)


class ThresholdConfigTests(unittest.TestCase):
    """BIOMETRIC_ACCURACY_THRESHOLD drives the setting; the code default stays strict."""

    def _settings(self):
        from app.config import Settings

        return Settings(
            _env_file=None,
            supabase_url="https://example.supabase.co",
            supabase_anon_key="anon",
            supabase_service_role_key="service",
        )

    def test_default_is_strict_when_env_unset(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            settings = self._settings()
        self.assertAlmostEqual(settings.biometric_accuracy_threshold, 0.70)

    def test_env_var_overrides_default(self):
        with mock.patch.dict(os.environ, {"BIOMETRIC_ACCURACY_THRESHOLD": "0.61"}):
            settings = self._settings()
        self.assertAlmostEqual(settings.biometric_accuracy_threshold, 0.61)


if __name__ == "__main__":
    unittest.main()
