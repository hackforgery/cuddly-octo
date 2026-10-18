from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openpyxl import load_workbook


@dataclass
class Participant:
    row_number: int
    name: str
    email: str
    index_value: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Certificate:
    path: Path
    sequence: int | None
    filename_name: str


@dataclass
class Match:
    participant: Participant
    certificate: Certificate | None
    status: str
    method: str = ""
    issue: str = ""

    @property
    def ready(self) -> bool:
        return self.status == "matched" and self.certificate is not None and bool(self.participant.email.strip())


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold()
    value = re.sub(r"[\W_]+", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def _cell_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def read_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    """Read CSV or XLSX; return records and original column names."""
    suffix = path.suffix.casefold()
    if suffix == ".csv":
        # utf-8-sig handles Excel-exported UTF-8 files with a BOM.
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            sample = handle.read(4096)
            handle.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            except csv.Error:
                dialect = csv.excel
            reader = csv.DictReader(handle, dialect=dialect)
            if not reader.fieldnames:
                raise ValueError("The CSV has no header row.")
            headers = [str(h).strip() for h in reader.fieldnames if h is not None]
            rows = [{str(k).strip(): _cell_string(v) for k, v in row.items() if k is not None} for row in reader]
            return rows, headers
    if suffix in {".xlsx", ".xlsm"}:
        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            sheet = workbook.active
            iterator = sheet.iter_rows(values_only=True)
            first = next(iterator, None)
            if not first:
                raise ValueError("The spreadsheet is empty.")
            headers = [_cell_string(value) for value in first]
            if not any(headers):
                raise ValueError("The spreadsheet has no header row.")
            rows = []
            for values in iterator:
                row = {}
                for index, header in enumerate(headers):
                    if header:
                        row[header] = _cell_string(values[index] if index < len(values) else None)
                if any(value.strip() for value in row.values()):
                    rows.append(row)
            return rows, headers
        finally:
            workbook.close()
    raise ValueError("Unsupported sheet format. Use .csv, .xlsx, or .xlsm.")


def discover_column(headers: list[str], candidates: tuple[str, ...]) -> str:
    normalized = {re.sub(r"[^a-z0-9]", "", h.casefold()): h for h in headers}
    for candidate in candidates:
        key = re.sub(r"[^a-z0-9]", "", candidate.casefold())
        if key in normalized:
            return normalized[key]
    return ""


def read_participants(path: Path, name_column: str = "", email_column: str = "", index_column: str = "") -> tuple[list[Participant], list[str]]:
    rows, headers = read_rows(path)
    name_column = name_column if name_column in headers else discover_column(headers, ("name", "full name", "participant name"))
    email_column = email_column if email_column in headers else discover_column(headers, ("email", "email address", "e-mail"))
    index_column = index_column if index_column in headers else discover_column(headers, ("index", "id", "participant id", "certificate id", "serial number"))
    if not name_column:
        raise ValueError(f"Could not detect a name column. Available columns: {', '.join(headers)}")
    participants = []
    for i, row in enumerate(rows, start=2):
        name = row.get(name_column, "").strip()
        if not name:
            continue
        participants.append(Participant(
            row_number=i,
            name=name,
            email=row.get(email_column, "").strip() if email_column else "",
            index_value=row.get(index_column, "").strip() if index_column else "",
            raw=row,
        ))
    return participants, headers


def discover_certificates(directory: Path) -> list[Certificate]:
    if not directory.is_dir():
        raise ValueError(f"Certificate directory does not exist: {directory}")
    certificates = []
    for path in sorted(directory.iterdir(), key=lambda p: p.name.casefold()):
        if not path.is_file() or path.suffix.casefold() != ".pdf":
            continue
        match = re.match(r"^\s*(\d+)\s*[_\- ]+\s*(.*?)\s*\.pdf$", path.name, flags=re.IGNORECASE)
        if match:
            sequence = int(match.group(1))
            filename_name = re.sub(r"[_\-]+", " ", match.group(2)).strip()
        else:
            sequence = None
            filename_name = path.stem
        certificates.append(Certificate(path=path.resolve(), sequence=sequence, filename_name=filename_name))
    return certificates


def match_participants(participants: list[Participant], certificates: list[Certificate]) -> tuple[list[Match], list[Certificate]]:
    """Conservative exact-normalized-name matching, with index used only as a tie-break/check.

    Sequence/index values are not assumed to share a numbering convention. A unique normalized
    name can match directly; duplicate names are held for review unless an explicit index uniquely
    disambiguates them.
    """
    by_name: dict[str, list[Certificate]] = {}
    for cert in certificates:
        by_name.setdefault(normalize_name(cert.filename_name), []).append(cert)
    used: set[Path] = set()
    matches: list[Match] = []
    participant_name_counts: dict[str, int] = {}
    for participant in participants:
        key = normalize_name(participant.name)
        participant_name_counts[key] = participant_name_counts.get(key, 0) + 1

    for participant in participants:
        key = normalize_name(participant.name)
        candidates = by_name.get(key, [])
        if not key or not candidates:
            matches.append(Match(participant, None, "unmatched", issue="No exact normalized-name match."))
            continue
        available = [candidate for candidate in candidates if candidate.path not in used]
        if len(candidates) == 1 and len(available) == 1 and participant_name_counts.get(key, 0) == 1:
            cert = available[0]
            used.add(cert.path)
            matches.append(Match(participant, cert, "matched", method="normalized_name"))
            continue
        # Only use the index when it is an exact numeric sequence match. Never infer +1/-1 offsets.
        numeric_index = None
        try:
            numeric_index = int(participant.index_value)
        except (TypeError, ValueError):
            pass
        index_candidates = [c for c in available if numeric_index is not None and c.sequence == numeric_index]
        if len(index_candidates) == 1 and participant_name_counts.get(key, 0) == 1:
            cert = index_candidates[0]
            used.add(cert.path)
            matches.append(Match(participant, cert, "matched", method="name_and_index"))
        else:
            matches.append(Match(participant, None, "ambiguous", issue="Multiple same-name candidates or duplicate participant names; review required."))

    orphaned = [cert for cert in certificates if cert.path not in used]
    return matches, orphaned


def validate_matches(matches: list[Match]) -> list[Match]:
    """Annotate missing/invalid emails and duplicate recipient addresses; never silently send them."""
    email_groups: dict[str, list[int]] = {}
    for i, match in enumerate(matches):
        email = match.participant.email.strip().casefold()
        if email:
            email_groups.setdefault(email, []).append(i)
    for match in matches:
        email = match.participant.email.strip()
        if match.status == "matched" and not email:
            match.status = "invalid_email"
            match.issue = "Email address is missing."
        elif match.status == "matched" and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            match.status = "invalid_email"
            match.issue = "Email address format appears invalid."
    for email, indices in email_groups.items():
        if len(indices) > 1:
            for index in indices:
                match = matches[index]
                if match.status == "matched":
                    match.status = "duplicate_email"
                    match.issue = f"Email address is shared by {len(indices)} participant rows; review required."
    return matches
