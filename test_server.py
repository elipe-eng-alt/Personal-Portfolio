import json
import tempfile
import threading
import unittest
from contextlib import closing
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

from server import (
    PortfolioHTTPServer,
    PortfolioRequestHandler,
    connect_database,
    initialize_database,
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

    def request(self, opener, path, method="GET", payload=None):
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers={"Content-Type": "application/json"} if body is not None else {},
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
        contract_status, _ = self.request(
            self.opener,
            "/api/contracts",
            method="POST",
            payload={"service_id": "landing-page", "description": "Site para minha loja"},
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
