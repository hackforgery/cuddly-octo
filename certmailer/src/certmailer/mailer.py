from __future__ import annotations

import base64
import html
import os
import socket
import time
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Event
from urllib.parse import urlparse, parse_qs

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from platformdirs import user_config_dir

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
APP_NAME = "certmailer"
OAUTH_TIMEOUT_SECONDS = 300


def token_path() -> Path:
    directory = Path(user_config_dir(APP_NAME, appauthor=False))
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "token.json"


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _manual_oauth(flow: InstalledAppFlow, on_auth_url=None):
    """Run a loopback OAuth callback without attempting to launch a browser."""
    port = _free_loopback_port()
    redirect_uri = f"http://127.0.0.1:{port}/"
    flow.redirect_uri = redirect_uri
    authorization_url, _ = flow.authorization_url(prompt="consent", access_type="offline")

    callback_done = Event()
    result: dict[str, object] = {}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - required by BaseHTTPRequestHandler
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            if "error" in query:
                result["error"] = query.get("error_description", query["error"])[0]
                body = b"Authorization was not completed. You can close this tab and return to CertMailer."
            elif "code" not in query or "state" not in query:
                result["error"] = "Google returned an incomplete OAuth callback."
                body = b"Incomplete authorization response. Return to CertMailer and check its log."
            else:
                try:
                    callback_url = f"{redirect_uri}?{parsed.query}"
                    # OAuthlib blocks plain HTTP by default. For this desktop-app
                    # flow, the callback is bound only to 127.0.0.1 (loopback).
                    # Enable the exception only around the local callback token
                    # exchange, then restore the caller's environment unchanged.
                    previous_insecure_transport = os.environ.get("OAUTHLIB_INSECURE_TRANSPORT")
                    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
                    try:
                        flow.fetch_token(authorization_response=callback_url)
                    finally:
                        if previous_insecure_transport is None:
                            os.environ.pop("OAUTHLIB_INSECURE_TRANSPORT", None)
                        else:
                            os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = previous_insecure_transport
                    result["credentials"] = flow.credentials
                    body = b"CertMailer authentication succeeded. You can close this tab and return to the app."
                except Exception as exc:  # surfaced to the TUI below
                    result["error"] = f"Could not complete OAuth callback: {exc}"
                    body = b"CertMailer could not complete authentication. Return to the app and inspect the error log."
            self.send_response(200 if "credentials" in result else 400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            callback_done.set()

        def log_message(self, format, *args):  # noqa: A003 - standard handler signature
            return

    try:
        server = HTTPServer(("127.0.0.1", port), CallbackHandler)
    except OSError as exc:
        raise RuntimeError(f"Could not start the local OAuth callback server: {exc}") from exc

    server.timeout = 1
    try:
        if on_auth_url:
            on_auth_url(authorization_url)
        deadline = time.monotonic() + OAUTH_TIMEOUT_SECONDS
        while not callback_done.is_set() and time.monotonic() < deadline:
            server.handle_request()
        if not callback_done.is_set():
            raise TimeoutError(
                f"OAuth timed out after {OAUTH_TIMEOUT_SECONDS} seconds. Open the displayed URL and complete consent."
            )
        if "error" in result:
            raise RuntimeError(str(result["error"]))
        credentials = result.get("credentials")
        if credentials is None:
            raise RuntimeError("OAuth ended without returning credentials.")
        return credentials
    finally:
        server.server_close()


def gmail_service(credentials_json: Path, on_auth_url=None):
    """Authenticate with OAuth. credentials_json is downloaded from Google Cloud."""
    token_file = token_path()
    creds = None
    if token_file.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
        except (ValueError, OSError):
            # Keep a malformed token from preventing a fresh OAuth flow.
            creds = None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not credentials_json.is_file():
                raise FileNotFoundError(
                    f"OAuth client JSON not found: {credentials_json}. Configure a Desktop app OAuth client in Google Cloud."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_json), SCOPES)
            creds = _manual_oauth(flow, on_auth_url=on_auth_url)
        token_file.write_text(creds.to_json(), encoding="utf-8")
        try:
            token_file.chmod(0o600)
        except OSError:
            pass
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def send_message(service, to: str, subject: str, body_text: str, body_html: str, attachment: Path) -> str:
    if not attachment.is_file():
        raise FileNotFoundError(f"Certificate not found: {attachment}")
    message = EmailMessage()
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body_text)
    message.add_alternative(body_html, subtype="html")
    data = attachment.read_bytes()
    message.add_attachment(data, maintype="application", subtype="pdf", filename=attachment.name)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    response = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return str(response.get("id", "accepted-no-message-id"))


def render_body(template: str, name: str) -> str:
    """Tiny safe substitution for the prototype; supports {{ name }} in user-authored templates."""
    escaped_name = html.escape(name)
    return template.replace("{{ name }}", escaped_name).replace("{{name}}", escaped_name)


def html_to_text(body_html: str) -> str:
    import re
    text = re.sub(r"<\s*br\s*/?\s*>", "\n", body_html, flags=re.IGNORECASE)
    text = re.sub(r"</\s*(p|div|li)\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()
