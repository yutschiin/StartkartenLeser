"""Loopback HTTP boundary for the bundled Material UI application."""

from __future__ import annotations

from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import logging
import mimetypes
from pathlib import Path
import secrets
import sqlite3
from urllib.parse import urlsplit

from startkartenleser.application.ports import ConcurrentCardUpdate
from startkartenleser.application.use_cases import UseCaseError
from startkartenleser.browser_workflow import BrowserError, BrowserWorkflow, identifier, integer
from startkartenleser.domain.rules import InvalidCardTransition
from startkartenleser.infrastructure.image_pipeline import ImageInputError
from startkartenleser.infrastructure.sqlite_repositories import CleanupPendingError


LOGGER = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "web_static"
MAX_BODY = 28 * 1024 * 1024


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"unsupported JSON type: {type(value).__name__}")


class BrowserServer(ThreadingHTTPServer):
    daemon_threads = False

    def __init__(
        self, workflow: BrowserWorkflow, port: int = 0, *, static: Path = STATIC,
    ) -> None:
        if not (static / "index.html").is_file():
            raise RuntimeError(workflow.text.text("browser.missing_build"))
        self.workflow = workflow
        self.static = static.resolve()
        self.token = secrets.token_urlsafe(32)
        super().__init__(("127.0.0.1", port), Handler)
        self.origin = f"http://127.0.0.1:{self.server_port}"
        self.launch_url = f"{self.origin}/#{self.token}"


