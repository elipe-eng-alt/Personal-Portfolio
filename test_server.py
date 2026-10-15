import json
import ssl
import tempfile
import threading
import unittest
from contextlib import closing
from http.cookiejar import CookieJar
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

from server import (
    PortfolioHTTPServer,
    PortfolioRequestHandler,
    SMTPSettings,
    connect_database,
    deliver_pending_notifications,
    initialize_database,
    parse_public_origin,
    send_project_notification,
)


class PortfolioAPITests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "test.sqlite3"
        initialize_database(self.database_path)
        self.server = PortfolioHTTPServer(
            ("127.0.0.1", 0),
            PortfolioRequestHandler,
            database_path=self.database_path,
        )
        self.server.smtp_settings = None
        self.server_thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.server_thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        self.opener = self.make_opener()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=5)
        self.temp_dir.cleanup()

    @staticmethod
    def make_opener():
        return build_opener(HTTPCookieProcessor(CookieJar()))

    def request(self, opener, path, method="GET", payload=None, origin=None):
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"} if body is not None else {}
        if body is not None:
            headers["Origin"] = origin or self.base_url
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers=headers,
        )
        try:
            with opener.open(request) as response:
                return response.status, json.loads(response.read())
        except HTTPError as error:
            return error.code, json.loads(error.read())

    def register(self, opener, email):
        return self.request(
            opener,
            "/api/register",
            method="POST",
            payload={"email": email, "password": "strong-password-123"},
        )

    def test_registration_hashes_password_and_starts_session(self):
        status, result = self.register(self.opener, "Felipe@example.com")

        self.assertEqual(status, 201)
        self.assertEqual(result["user"]["email"], "felipe@example.com")
        session_status, session = self.request(self.opener, "/api/session")
        self.assertEqual(session_status, 200)
        self.assertEqual(session["user"]["email"], "felipe@example.com")

        with closing(connect_database(self.database_path)) as connection:
            user = connection.execute(
                "SELECT email, password_hash FROM users"
            ).fetchone()
        self.assertEqual(user["email"], "felipe@example.com")
        self.assertTrue(user["password_hash"].startswith("pbkdf2_sha256$"))
        self.assertNotIn("strong-password-123", user["password_hash"])

    def test_duplicate_email_is_rejected(self):
        first_status, _ = self.register(self.opener, "client@example.com")
        second_status, result = self.register(self.opener, "CLIENT@example.com")

        self.assertEqual(first_status, 201)
        self.assertEqual(second_status, 409)
        self.assertIn("Entre na sua conta", result["error"])

    def test_login_and_logout_manage_the_client_session(self):
        register_status, _ = self.register(self.opener, "client@example.com")
        self.assertEqual(register_status, 201)

        client = self.make_opener()
        failed_login, _ = self.request(
            client,
            "/api/login",
            method="POST",
            payload={"email": "client@example.com", "password": "wrong-password"},
        )
        self.assertEqual(failed_login, 401)

        login_status, login_result = self.request(
            client,
            "/api/login",
            method="POST",
            payload={
                "email": "CLIENT@example.com",
                "password": "strong-password-123",
            },
        )
        self.assertEqual(login_status, 200)
        self.assertEqual(login_result["user"]["email"], "client@example.com")
        _, session = self.request(client, "/api/session")
        self.assertIsNotNone(session["user"])

        logout_status, _ = self.request(
            client,
            "/api/logout",
            method="POST",
            payload={},
        )
        self.assertEqual(logout_status, 200)
        _, session = self.request(client, "/api/session")
        self.assertIsNone(session["user"])

    def test_contracts_create_tasks_and_are_private_to_each_user(self):
        anonymous_status, _ = self.request(
            self.opener,
            "/api/contracts",
            method="POST",
            payload={"service_id": "landing-page", "description": "Site para minha loja"},
        )
        self.assertEqual(anonymous_status, 401)

        register_status, _ = self.register(self.opener, "first@example.com")
        self.assertEqual(register_status, 201)
        with self.assertLogs("root", level="ERROR"):
            contract_status, _ = self.request(
                self.opener,
                "/api/contracts",
                method="POST",
                payload={
                    "service_id": "landing-page",
                    "description": "Site para minha loja",
                },
            )
        self.assertEqual(contract_status, 201)

        tasks_status, task_result = self.request(self.opener, "/api/tasks")
        self.assertEqual(tasks_status, 200)
        self.assertEqual(len(task_result["contracts"]), 1)
        contract = task_result["contracts"][0]
        self.assertEqual(contract["service_title"], "Landing page")
        self.assertEqual(len(contract["tasks"]), 3)
        self.assertEqual(contract["description"], "Site para minha loja")

        second_client = self.make_opener()
        second_register_status, _ = self.register(second_client, "second@example.com")
        self.assertEqual(second_register_status, 201)
        _, second_tasks = self.request(second_client, "/api/tasks")
        self.assertEqual(second_tasks["contracts"], [])

        _, dashboard = self.request(self.opener, "/api/dashboard")
        self.assertEqual(dashboard["total"], 1)
        self.assertEqual(sum(month["count"] for month in dashboard["series"]), 1)
        self.assertEqual(len(dashboard["series"]), 6)

        with closing(connect_database(self.database_path)) as connection:
            notification = connection.execute(
                "SELECT status, last_error FROM email_outbox"
            ).fetchone()
        self.assertEqual(notification["status"], "pending")
        self.assertEqual(notification["last_error"], "EmailNotConfiguredError")

    def test_project_request_email_uses_fixed_recipient_and_customer_reply_to(self):
        self.register(self.opener, "client@example.com")
        sent_notifications = []
        self.server.smtp_settings = SMTPSettings(
            host="smtp.gmail.com",
            port=587,
            username="felipe@example.com",
            password="test-only-password",
            recipient="felipegabrieloliveira1000@gmail.com",
        )
        self.server.email_sender = lambda settings, notification: sent_notifications.append(
            (settings, notification)
        )

        status, result = self.request(
            self.opener,
            "/api/contracts",
            method="POST",
            payload={
                "service_id": "custom-project",
                "description": "Preciso de um site para divulgar minha loja.",
                "recipient": "attacker@example.com",
            },
        )

        self.assertEqual(status, 201)
        self.assertEqual(result["email_status"], "sent")
        self.assertEqual(len(sent_notifications), 1)
        settings, notification = sent_notifications[0]
        self.assertEqual(settings.recipient, "felipegabrieloliveira1000@gmail.com")
        self.assertEqual(notification["customer_email"], "client@example.com")
        self.assertEqual(notification["service_title"], "Projeto sob medida")
        self.assertEqual(
            notification["description"],
            "Preciso de um site para divulgar minha loja.",
        )
        with closing(connect_database(self.database_path)) as connection:
            outbox = connection.execute(
                "SELECT status, sent_at FROM email_outbox"
            ).fetchone()
        self.assertEqual(outbox["status"], "sent")
        self.assertIsNotNone(outbox["sent_at"])

    @patch("server.smtplib.SMTP")
    def test_email_delivery_uses_authenticated_starttls_and_plain_text(self, smtp_factory):
        client = smtp_factory.return_value.__enter__.return_value
        notification = {
            "contract_id": 27,
            "service_title": "Projeto sob medida",
            "description": "Quero um site para meu negócio.",
            "created_at": "2026-10-15T10:00:00+00:00",
            "customer_email": "cliente@example.com",
        }
        settings = SMTPSettings(
            host="smtp.gmail.com",
            port=587,
            username="felipe@example.com",
            password="test-only-password",
            recipient="felipegabrieloliveira1000@gmail.com",
        )

        send_project_notification(settings, notification)

        smtp_factory.assert_called_once_with("smtp.gmail.com", 587, timeout=15)
        client.starttls.assert_called_once()
        self.assertIsInstance(
            client.starttls.call_args.kwargs["context"],
            ssl.SSLContext,
        )
        client.login.assert_called_once_with("felipe@example.com", "test-only-password")
        message = client.send_message.call_args.args[0]
        self.assertEqual(message["To"], "felipegabrieloliveira1000@gmail.com")
        self.assertEqual(message["Reply-To"], "cliente@example.com")
        self.assertEqual(message["Subject"], "Nova solicitação de projeto #27: Projeto sob medida")
        self.assertIn("Quero um site para meu negócio.", message.get_content())

    def test_pending_email_is_retried_after_smtp_becomes_available(self):
        self.register(self.opener, "client@example.com")
        with self.assertLogs("root", level="ERROR"):
            _, first_result = self.request(
                self.opener,
                "/api/contracts",
                method="POST",
                payload={
                    "service_id": "dashboard",
                    "description": "Painel para minha empresa.",
                },
            )
        self.assertEqual(first_result["email_status"], "pending")

        self.server.smtp_settings = SMTPSettings(
            host="smtp.gmail.com",
            port=587,
            username="felipe@example.com",
            password="test-only-password",
            recipient="felipegabrieloliveira1000@gmail.com",
        )
        sent_notifications = []
        self.server.email_sender = lambda settings, notification: sent_notifications.append(
            notification
        )
        with closing(connect_database(self.database_path)) as connection:
            with connection:
                connection.execute("UPDATE email_outbox SET next_attempt_at = 0")

        deliver_pending_notifications(self.server)

        self.assertEqual(len(sent_notifications), 1)
        with closing(connect_database(self.database_path)) as connection:
            outbox = connection.execute(
                "SELECT status FROM email_outbox"
            ).fetchone()
        self.assertEqual(outbox["status"], "sent")

    def test_cross_origin_requests_are_rejected(self):
        status, result = self.request(
            self.opener,
            "/api/register",
            method="POST",
            payload={"email": "client@example.com", "password": "strong-password-123"},
            origin="https://attacker.example",
        )

        self.assertEqual(status, 403)
        self.assertEqual(result["error"], "Origem da solicitação inválida.")

    def test_https_origin_requires_exact_domain_and_marks_session_cookies_secure(self):
        self.server.public_origin = parse_public_origin(
            "https://personal-portfolio-0lg6.onrender.com"
        )
        handler = object.__new__(PortfolioRequestHandler)
        handler.server = self.server
        handler.headers = {
            "Origin": "https://personal-portfolio-0lg6.onrender.com",
            "Host": "personal-portfolio-0lg6.onrender.com",
        }

        self.assertTrue(handler.has_valid_request_origin())
        self.assertIn("; Secure", handler.set_session_cookie("session-token")[1])
        self.assertIn("; Secure", handler.clear_session_cookie()[1])

        handler.headers["Origin"] = "http://personal-portfolio-0lg6.onrender.com"
        self.assertFalse(handler.has_valid_request_origin())
        handler.headers["Origin"] = "https://attacker.example"
        self.assertFalse(handler.has_valid_request_origin())

    def test_public_origin_rejects_paths_and_credentials(self):
        for origin in (
            "https://portfolio.example.com/path",
            "https://user:password@portfolio.example.com",
            "file:///portfolio.example.com",
        ):
            with self.subTest(origin=origin):
                with self.assertRaises(ValueError):
                    parse_public_origin(origin)

    def test_project_requests_are_rate_limited_per_client(self):
        self.register(self.opener, "client@example.com")
        self.server.smtp_settings = SMTPSettings(
            host="smtp.gmail.com",
            port=587,
            username="felipe@example.com",
            password="test-only-password",
            recipient="felipegabrieloliveira1000@gmail.com",
        )
        self.server.email_sender = lambda settings, notification: None

        for request_number in range(5):
            status, _ = self.request(
                self.opener,
                "/api/contracts",
                method="POST",
                payload={
                    "service_id": "landing-page",
                    "description": f"Projeto {request_number}",
                },
            )
            self.assertEqual(status, 201)

        status, result = self.request(
            self.opener,
            "/api/contracts",
            method="POST",
            payload={"service_id": "landing-page", "description": "Sexto projeto"},
        )

        self.assertEqual(status, 429)
        self.assertIn("limite de solicitações", result["error"])

    def test_invalid_registration_data_is_rejected(self):
        status, result = self.request(
            self.opener,
            "/api/register",
            method="POST",
            payload={"email": "not-an-email", "password": "short"},
        )

        self.assertEqual(status, 400)
        self.assertIn("e-mail válido", result["error"])


if __name__ == "__main__":
    unittest.main()
