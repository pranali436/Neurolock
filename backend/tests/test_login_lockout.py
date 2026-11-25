"""Unit tests for the temporary password lockout on POST /api/login.

The Supabase clients and SMTP email call are replaced with in-memory fakes so the
lockout decision logic can be exercised without touching the live project.
"""

import unittest
from unittest import mock

from fastapi.testclient import TestClient


def _load_main():
    import app.main as main

    return main


class _Response:
    def __init__(self, data):
        self.data = data


class _RpcCall:
    def __init__(self, handler, name, params):
        self._handler = handler
        self._name = name
        self._params = params

    def execute(self):
        return _Response(self._handler(self._name, self._params))


class _Table:
    def __init__(self, name, admin):
        self.name = name
        self._admin = admin

    def insert(self, data):
        self._admin.inserted.append((self.name, data))
        return self

    def execute(self):
        return _Response([])


class FakeAdmin:
    def __init__(self, handler):
        self._handler = handler
        self.rpc_calls = []
        self.inserted = []

    def rpc(self, name, params=None):
        self.rpc_calls.append((name, params))
        return _RpcCall(self._handler, name, params)

    def table(self, name):
        return _Table(name, self)


class FakeSignIn:
    def __init__(self, behavior):
        self._behavior = behavior
        self.calls = []

    def sign_in_with_password(self, credentials):
        self.calls.append(credentials)
        return self._behavior(credentials)


class FakeAuthClient:
    def __init__(self, behavior):
        self.sign_in = FakeSignIn(behavior)
        self.auth = self.sign_in


class FakeUser:
    def __init__(self, uid, email):
        self.id = uid
        self.email = email


class FakeSession:
    def __init__(self):
        self.access_token = "access-token"
        self.refresh_token = "refresh-token"


class FakeAuthResponse:
    def __init__(self, uid="user-1", email="user@example.com"):
        self.user = FakeUser(uid, email)
        self.session = FakeSession()


class LoginLockoutTests(unittest.TestCase):
    def setUp(self):
        self.main = _load_main()
        self.client = TestClient(self.main.app)

        self.rpc_log = []
        self.lockout_response = []
        self.record_response = []
        self.reset_response = []
        self.lockout_error = None
        self.auth_error = None

        self.admin = FakeAdmin(self._rpc_handler)
        self.auth_client = FakeAuthClient(self._auth_handler)

        self._patches = [
            mock.patch.object(self.main, "admin", self.admin),
            mock.patch.object(self.main, "auth_client", self.auth_client),
            mock.patch.object(self.main, "send_security_alert", lambda *a, **k: True),
        ]
        for patcher in self._patches:
            patcher.start()

    def tearDown(self):
        for patcher in self._patches:
            patcher.stop()

    def _rpc_handler(self, name, params):
        self.rpc_log.append((name, params))
        if name == "get_password_lockout_by_email":
            if self.lockout_error is not None:
                raise self.lockout_error
            return self.lockout_response
        if name == "record_password_failure_by_email":
            return self.record_response
        if name == "reset_auth_failure":
            return self.reset_response
        return []

    def _auth_handler(self, credentials):
        if self.auth_error is not None:
            raise self.auth_error
        return FakeAuthResponse()

    def _login(self, email="user@example.com", password="s3cret-pass"):
        return self.client.post(
            "/api/login",
            json={"email": email, "password": password},
        )

    def _rpc_names(self):
        return [name for name, _ in self.rpc_log]

    def test_locked_account_returns_423_before_authentication(self):
        self.lockout_response = [
            {"locked": True, "failure_count": 3, "retry_after_seconds": 300}
        ]

        response = self._login()

        self.assertEqual(response.status_code, 423)
        self.assertIn("locked", response.json()["detail"].lower())
        self.assertEqual(response.headers.get("retry-after"), "300")
        self.assertIn("5 minute", response.json()["detail"])
        # Authentication must not be attempted while locked.
        self.assertEqual(self.auth_client.sign_in.calls, [])
        self.assertEqual(self._rpc_names()[0], "get_password_lockout_by_email")
        self.assertIn(
            ("get_password_lockout_by_email", {"p_email": "user@example.com"}),
            self.rpc_log,
        )

    def test_lockout_message_rounds_partial_minutes_up(self):
        self.lockout_response = [
            {"locked": True, "failure_count": 5, "retry_after_seconds": 61}
        ]

        response = self._login()

        self.assertEqual(response.status_code, 423)
        self.assertIn("2 minute", response.json()["detail"])

    def test_expired_window_is_not_locked_and_auth_proceeds(self):
        self.lockout_response = [
            {"locked": False, "failure_count": 4, "retry_after_seconds": 0}
        ]
        self.auth_error = RuntimeError("Invalid login credentials")

        response = self._login()

        self.assertEqual(response.status_code, 401)
        self.assertEqual(len(self.auth_client.sign_in.calls), 1)

    def test_wrong_password_records_a_failure(self):
        self.lockout_response = []
        self.auth_error = RuntimeError("Invalid login credentials")

        response = self._login()

        self.assertEqual(response.status_code, 401)
        self.assertIn("record_password_failure_by_email", self._rpc_names())
        self.assertIn(
            ("record_password_failure_by_email", {"p_email": "user@example.com"}),
            self.rpc_log,
        )

    def test_unregistered_email_is_not_locked(self):
        # The RPC returns no rows for an unknown email, so the request proceeds.
        self.lockout_response = []
        self.auth_error = RuntimeError("Invalid login credentials")

        response = self._login(email="nobody@example.invalid")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(self._rpc_names()[0], "get_password_lockout_by_email")

    def test_successful_login_resets_the_counter(self):
        self.lockout_response = []
        self.auth_error = None

        response = self._login()

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            ("reset_auth_failure", {"p_user_id": "user-1", "p_failure_type": "password"}),
            self.rpc_log,
        )

    def test_lockout_check_error_fails_open(self):
        self.lockout_error = RuntimeError("database unavailable")
        self.auth_error = None

        response = self._login()

        # A broken lockout check must not block a legitimate sign-in.
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.auth_client.sign_in.calls), 1)

    def test_unconfirmed_email_returns_actionable_403(self):
        class _UnconfirmedError(Exception):
            code = "email_not_confirmed"

        self.lockout_response = []
        self.auth_error = _UnconfirmedError("Email not confirmed")

        response = self._login()

        self.assertEqual(response.status_code, 403)
        self.assertIn("confirm", response.json()["detail"].lower())
        # An unconfirmed email must never be counted as a password failure.
        self.assertNotIn("record_password_failure_by_email", self._rpc_names())

    def test_unexpected_auth_error_is_reported_as_unavailable(self):
        self.lockout_response = []
        self.auth_error = RuntimeError("network unavailable")

        response = self._login()

        self.assertEqual(response.status_code, 503)
        self.assertNotIn("record_password_failure_by_email", self._rpc_names())


if __name__ == "__main__":
    unittest.main()
