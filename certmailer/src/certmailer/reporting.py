from __future__ import annotations

import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .matching import Match

REPORT_FIELDS = [
    "timestamp_utc", "participant_row", "participant_name", "email", "certificate_filename",
    "match_status", "match_method", "delivery_status", "provider_message_id", "attempts", "error",
]


def export_preflight(matches: list[Match], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REPORT_FIELDS)
        writer.writeheader()
        now = datetime.now(timezone.utc).isoformat()
        for match in matches:
            writer.writerow({
                "timestamp_utc": now,
                "participant_row": match.participant.row_number,
                "participant_name": match.participant.name,
                "email": match.participant.email,
                "certificate_filename": match.certificate.path.name if match.certificate else "",
                "match_status": match.status,
                "match_method": match.method,
                "delivery_status": "not_attempted",
                "provider_message_id": "",
                "attempts": 0,
                "error": match.issue,
            })


def ensure_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("""CREATE TABLE IF NOT EXISTS delivery_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_key TEXT NOT NULL,
        participant_row INTEGER NOT NULL,
        participant_name TEXT NOT NULL,
        email TEXT NOT NULL,
        certificate_filename TEXT NOT NULL,
        status TEXT NOT NULL,
        provider_message_id TEXT,
        error TEXT,
        attempted_at_utc TEXT NOT NULL,
        UNIQUE(batch_key, participant_row)
    )""")
    connection.commit()
    return connection


def record_attempt(connection: sqlite3.Connection, batch_key: str, match: Match, status: str, message_id: str = "", error: str = "") -> None:
    connection.execute(
        """INSERT INTO delivery_attempts
        (batch_key, participant_row, participant_name, email, certificate_filename, status, provider_message_id, error, attempted_at_utc)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(batch_key, participant_row) DO UPDATE SET
        status=excluded.status, provider_message_id=excluded.provider_message_id,
        error=excluded.error, attempted_at_utc=excluded.attempted_at_utc""",
        (batch_key, match.participant.row_number, match.participant.name, match.participant.email,
         match.certificate.path.name if match.certificate else "", status, message_id, error,
         datetime.now(timezone.utc).isoformat()),
    )
    connection.commit()
