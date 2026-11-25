"""Tests for Gmail SMTP alert handling: success, failure, and secret redaction."""

import json
import unittest
from unittest import mock

import app.email_alerts as email_alerts


def _mock_smtp_server():
    server = mock.MagicMock()
    server.__enter__.return_value = server
    server.__exit__.return_value = False
    return server


class EmailAlertTests(unittest.TestCase):
    def setUp(self):
        self._patches = [
            mock.patch.object(email_alerts.settings, "smtp_username", "bot@example.com"),
            mock.patch.object(email_alerts.settings, "smtp_password", "smtp-secret-pass"),
            mock.patch.object(email_alerts.settings, "smtp_host", "smtp.gmail.com"),
            mock.patch.object(email_alerts.settings, "smtp_port", 587),
            mock.patch.object(email_alerts.settings, "sender_email", "sender@example.com"),
            mock.patch.object(email_alerts.settings, "email_js_service_id", ""),
            mock.patch.object(email_alerts.settings, "email_js_template_id", ""),
            mock.patch.object(email_alerts.settings, "email_js_public_key", ""),
            mock.patch.object(email_alerts.settings, "email_js_private_key", ""),
        ]
        for patcher in self._patches:
            patcher.start()

    def tearDown(self):
        for patcher in self._patches:
            patcher.stop()

    def test_success_returns_true(self):
        server = _mock_smtp_server()
        with mock.patch.object(
            email_alerts.smtplib, "SMTP", return_value=server
        ) as smtp_cls:
            self.assertTrue(
                email_alerts.send_security_alert("user@example.com", "event", "detail")
            )

        smtp_cls.assert_called_once_with("smtp.gmail.com", 587, timeout=15)
        server.starttls.assert_called_once()
        server.login.assert_called_once_with("bot@example.com", "smtp-secret-pass")
        server.send_message.assert_called_once()

    def test_send_error_is_swallowed_and_secret_redacted(self):
        server = _mock_smtp_server()
        server.starttls.side_effect = RuntimeError(
            "535 authentication failed for smtp-secret-pass"
        )
        with mock.patch.object(email_alerts.smtplib, "SMTP", return_value=server):
            with self.assertLogs("neurolock.email_alerts", level="ERROR") as logs:
                result = email_alerts.send_security_alert(
                    "user@example.com", "event", "detail"
                )
        self.assertFalse(result)
        joined = "\n".join(logs.output)
        self.assertNotIn("smtp-secret-pass", joined)
        self.assertIn("[redacted]", joined)

    def test_login_error_returns_false(self):
        server = _mock_smtp_server()
        server.login.side_effect = RuntimeError("bad credentials")
        with mock.patch.object(email_alerts.smtplib, "SMTP", return_value=server):
            with self.assertLogs("neurolock.email_alerts", level="ERROR"):
                self.assertFalse(
                    email_alerts.send_security_alert("user@example.com", "event")
                )

    def test_missing_configuration_returns_false(self):
        with mock.patch.object(email_alerts.settings, "smtp_password", ""):
            with mock.patch.object(email_alerts.smtplib, "SMTP") as smtp_cls:
                result = email_alerts.send_security_alert("user@example.com", "event")
        self.assertFalse(result)
        smtp_cls.assert_not_called()

    def test_empty_recipient_returns_false(self):
        with mock.patch.object(email_alerts.smtplib, "SMTP") as smtp_cls:
            result = email_alerts.send_security_alert("", "event")
        self.assertFalse(result)
        smtp_cls.assert_not_called()

    def test_lockout_email_contains_unlock_link(self):
        server = _mock_smtp_server()
        url = "http://localhost:8000/api/unlock?token=abc123"
        with mock.patch.object(email_alerts.smtplib, "SMTP", return_value=server):
            self.assertTrue(
                email_alerts.send_lockout_email("user@example.com", url, 12)
            )

        sent = server.send_message.call_args[0][0]
        html = sent.get_body(preferencelist=("html",)).get_content()
        plain = sent.get_body(preferencelist=("plain",)).get_content()
        self.assertIn("token=abc123", html)
        self.assertIn("Unlock my account", html)
        self.assertIn("12", html)
        self.assertIn("token=abc123", plain)

    def test_emailjs_fallback_uses_service_when_smtp_missing(self):
        with mock.patch.object(email_alerts.settings, "smtp_username", ""), \
             mock.patch.object(email_alerts.settings, "smtp_password", ""), \
             mock.patch.object(email_alerts.settings, "sender_email", ""), \
             mock.patch.object(email_alerts.settings, "email_js_service_id", "service_key"), \
             mock.patch.object(email_alerts.settings, "email_js_template_id", "template_key"), \
             mock.patch.object(email_alerts.settings, "email_js_public_key", "public_key"), \
             mock.patch.object(email_alerts, "_send_emailjs", return_value=True) as send_emailjs:
            result = email_alerts.send_security_alert(
                "user@example.com",
                "login failure",
                "3 failed sign-in attempts",
            )

        self.assertTrue(result)
        send_emailjs.assert_called_once_with(
            "user@example.com",
            "login failure",
            "3 failed sign-in attempts",
        )

    def test_emailjs_is_preferred_when_both_transports_are_configured(self):
        with mock.patch.object(email_alerts.settings, "smtp_username", "bot@example.com"), \
             mock.patch.object(email_alerts.settings, "smtp_password", "smtp-secret-pass"), \
             mock.patch.object(email_alerts.settings, "sender_email", "sender@example.com"), \
             mock.patch.object(email_alerts.settings, "email_js_service_id", "service_key"), \
             mock.patch.object(email_alerts.settings, "email_js_template_id", "template_key"), \
             mock.patch.object(email_alerts.settings, "email_js_public_key", "public_key"), \
             mock.patch.object(email_alerts, "_send_emailjs", return_value=True) as send_emailjs, \
             mock.patch.object(email_alerts.smtplib, "SMTP") as smtp_cls:
            result = email_alerts.send_security_alert(
                "user@example.com",
                "login failure",
                "3 failed sign-in attempts",
            )

        self.assertTrue(result)
        send_emailjs.assert_called_once_with(
            "user@example.com",
            "login failure",
            "3 failed sign-in attempts",
        )
        smtp_cls.assert_not_called()

    def test_emailjs_request_includes_private_key_as_access_token(self):
        with mock.patch.object(email_alerts.settings, "email_js_service_id", "service_key"), \
             mock.patch.object(email_alerts.settings, "email_js_template_id", "template_key"), \
             mock.patch.object(email_alerts.settings, "email_js_public_key", "public_key"), \
             mock.patch.object(email_alerts.settings, "email_js_private_key", "private_key"), \
             mock.patch.object(email_alerts.urllib.request, "urlopen") as urlopen:
            response = mock.MagicMock()
            response.status = 200
            response.__enter__.return_value = response
            urlopen.return_value = response

            self.assertTrue(
                email_alerts._send_emailjs("user@example.com", "login failure", "details")
            )

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["accessToken"], "private_key")
        self.assertEqual(payload["user_id"], "public_key")


if __name__ == "__main__":
    unittest.main()
