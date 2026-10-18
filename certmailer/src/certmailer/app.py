from __future__ import annotations

import re
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from platformdirs import user_data_dir, user_config_dir
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Log, Static, TextArea

from .mailer import gmail_service, html_to_text, render_body, send_message
from .matching import Match, discover_certificates, match_participants, read_participants, validate_matches
from .reporting import ensure_db, export_preflight, record_attempt

APP_NAME = "certmailer"
DEFAULT_HTML = """<p>Dear {{ name }},</p>
<p>Thank you for participating in our event.</p>
<p>Please find your certificate attached to this email.</p>
<p>Regards,<br>Organising Team</p>"""


class CertMailerApp(App):
    TITLE = "CertMailer — Certificate Delivery Manager"
    SUB_TITLE = "Matching-first prototype · Gmail · review before sending"
    CSS = """
    Screen { layout: vertical; }
    #main { height: 1fr; scrollbar-gutter: stable; }
    #paths { height: auto; padding: 1 2; border: round $primary; margin: 1 1 0 1; }
    .fieldrow { height: 3; }
    .fieldlabel { width: 20; padding-top: 1; }
    .pathinput { width: 1fr; }
    #columns { height: auto; padding: 0 2 1 2; }
    #actions { height: auto; padding: 0 2; }
    #summary { height: 3; padding: 1 2; color: $text; }
    #table { height: 16; min-height: 8; margin: 0 2; }
    #email { height: auto; padding: 0 2; }
    #body { height: 8; min-height: 5; }
    #testrow { height: auto; padding: 1 2; }
    #testto { width: 1fr; }
    #testbuttonrow { height: auto; padding: 0 2 1 2; }
    #authurlrow { height: auto; padding: 0 2 1 2; }
    #authurlcontrols { height: 3; }
    #authurl { width: 1fr; }
    #confirm { width: 1fr; }
    #sendbuttonrow { height: auto; padding: 0 2 1 2; }
    #log { height: 8; border: round $secondary; margin: 1 2; }
    #sendrow { height: auto; padding: 0 2; }
    Button { margin-right: 1; }
    """

    BINDINGS = [("ctrl+q", "quit", "Quit"), ("ctrl+r", "scan", "Scan/match")]

    def __init__(self):
        super().__init__()
        self.matches: list[Match] = []
        self.orphaned = []
        self.service = None
        self.batch_key = ""
        self.last_sheet = ""
        self.last_directory = ""

    def compose(self) -> ComposeResult:
        yield Header()
        # Put the full dashboard inside a scrollable viewport so the test and live-send
        # controls remain reachable even in short terminal windows.
        with VerticalScroll(id="main"):
            with Vertical(id="paths"):
                with Horizontal(classes="fieldrow"):
                    yield Label("Participant CSV/XLSX", classes="fieldlabel")
                    yield Input(placeholder="/path/to/participants.xlsx", id="sheet", classes="pathinput")
                with Horizontal(classes="fieldrow"):
                    yield Label("Certificate directory", classes="fieldlabel")
                    yield Input(placeholder="/path/to/certificates", id="directory", classes="pathinput")
                with Horizontal(classes="fieldrow"):
                    yield Label("OAuth client JSON", classes="fieldlabel")
                    yield Input(placeholder="/path/to/credentials.json", id="oauth", classes="pathinput")
            with Horizontal(id="columns"):
                yield Label("Name column")
                yield Input(placeholder="auto-detect", id="namecol")
                yield Label("Email column")
                yield Input(placeholder="auto-detect", id="emailcol")
                yield Label("Index column")
                yield Input(placeholder="auto-detect", id="indexcol")
            with Horizontal(id="actions"):
                yield Button("Scan & Match", id="scan", variant="primary")
                yield Button("Export Preflight CSV", id="export")
                yield Button("Preview Sample", id="preview")
            yield Static("No data loaded. Scan inputs to begin. Matching never sends email.", id="summary")
            yield DataTable(id="table", zebra_stripes=True)
            with Vertical(id="email"):
                yield Label("Email subject")
                yield Input(value="Your certificate", id="subject")
                yield Label("HTML email body (supports {{ name }})")
                yield TextArea(DEFAULT_HTML, id="body")
            with Vertical(id="testrow"):
                yield Label("Test recipient")
                yield Input(placeholder="you@example.com", id="testto")
            with Horizontal(id="testbuttonrow"):
                yield Button("Authenticate + Send Test", id="test", variant="warning")
            with Vertical(id="authurlrow"):
                yield Label("Google OAuth URL — click Copy URL, then paste it into your browser")
                with Horizontal(id="authurlcontrols"):
                    yield Input(placeholder="The full Google authorization URL will appear here", id="authurl")
                    yield Button("Copy URL", id="copy-auth-url", disabled=True)
            with Vertical(id="sendrow"):
                yield Label("Type SEND to confirm live batch:")
                yield Input(placeholder="SEND", id="confirm")
            with Horizontal(id="sendbuttonrow"):
                yield Button("Send Valid Matches", id="send", variant="error")
            yield Log(id="log", highlight=True)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#table", DataTable)
        table.add_columns("Row", "Name", "Email", "Certificate", "Status", "Issue")
        self.log_line("Ready. First run should be Scan & Match, then inspect the manifest.")
        self.log_line(f"User config directory: {user_config_dir(APP_NAME, appauthor=False)}")
        self.log_line(f"User data directory: {user_data_dir(APP_NAME, appauthor=False)}")

    def log_line(self, message: str) -> None:
        self.query_one("#log", Log).write_line(message)

    def action_scan(self) -> None:
        self.scan_inputs()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "scan":
            self.scan_inputs()
        elif event.button.id == "export":
            self.export_report()
        elif event.button.id == "preview":
            self.preview_sample()
        elif event.button.id == "test":
            self.send_test()
        elif event.button.id == "copy-auth-url":
            self.copy_auth_url()
        elif event.button.id == "send":
            self.send_batch()

    def scan_inputs(self) -> None:
        try:
            sheet_path = Path(self.query_one("#sheet", Input).value.strip()).expanduser().resolve()
            directory = Path(self.query_one("#directory", Input).value.strip()).expanduser().resolve()
            namecol = self.query_one("#namecol", Input).value.strip()
            emailcol = self.query_one("#emailcol", Input).value.strip()
            indexcol = self.query_one("#indexcol", Input).value.strip()
            if not sheet_path.is_file():
                raise ValueError(f"Participant sheet does not exist: {sheet_path}")
            participants, headers = read_participants(sheet_path, namecol, emailcol, indexcol)
            certificates = discover_certificates(directory)
            raw_matches, orphaned = match_participants(participants, certificates)
            self.matches = validate_matches(raw_matches)
            self.orphaned = orphaned
            self.last_sheet, self.last_directory = str(sheet_path), str(directory)
            fingerprint = hashlib.sha256()
            fingerprint.update(str(sheet_path).encode())
            fingerprint.update(str(sheet_path.stat().st_mtime_ns).encode())
            fingerprint.update(str(directory).encode())
            for match in self.matches:
                fingerprint.update(f"{match.participant.row_number}|{match.participant.name}|{match.participant.email}|{match.certificate.path if match.certificate else ''}".encode())
                if match.certificate and match.certificate.path.exists():
                    fingerprint.update(str(match.certificate.path.stat().st_mtime_ns).encode())
            self.batch_key = fingerprint.hexdigest()[:24]
            table = self.query_one("#table", DataTable)
            table.clear()
            for match in self.matches:
                cert = match.certificate.path.name if match.certificate else "—"
                table.add_row(str(match.participant.row_number), match.participant.name, match.participant.email or "—", cert, match.status, match.issue or "—")
            ready = sum(1 for m in self.matches if m.ready)
            unmatched = sum(1 for m in self.matches if m.status == "unmatched")
            ambiguous = sum(1 for m in self.matches if m.status == "ambiguous")
            invalid = sum(1 for m in self.matches if m.status in {"invalid_email", "duplicate_email"})
            self.query_one("#summary", Static).update(
                f"Participants: {len(self.matches)} | Ready: {ready} | Unmatched: {unmatched} | Ambiguous: {ambiguous} | Email issues: {invalid} | Orphan PDFs: {len(orphaned)} | Columns: {', '.join(headers)}"
            )
            self.log_line(f"Loaded {len(self.matches)} participants and {len(certificates)} PDFs. No messages sent.")
            if orphaned:
                self.log_line("Orphan PDFs: " + ", ".join(c.path.name for c in orphaned[:10]) + (" …" if len(orphaned) > 10 else ""))
        except Exception as exc:
            self.log_line(f"SCAN ERROR: {exc}")
            self.notify(str(exc), title="Could not scan inputs", severity="error")

    def report_path(self) -> Path:
        root = Path(user_data_dir(APP_NAME, appauthor=False)) / "reports"
        root.mkdir(parents=True, exist_ok=True)
        name = self.batch_key or datetime.now(timezone.utc).strftime("preflight-%Y%m%dT%H%M%SZ")
        return root / f"{name}-report.csv"

    def export_report(self) -> None:
        if not self.matches:
            self.notify("Scan inputs first.", severity="warning")
            return
        path = self.report_path()
        try:
            export_preflight(self.matches, path)
            self.log_line(f"Preflight CSV exported: {path}")
            self.notify(f"CSV exported to {path}")
        except Exception as exc:
            self.log_line(f"REPORT ERROR: {exc}")

    def preview_sample(self) -> None:
        ready = next((m for m in self.matches if m.ready), None)
        if not ready:
            self.notify("No fully matched participant with a valid email is ready to preview.", severity="warning")
            return
        subject = self.query_one("#subject", Input).value
        body = self.query_one("#body", TextArea).text
        rendered = render_body(body, ready.participant.name)
        self.log_line(f"PREVIEW — To: {ready.participant.email} | Subject: {subject} | Attachment: {ready.certificate.path.name}")
        self.log_line("HTML body: " + rendered.replace("\n", " ")[:500])
        self.notify(f"Preview logged for {ready.participant.name}; no email sent.")

    def get_service(self):
        oauth = Path(self.query_one("#oauth", Input).value.strip()).expanduser().resolve()
        if not self.service:
            self.log_line("Starting Gmail OAuth flow. A browser window may open.")
            self.service = gmail_service(oauth)
        return self.service

    def send_test(self) -> None:
        recipient = self.query_one("#testto", Input).value.strip()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", recipient):
            self.notify("Enter a valid test recipient email address.", severity="error")
            return
        sample = next((m for m in self.matches if m.ready), None)
        if not sample:
            self.notify("No ready certificate available for test send.", severity="warning")
            return

        oauth = Path(self.query_one("#oauth", Input).value.strip()).expanduser().resolve()
        subject = "[TEST] " + self.query_one("#subject", Input).value
        template = self.query_one("#body", TextArea).text
        participant_name = sample.participant.name
        certificate_path = str(sample.certificate.path)

        button = self.query_one("#test", Button)
        button.disabled = True
        self.log_line("Starting Gmail OAuth and test send in a background worker. The UI should remain responsive.")
        self.query_one("#authurl", Input).value = ""
        self.query_one("#copy-auth-url", Button).disabled = True
        self._send_test_worker(
            str(oauth), recipient, subject, template, participant_name, certificate_path
        )

    @work(thread=True, exclusive=True, name="send-test")
    def _send_test_worker(
        self,
        oauth_path: str,
        recipient: str,
        subject: str,
        template: str,
        participant_name: str,
        certificate_path: str,
    ) -> None:
        """Authenticate and send one test message without blocking Textual's UI thread."""
        try:
            service = gmail_service(
                Path(oauth_path),
                on_auth_url=lambda url: self.call_from_thread(self._show_auth_url, url),
            )
            html_body = render_body(template, participant_name)
            text_body = html_to_text(html_body)
            message_id = send_message(
                service, recipient, subject, text_body, html_body, Path(certificate_path)
            )
            self.call_from_thread(
                self._test_send_succeeded,
                service,
                recipient,
                certificate_path,
                message_id,
            )
        except Exception as exc:
            self.call_from_thread(self._test_send_failed, str(exc))

    def _show_auth_url(self, url: str) -> None:
        from urllib.parse import parse_qs, urlparse

        self.query_one("#authurl", Input).value = url
        self.query_one("#copy-auth-url", Button).disabled = False
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        redirect_uri = params.get("redirect_uri", [""])[0]
        self.log_line(
            "OAuth URL diagnostics: "
            f"host={parsed.netloc}, path={parsed.path}, "
            f"response_type={params.get('response_type', ['missing'])[0]}, "
            f"client_id_present={bool(params.get('client_id'))}, "
            f"state_present={bool(params.get('state'))}, "
            f"scope_present={bool(params.get('scope'))}, "
            f"redirect_uri={redirect_uri}"
        )
        self.log_line("OAuth URL ready. Click Copy URL, then paste it into your browser address bar.")

    def copy_auth_url(self) -> None:
        url = self.query_one("#authurl", Input).value.strip()
        if not url:
            self.notify("No OAuth URL is available yet.", severity="warning")
            return
        try:
            self.copy_to_clipboard(url)
            self.notify("OAuth URL copied to clipboard. Paste it into your browser address bar.")
            self.log_line("OAuth URL copied to clipboard.")
        except Exception as exc:
            self.log_line(f"Clipboard copy failed: {exc}")
            self.notify("Clipboard copy failed. Select and copy the URL field manually.", severity="error")

    def _test_send_succeeded(
        self, service, recipient: str, certificate_path: str, message_id: str
    ) -> None:
        self.service = service
        self.query_one("#test", Button).disabled = False
        self.log_line(
            f"TEST ACCEPTED by Gmail: recipient={recipient}, "
            f"sample={Path(certificate_path).name}, message_id={message_id}"
        )
        self.notify("Test message accepted by Gmail. Check the test inbox before live sending.")

    def _test_send_failed(self, error: str) -> None:
        self.query_one("#test", Button).disabled = False
        self.log_line(f"TEST SEND ERROR: {error}")
        self.notify(f"Test send failed: {error}", severity="error")

    def send_batch(self) -> None:
        if self.query_one("#confirm", Input).value.strip() != "SEND":
            self.notify("Type SEND exactly to confirm live delivery.", severity="error")
            return
        if not self.matches:
            self.notify("Scan inputs first.", severity="warning")
            return
        ready = [m for m in self.matches if m.ready]
        if not ready:
            self.notify("There are no valid, confidently matched recipients.", severity="warning")
            return
        if not self.service:
            self.notify("Authenticate and send a test message first.", severity="warning")
            return
        self.log_line(f"LIVE BATCH STARTED: {len(ready)} eligible recipients. Ctrl+Q exits; stop is not immediate during an active request.")
        db_path = Path(user_data_dir(APP_NAME, appauthor=False)) / "delivery.sqlite3"
        connection = ensure_db(db_path)
        try:
            subject = self.query_one("#subject", Input).value
            template = self.query_one("#body", TextArea).text
            previously_attempted = {row[0]: row[1] for row in connection.execute(
                "SELECT participant_row, status FROM delivery_attempts WHERE batch_key=?", (self.batch_key,)
            ).fetchall()}
            already_done = 0
            for number, match in enumerate(ready, start=1):
                if match.participant.row_number in previously_attempted:
                    already_done += 1
                    self.log_line(f"SKIP: {match.participant.name} already has recorded status {previously_attempted[match.participant.row_number]}; reconcile manually before another attempt.")
                    continue
                self.log_line(f"[{number}/{len(ready)}] Submitting {match.participant.name} <{match.participant.email}> …")
                try:
                    body_html = render_body(template, match.participant.name)
                    message_id = send_message(self.service, match.participant.email, subject, html_to_text(body_html), body_html, match.certificate.path)
                    record_attempt(connection, self.batch_key, match, "accepted", message_id=message_id)
                    self.log_line(f"ACCEPTED: {match.participant.name} (message_id={message_id})")
                except Exception as exc:
                    # Conservative policy: no automatic retry, because a transport failure may occur after provider acceptance.
                    record_attempt(connection, self.batch_key, match, "failed_or_uncertain", error=str(exc))
                    self.log_line(f"FAILED/UNCERTAIN: {match.participant.name}: {exc}. Not retrying automatically.")
                time.sleep(1.0)
            self.export_delivery_report(connection)
            self.notify(f"Batch loop completed. Previously attempted/skipped: {already_done}. Review the report and failed/uncertain outcomes.")
        finally:
            connection.close()

    def export_delivery_report(self, connection) -> None:
        path = self.report_path()
        rows = connection.execute("SELECT attempted_at_utc, participant_row, participant_name, email, certificate_filename, status, provider_message_id, error FROM delivery_attempts WHERE batch_key=? ORDER BY participant_row", (self.batch_key,)).fetchall()
        import csv
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["timestamp_utc", "participant_row", "participant_name", "email", "certificate_filename", "match_status", "match_method", "delivery_status", "provider_message_id", "attempts", "error"])
            for row in rows:
                writer.writerow([row[0], row[1], row[2], row[3], row[4], "matched", "normalized_name", row[5], row[6] or "", 1, row[7] or ""])
        self.log_line(f"Delivery CSV: {path}")


def main() -> None:
    CertMailerApp().run()


if __name__ == "__main__":
    main()