class Handler(BaseHTTPRequestHandler):
    server: BrowserServer

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, format: str, *args: object) -> None:
        # URLs, card content, image names and tokens are not access-log data.
        return

    def send_data(
        self, status: int, data: bytes, content_type: str, *, filename: str | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(self), microphone=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'; "
            "font-src 'self'; object-src 'none'; base-uri 'none'; "
            "frame-ancestors 'none'; form-action 'none'",
        )
        if filename is not None:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, status: int, payload: object) -> None:
        self.send_data(
            status, json.dumps(payload, ensure_ascii=False, default=_json_default).encode(),
            "application/json; charset=utf-8",
        )

    def check_request(self) -> None:
        if self.headers.get("Host") != urlsplit(self.server.origin).netloc:
            raise BrowserError(403, "browser.forbidden")
        origin = self.headers.get("Origin")
        if origin is not None and origin != self.server.origin:
            raise BrowserError(403, "browser.forbidden")
        if self.command != "GET" and origin != self.server.origin:
            raise BrowserError(403, "browser.forbidden")
        if urlsplit(self.path).path.startswith("/api/"):
            token = self.headers.get("X-App-Token", "")
            if not token.isascii() or not secrets.compare_digest(token, self.server.token):
                raise BrowserError(403, "browser.forbidden")

    def do_GET(self) -> None:
        self.dispatch()

    def do_POST(self) -> None:
        self.dispatch()

    def do_PATCH(self) -> None:
        self.dispatch()

    def do_DELETE(self) -> None:
        self.dispatch()

    def dispatch(self) -> None:
        try:
            self.check_request()
            path = urlsplit(self.path).path
            payload = self.json_body() if self.command in ("POST", "PATCH") else {}
            # Recognition owns its own lock, not the human-write lock.
            if self.command == "POST" and path.endswith("/recognize"):
                parts = path.strip("/").split("/")
                if len(parts) != 4 or parts[:2] != ["api", "cards"]:
                    raise BrowserError(404, "browser.not_found")
                self.send_json(200, self.server.workflow.recognize(parts[2], payload))
            else:
                with self.server.workflow.lock:
                    self.route(path, payload)
        except BrowserError as error:
            self.send_error_json(error.status, error.key)
        except ConcurrentCardUpdate:
            self.send_error_json(409, "error.card_changed")
        except UseCaseError as error:
            self.send_error_json(409, error.localization_key)
        except ImageInputError as error:
            self.send_error_json(400, error.localization_key)
        except InvalidCardTransition:
            self.send_error_json(409, "error.card_transition_invalid")
        except CleanupPendingError:
            LOGGER.error("Database change committed; managed image cleanup requires retry")
            self.send_error_json(500, "browser.cleanup_pending")
        except (BrokenPipeError, ConnectionResetError):
            LOGGER.warning("Browser disconnected; reload to verify the last saved state")
        except TimeoutError:
            self.send_error_json(408, "browser.invalid_request")
        except (OSError, sqlite3.Error):
            LOGGER.exception("Local storage operation failed")
            self.send_error_json(500, "error.save_failed")
        except Exception:
            LOGGER.exception("Unexpected browser request failure")
            self.send_error_json(500, "browser.internal_error")

    def send_error_json(self, status: int, key: str) -> None:
        self.send_json(status, {"error": key, "message": self.server.workflow.text.text(key)})

    def json_body(self) -> dict:
        if (
            self.headers.get("Transfer-Encoding") is not None
            or self.headers.get_content_type() != "application/json"
        ):
            raise BrowserError(415, "browser.invalid_request")
        try:
            size = int(self.headers.get("Content-Length", ""))
        except ValueError:
            raise BrowserError(400, "browser.invalid_request") from None
        if not 0 < size <= MAX_BODY:
            raise BrowserError(413, "error.image_too_large")
        data = self.rfile.read(size)
        if len(data) != size:
            raise BrowserError(400, "browser.invalid_request")
        try:
            payload = json.loads(data)
        except (ValueError, UnicodeError):
            raise BrowserError(400, "browser.invalid_request") from None
        if not isinstance(payload, dict):
            raise BrowserError(400, "browser.invalid_request")
        return payload

    def route(self, path: str, payload: dict) -> None:
        workflow = self.server.workflow
        method = self.command
        if not path.startswith("/api/"):
            if method != "GET":
                raise BrowserError(404, "browser.not_found")
            candidate = self.server.static / ("index.html" if path == "/" else path.lstrip("/"))
            if (
                not candidate.resolve().is_relative_to(self.server.static)
                or not candidate.is_file()
            ):
                raise BrowserError(404, "browser.not_found")
            content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
            self.send_data(200, candidate.read_bytes(), content_type)
            return
        if path == "/api/bootstrap" and method == "GET":
            self.send_json(200, {
                "sessions": [
                    workflow.session_data(session)
                    for session in workflow.repositories.list_sessions()
                ],
                "strokes": [
                    {"value": option.value, "label": option.label}
                    for option in workflow.strokes
                ],
                "texts": dict(workflow.text.messages),
            })
            return
        if path == "/api/sessions" and method == "POST":
            self.send_json(201, workflow.create_session(payload))
            return
        if path == "/api/capture" and method == "POST":
            self.send_json(200, workflow.capture(payload))
            return
        parts = path.strip("/").split("/")
        if len(parts) not in (3, 4) or parts[0] != "api":
            raise BrowserError(404, "browser.not_found")
        resource, item = parts[1:3]
        action = parts[3] if len(parts) == 4 else None
        if resource == "sessions":
            session = workflow.session(item)
            if action is None and method == "GET":
                cards = workflow.repositories.list_cards(item)
                self.send_json(200, {
                    "session": workflow.session_data(session, card_count=len(cards)),
                    "cards": [workflow.detail(card.id) for card in cards],
                })
                return
            if action is None and method == "DELETE":
                workflow.use_cases.delete_session(item)
                self.send_json(200, {"deleted": True})
                return
            if action == "export" and method == "GET":
                self.send_data(
                    200, workflow.export(item), "text/csv; charset=utf-8",
                    filename=workflow.export_filename(item),
                )
                return
        if resource == "cards":
            workflow.card(item)
            if action is None and method == "GET":
                self.send_json(200, workflow.detail(item))
                return
            if action == "image" and method == "GET":
                image = workflow.use_cases.read_card_image(item)
                stream = io.BytesIO()
                image.save(stream, format="PNG")
                self.send_data(200, stream.getvalue(), "image/png")
                return
            if action == "card-image" and method == "GET":
                image, _ = workflow.card_display(item)
                stream = io.BytesIO()
                image.save(stream, format="PNG")
                self.send_data(200, stream.getvalue(), "image/png")
                return
            if action == "overlays" and method == "GET":
                self.send_json(200, workflow.card_display(item)[1])
                return
            if action is None and method == "DELETE":
                workflow.use_cases.delete_card(item)
                self.send_json(200, {"deleted": True})
                return
            if action is None and method == "PATCH":
                self.send_json(200, workflow.save(item, payload))
                return
            if action == "approve" and method == "POST":
                self.send_json(200, workflow.approve(item, payload))
                return
            if action == "move" and method == "POST":
                destination = identifier(payload, "session_id")
                workflow.session(destination, classified=True)
                card = workflow.card(item)
                if card.session_id == destination:
                    raise BrowserError(400, "browser.invalid_request")
                workflow.repositories.move_card(item, integer(payload, "revision"), destination)
                self.send_json(200, workflow.detail(item))
                return
        raise BrowserError(404, "browser.not_found")
