from pathlib import Path

from certmailer.matching import Certificate, Participant, match_participants, normalize_name, validate_matches


def test_normalize_name_handles_case_and_separators():
    assert normalize_name("  Arpana_Oraon ") == normalize_name("ARPANA Oraon")


def test_unique_name_matches_even_without_index_assumption(tmp_path: Path):
    cert_path = tmp_path / "001_Arpana_Oraon.pdf"
    cert_path.write_bytes(b"%PDF-test")
    participant = Participant(row_number=2, name="Arpana Oraon", email="arpana@example.com", index_value="0")
    cert = Certificate(cert_path, 1, "Arpana Oraon")
    matches, orphaned = match_participants([participant], [cert])
    assert matches[0].status == "matched"
    assert matches[0].certificate == cert
    assert not orphaned


def test_duplicate_names_are_ambiguous(tmp_path: Path):
    p1 = Participant(2, "Ankit Kumar", "one@example.com", "1")
    p2 = Participant(3, "Ankit Kumar", "two@example.com", "2")
    cert = Certificate(tmp_path / "001_Ankit_Kumar.pdf", 1, "Ankit Kumar")
    matches, _ = match_participants([p1, p2], [cert])
    assert [m.status for m in matches] == ["ambiguous", "ambiguous"]


def test_duplicate_emails_block_delivery(tmp_path: Path):
    cert1 = Certificate(tmp_path / "001_Alice_A.pdf", 1, "Alice A")
    cert2 = Certificate(tmp_path / "002_Bob_B.pdf", 2, "Bob B")
    participants = [
        Participant(2, "Alice A", "same@example.com"),
        Participant(3, "Bob B", "same@example.com"),
    ]
    matches, _ = match_participants(participants, [cert1, cert2])
    matches = validate_matches(matches)
    assert all(m.status == "duplicate_email" for m in matches)
    assert not any(m.ready for m in matches)
