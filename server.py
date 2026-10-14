import hashlib
import hmac
import json
import mimetypes
import re
import secrets
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent
DATABASE_PATH = ROOT / "data" / "portfolio.sqlite3"
COOKIE_NAME = "portfolio_session"
SESSION_LIFETIME = 7 * 24 * 60 * 60
PASSWORD_ITERATIONS = 600_000
MAX_BODY_SIZE = 16_384
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
MONTHS_PT = (
    "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
    "Jul", "Ago", "Set", "Out", "Nov", "Dez",
)
PAGE_PATHS = {
    "/",
    "/index.html",
    "/dashboard",
    "/tasks",
    "/services",
    "/projects",
    "/register",
    "/login",
    "/access",
}
STATIC_FILES = {
    "/styles.css": ROOT / "styles.css",
    "/app.js": ROOT / "app.js",
}
DEFAULT_SERVICES = (
    (
        "landing-page",
        "Landing page",
        "Site responsivo para apresentar seu negócio, serviço ou produto.",
        "Site",
    ),
    (
        "dashboard",
        "Dashboard personalizado",
        "Painel com indicadores e visualizações para acompanhar seu negócio.",
        "Sistema",
    ),
    (
        "online-store",
        "Loja online",
        "Catálogo digital com fluxo de solicitações de compra.",
        "E-commerce",
    ),
    (
        "custom-project",
        "Projeto sob medida",
        "Conte sua ideia para receber uma proposta alinhada às suas necessidades.",
        "Personalizado",
    ),
)


