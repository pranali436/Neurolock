"""Access-control tests after typing verification was removed from sign-in.

Typing verification (and its signed token) is no longer part of the flow. These
tests prove:
  * a valid password session (first factor) can use protected endpoints,
  * a biometric token is neither required nor able to change access,
  * a missing/invalid session is still rejected with 401,
  * the dashboard score endpoint returns a real stored score, or null.
"""

import unittest
from unittest import mock

from fastapi.testclient import TestClient

import app.auth as auth_module
import app.main as main

USER = {"id": "user-1", "email": "user@example.com"}
VECTOR = {"mean_dwell": 80.0, "mean_flight": 400.0, "std_flight": 100.0, "count": 36.0}


class _Response:
    def __init__(self, data):
        self.data = data


class _Table:
    """Minimal fluent fake for the Supabase table API used by the endpoints."""

    def __init__(self, admin, name):
        self._admin = admin
        self._name = name

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def maybe_single(self): return self

    def insert(self, data):
        self._admin.inserted.append((self._name, data))
        return self

    def upsert(self, data):
        self._admin.upserted.append((self._name, data))
        return self

    def delete(self):
        return self

    def execute(self):
        if self._name == "security_events":
            return _Response(list(self._admin.events))
        return _Response([])


class FakeAdmin:
    def __init__(self, events=None):
        self.events = events or []
        self.inserted = []
        self.upserted = []

    def table(self, name):
        return _Table(self, name)

    def rpc(self, name, params=None):
        return _Table(self, "rpc")


class PasswordOnlyAccessTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.admin = FakeAdmin()
        self._patches = [
            mock.patch.object(main, "admin", self.admin),
            mock.patch.object(main, "record_failure_and_alert", lambda *a, **k: None),
        ]
        for patcher in self._patches:
            patcher.start()
        main.app.dependency_overrides[main.current_user] = lambda: dict(USER)

    def tearDown(self):
        for patcher in self._patches:
            patcher.stop()
        main.app.dependency_overrides.pop(main.current_user, None)

    def test_files_accessible_with_password_session_only(self):
        response = self.client.get("/api/files")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["files"], [])

    def test_security_alert_accessible_with_password_session_only(self):
        response = self.client.post(
            "/api/security-alert", json={"event": "x", "detail": "y"}
        )
        self.assertEqual(response.status_code, 200)

    def test_biometric_token_is_not_required(self):
        without = self.client.get("/api/files")
        with_bogus = self.client.get(
            "/api/files", headers={"X-Biometric-Token": "bogus"}
        )
        self.assertEqual(without.status_code, 200)
        self.assertEqual(with_bogus.status_code, 200)

    def test_first_factor_endpoints_still_work(self):
        self.assertEqual(self.client.get("/api/biometric/status").status_code, 200)
        self.assertEqual(self.client.get("/api/auth/status").status_code, 200)

    def test_reenrollment_allowed_without_token(self):
        payload = {"samples": [{"features": VECTOR}] * 3}
        response = self.client.post("/api/enrollment", json=payload)
        self.assertEqual(response.status_code, 200)

    def test_enrollment_requires_three_samples(self):
        payload = {"samples": [{"features": VECTOR}] * 2}
        response = self.client.post("/api/enrollment", json=payload)
        self.assertEqual(response.status_code, 422)


class LastScoreTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        main.app.dependency_overrides[main.current_user] = lambda: dict(USER)

    def tearDown(self):
        main.app.dependency_overrides.pop(main.current_user, None)

    def _get(self, events):
        with mock.patch.object(main, "admin", FakeAdmin(events=events)):
            return self.client.get("/api/biometric/last-score")

    def test_returns_none_when_never_verified(self):
        response = self._get([])
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["accuracy"])

    def test_returns_the_real_stored_score(self):
        response = self._get([{"details": {"accuracy": 0.83}, "created_at": "2026-01-02"}])
        self.assertEqual(response.status_code, 200)
        self.assertAlmostEqual(response.json()["accuracy"], 0.83)

    def test_malformed_stored_score_is_not_invented(self):
        response = self._get([{"details": {"accuracy": "high"}}])
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["accuracy"])


class SessionTokenTests(unittest.TestCase):
    """The real `current_user` dependency (no override) still requires a session."""

    def setUp(self):
        self.client = TestClient(main.app)

    def test_missing_authorization_header_is_401(self):
        self.assertEqual(self.client.get("/api/files").status_code, 401)
        self.assertEqual(self.client.get("/api/biometric/last-score").status_code, 401)

    def test_non_bearer_authorization_is_401(self):
        response = self.client.get("/api/files", headers={"Authorization": "Basic abc"})
        self.assertEqual(response.status_code, 401)

    def test_invalid_bearer_token_is_401(self):
        fake = mock.MagicMock()
        fake.auth.get_user.side_effect = Exception("invalid jwt")
        with mock.patch.object(auth_module, "auth_client", fake):
            response = self.client.get(
                "/api/files", headers={"Authorization": "Bearer invalid"}
            )
        self.assertEqual(response.status_code, 401)

    def test_valid_session_reaches_protected_endpoint(self):
        user = mock.MagicMock()
        user.id = USER["id"]
        user.email = USER["email"]
        auth_response = mock.MagicMock()
        auth_response.user = user
        fake = mock.MagicMock()
        fake.auth.get_user.return_value = auth_response
        with mock.patch.object(auth_module, "auth_client", fake), \
             mock.patch.object(main, "admin", FakeAdmin()):
            response = self.client.get(
                "/api/files", headers={"Authorization": "Bearer good"}
            )
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