def connect_database(database_path):
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(database_path=DATABASE_PATH):
    database_path = Path(database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)

    with closing(connect_database(database_path)) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS services (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                category TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS contracts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                service_id TEXT NOT NULL REFERENCES services(id),
                service_title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Solicitado',
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS contracts_created_at_idx
                ON contracts(created_at);
            CREATE INDEX IF NOT EXISTS contracts_user_id_idx
                ON contracts(user_id);

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contract_id INTEGER NOT NULL REFERENCES contracts(id)
                    ON DELETE CASCADE,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Aguardando início',
                position INTEGER NOT NULL
            );
            """
        )
        connection.executemany(
            """
            INSERT OR IGNORE INTO services (id, title, description, category)
            VALUES (?, ?, ?, ?)
            """,
            DEFAULT_SERVICES,
        )
        connection.commit()


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password, encoded_hash):
    try:
        algorithm, iterations_text, salt_hex, digest_hex = encoded_hash.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        if iterations < 1 or iterations > PASSWORD_ITERATIONS:
            return False
        salt = bytes.fromhex(salt_hex)
        expected_digest = bytes.fromhex(digest_hex)
    except (AttributeError, ValueError):
        return False

    actual_digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual_digest, expected_digest)


def token_digest(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class PortfolioHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address, request_handler, database_path=DATABASE_PATH):
        self.database_path = Path(database_path)
        super().__init__(server_address, request_handler)


class PortfolioRequestHandler(BaseHTTPRequestHandler):
    server_version = "PortfolioLocal/1.0"

    def log_message(self, format_string, *args):
        print(f"{self.address_string()} - {format_string % args}")

    def send_headers(self, status, content_type, extra_headers=()):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'; "
            "form-action 'self'",
        )
        for name, value in extra_headers:
            self.send_header(name, value)

    def send_json(self, status, payload, extra_headers=()):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_headers(
            status,
            "application/json; charset=utf-8",
            (*extra_headers, ("Content-Length", str(len(body))), ("Cache-Control", "no-store")),
        )
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status, message):
        self.send_json(status, {"error": message})

    def send_static_file(self, file_path):
        try:
            body = file_path.read_bytes()
        except FileNotFoundError:
            self.send_error_json(404, "Arquivo não encontrado.")
            return

        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in (
            "application/javascript",
            "application/json",
        ):
            content_type += "; charset=utf-8"

        self.send_headers(
            200,
            content_type,
            (("Content-Length", str(len(body))), ("Cache-Control", "no-cache")),
        )
        self.end_headers()
        self.wfile.write(body)

    def read_json_body(self):
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            self.send_error_json(415, "Envie os dados em formato JSON.")
            return None

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error_json(400, "Tamanho da solicitação inválido.")
            return None

        if content_length < 1 or content_length > MAX_BODY_SIZE:
            self.send_error_json(413, "A solicitação está vazia ou excede o limite permitido.")
            return None

        try:
            payload = json.loads(self.rfile.read(content_length))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_error_json(400, "O corpo da solicitação não contém JSON válido.")
            return None

        if not isinstance(payload, dict):
            self.send_error_json(400, "O corpo da solicitação precisa ser um objeto JSON.")
            return None
        return payload

    def current_user(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except CookieError:
            return None

        session_cookie = cookie.get(COOKIE_NAME)
        if session_cookie is None:
            return None

        with closing(connect_database(self.server.database_path)) as connection:
            return connection.execute(
                """
                SELECT users.id, users.email
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token_hash = ? AND sessions.expires_at > ?
                """,
                (token_digest(session_cookie.value), int(time.time())),
            ).fetchone()

    def set_session_cookie(self, token):
        return (
            "Set-Cookie",
            f"{COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Lax; "
            f"Max-Age={SESSION_LIFETIME}",
        )

    def create_session(self, user_id):
        token = secrets.token_urlsafe(32)
        expires_at = int(time.time()) + SESSION_LIFETIME
        with closing(connect_database(self.server.database_path)) as connection:
            with connection:
                connection.execute(
                    "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                    (token_digest(token), user_id, expires_at),
                )
        return token

    def require_user(self):
        user = self.current_user()
        if user is None:
            self.send_error_json(401, "Entre na sua conta para continuar.")
            return None
        return user

    def do_GET(self):
        path = urlsplit(self.path).path

        if path in PAGE_PATHS:
            self.send_static_file(ROOT / "index.html")
            return
        if path in STATIC_FILES:
            self.send_static_file(STATIC_FILES[path])
            return
        if path == "/api/session":
            user = self.current_user()
            self.send_json(
                200,
                {"user": {"email": user["email"]} if user else None},
            )
            return
        if path == "/api/services":
            with closing(connect_database(self.server.database_path)) as connection:
                services = connection.execute(
                    "SELECT id, title, description, category FROM services ORDER BY rowid"
                ).fetchall()
            self.send_json(200, {"services": [dict(service) for service in services]})
            return
        if path == "/api/dashboard":
            self.send_dashboard()
            return
        if path == "/api/tasks":
            user = self.require_user()
            if user is None:
                return
            self.send_tasks(user["id"])
            return

        self.send_error_json(404, "Rota não encontrada.")

    def send_dashboard(self):
        now = datetime.now(timezone.utc)
        current_month = now.strftime("%Y-%m")
        month_keys = []
        year = now.year
        month = now.month
        for _ in range(5):
            month -= 1
            if month == 0:
                month = 12
                year -= 1
        for _ in range(6):
            month_keys.append(f"{year:04d}-{month:02d}")
            month += 1
            if month == 13:
                month = 1
                year += 1

        first_month = month_keys[0]
        with closing(connect_database(self.server.database_path)) as connection:
            monthly_counts = connection.execute(
                """
                SELECT strftime('%Y-%m', created_at) AS month, COUNT(*) AS count
                FROM contracts
                WHERE created_at >= ?
                GROUP BY strftime('%Y-%m', created_at)
                """,
                (f"{first_month}-01T00:00:00+00:00",),
            ).fetchall()
            totals = connection.execute(
                """
                SELECT COUNT(*) AS total,
                    SUM(CASE WHEN strftime('%Y-%m', created_at) = ? THEN 1 ELSE 0 END)
                        AS this_month
                FROM contracts
                """,
                (current_month,),
            ).fetchone()
            service_count = connection.execute(
                "SELECT COUNT(*) AS count FROM services"
            ).fetchone()["count"]

        counts_by_month = {row["month"]: row["count"] for row in monthly_counts}
        series = [
            {
                "month": month_key,
                "label": MONTHS_PT[int(month_key[5:7]) - 1],
                "count": counts_by_month.get(month_key, 0),
            }
            for month_key in month_keys
        ]
        self.send_json(
            200,
            {
                "total": totals["total"],
                "this_month": totals["this_month"] or 0,
                "service_count": service_count,
                "series": series,
            },
        )

    def send_tasks(self, user_id):
        with closing(connect_database(self.server.database_path)) as connection:
            contracts = connection.execute(
                """
                SELECT id, service_title, description, status, created_at
                FROM contracts
                WHERE user_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (user_id,),
            ).fetchall()
            tasks = connection.execute(
                """
                SELECT tasks.contract_id, tasks.title, tasks.status
                FROM tasks
                JOIN contracts ON contracts.id = tasks.contract_id
                WHERE contracts.user_id = ?
                ORDER BY tasks.contract_id DESC, tasks.position
                """,
                (user_id,),
            ).fetchall()

        tasks_by_contract = {}
        for task in tasks:
            tasks_by_contract.setdefault(task["contract_id"], []).append(
                {"title": task["title"], "status": task["status"]}
            )

        self.send_json(
            200,
            {
                "contracts": [
                    {
                        "id": contract["id"],
                        "service_title": contract["service_title"],
                        "description": contract["description"],
                        "status": contract["status"],
                        "created_at": contract["created_at"],
                        "tasks": tasks_by_contract.get(contract["id"], []),
                    }
                    for contract in contracts
                ]
            },
        )

    def do_POST(self):
        path = urlsplit(self.path).path
        payload = self.read_json_body()
        if payload is None:
            return

        if path == "/api/register":
            self.register(payload)
            return
        if path == "/api/login":
            self.login(payload)
            return
        if path == "/api/logout":
            self.logout()
            return
        if path == "/api/contracts":
            self.create_contract(payload)
            return
        self.send_error_json(404, "Rota não encontrada.")

    def register(self, payload):
        email_value = payload.get("email")
        password = payload.get("password")
        if not isinstance(email_value, str) or not isinstance(password, str):
            self.send_error_json(400, "Informe um e-mail e uma senha.")
            return

        email = email_value.strip().casefold()
        if len(email) > 254 or not EMAIL_PATTERN.fullmatch(email):
            self.send_error_json(400, "Informe um endereço de e-mail válido.")
            return
        if len(password) < 10 or len(password) > 128:
            self.send_error_json(400, "A senha deve ter entre 10 e 128 caracteres.")
            return

        password_hash = hash_password(password)
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            with closing(connect_database(self.server.database_path)) as connection:
                with connection:
                    cursor = connection.execute(
                        """
                        INSERT INTO users (email, password_hash, created_at)
                        VALUES (?, ?, ?)
                        """,
                        (email, password_hash, created_at),
                    )
                    user_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            self.send_error_json(
                409,
                "Esse e-mail já tem cadastro. Entre na sua conta.",
            )
            return

        token = self.create_session(user_id)
        self.send_json(
            201,
            {"user": {"email": email}},
            (self.set_session_cookie(token),),
        )

    def login(self, payload):
        email_value = payload.get("email")
        password = payload.get("password")
        if (
            not isinstance(email_value, str)
            or not isinstance(password, str)
            or len(password) > 128
        ):
            self.send_error_json(400, "Informe um e-mail e uma senha válidos.")
            return

        email = email_value.strip().casefold()
        with closing(connect_database(self.server.database_path)) as connection:
            user = connection.execute(
                "SELECT id, email, password_hash FROM users WHERE email = ?",
                (email,),
            ).fetchone()

        if user is None or not verify_password(password, user["password_hash"]):
            self.send_error_json(401, "E-mail ou senha incorretos.")
            return

        token = self.create_session(user["id"])
        self.send_json(
            200,
            {"user": {"email": user["email"]}},
            (self.set_session_cookie(token),),
        )

    def logout(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except CookieError:
            cookie = SimpleCookie()
        session_cookie = cookie.get(COOKIE_NAME)
        if session_cookie is not None:
            with closing(connect_database(self.server.database_path)) as connection:
                with connection:
                    connection.execute(
                        "DELETE FROM sessions WHERE token_hash = ?",
                        (token_digest(session_cookie.value),),
                    )

        self.send_json(
            200,
            {"ok": True},
            (
                (
                    "Set-Cookie",
                    f"{COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0",
                ),
            ),
        )

    def create_contract(self, payload):
        user = self.require_user()
        if user is None:
            return

        service_id = payload.get("service_id")
        description = payload.get("description", "")
        if not isinstance(service_id, str) or not isinstance(description, str):
            self.send_error_json(400, "Os dados do serviço são inválidos.")
            return
        description = description.strip()
        if len(description) > 2_000:
            self.send_error_json(400, "A descrição deve ter no máximo 2.000 caracteres.")
            return

        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with closing(connect_database(self.server.database_path)) as connection:
            with connection:
                service = connection.execute(
                    "SELECT title FROM services WHERE id = ?",
                    (service_id,),
                ).fetchone()
                if service is None:
                    self.send_error_json(404, "O serviço selecionado não existe.")
                    return

                cursor = connection.execute(
                    """
                    INSERT INTO contracts
                        (user_id, service_id, service_title, description, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (user["id"], service_id, service["title"], description, created_at),
                )
                contract_id = cursor.lastrowid
                connection.executemany(
                    """
                    INSERT INTO tasks (contract_id, title, position)
                    VALUES (?, ?, ?)
                    """,
                    (
                        (contract_id, "Alinhamento do escopo", 1),
                        (contract_id, "Desenvolvimento do projeto", 2),
                        (contract_id, "Revisão e entrega", 3),
                    ),
                )

        self.send_json(201, {"id": contract_id, "status": "Solicitado"})


def main():
    initialize_database()
    server = PortfolioHTTPServer(("127.0.0.1", 8000), PortfolioRequestHandler)
    print("Portal iniciado em http://127.0.0.1:8000")
    print("Pressione Ctrl+C para encerrar.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando o portal...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
