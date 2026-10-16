#!/usr/bin/env python3
"""
Generate personalized participation certificates from a high-resolution PDF template.

Input CSV format:
    Name
    Aditi Sharma
    Rahul Verma

Install dependencies:
    python -m pip install pypdf reportlab

Run:
    python generate_certificates.py

Optional:
    python generate_certificates.py --csv participants.csv --template "Official Certificate Templates.pdf" --out output_certificates
"""

import argparse
import csv
import re
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
from io import BytesIO


# ---------------------------- CONFIGURATION ----------------------------

DEFAULT_TEMPLATE = "template.pdf"
DEFAULT_CSV = "participants.csv"
DEFAULT_OUTPUT_DIR = "certificates"

# Position of the name baseline, measured down from the TOP edge of the PDF page.
# Increase this value to move the name DOWN; decrease it to move the name UP.
NAME_BASELINE_FROM_TOP_PT = 303

# Text style. DejaVu Sans is a good clean sans-serif choice.
FONT_SIZE_PT = 26
MIN_FONT_SIZE_PT = 15
MAX_NAME_WIDTH_PT = 520
FONT_COLOR = "#073D3B"  # dark teal, close to the certificate body text

# Optional path to a .ttf font file. Leave as None to auto-detect DejaVu Sans.
# Examples:
# Windows: r"C:\Windows\Fonts\arial.ttf"
# Linux:   "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
# macOS:   "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_TTF_PATH = None

# Also create a single PDF containing every certificate.
CREATE_COMBINED_PDF = True
COMBINED_FILENAME = "All_Participation_Certificates.pdf"

# ----------------------------------------------------------------------


def find_font_path():
    """Find a usable TrueType font; users can override FONT_TTF_PATH above."""
    if FONT_TTF_PATH:
        path = Path(FONT_TTF_PATH).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"Configured font file was not found: {path}")
        return path

    candidates = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None  # ReportLab's built-in Helvetica fallback


def safe_filename(name, index):
    """Create a filesystem-safe filename, with index to avoid duplicate-name collisions."""
    cleaned = re.sub(r"[^\w.-]+", "_", name.strip(), flags=re.UNICODE).strip("._")
    cleaned = cleaned[:70] or "Participant"
    return f"{index:03d}_{cleaned}.pdf"


def read_names(csv_path):
    """Read the required Name column and reject blank names with useful row numbers."""
    names = []
    with csv_path.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames or "Name" not in reader.fieldnames:
            raise ValueError(
                f'The CSV must contain a column named exactly "Name". '
                f"Columns found: {reader.fieldnames}"
            )

        for row_number, row in enumerate(reader, start=2):
            name = (row.get("Name") or "").strip()
            if not name:
                raise ValueError(
                    f"Blank Name found on CSV row {row_number}. "
                    "Fill it in or remove that row, then run again."
                )
            names.append(name)

    if not names:
        raise ValueError("No participant names found in the CSV.")
    return names


def make_overlay(page_width, page_height, name, font_name):
    """Create a one-page transparent PDF containing only the participant name."""
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(page_width, page_height))

    font_size = FONT_SIZE_PT
    available_width = min(MAX_NAME_WIDTH_PT, page_width - 100)

    # Shrink only as much as necessary to keep the full name within the allowed width.
    while (
        pdfmetrics.stringWidth(name, font_name, font_size) > available_width
        and font_size > MIN_FONT_SIZE_PT
    ):
        font_size -= 0.5

    actual_width = pdfmetrics.stringWidth(name, font_name, font_size)
    if actual_width > available_width:
        raise ValueError(
            f'Name "{name}" is too long to fit even at the minimum font size '
            f"({MIN_FONT_SIZE_PT} pt). Shorten the name or increase MAX_NAME_WIDTH_PT."
        )

    x = page_width / 2
    y = page_height - NAME_BASELINE_FROM_TOP_PT

    pdf.setFillColor(HexColor(FONT_COLOR))
    pdf.setFont(font_name, font_size)
    pdf.drawCentredString(x, y, name)
    pdf.save()
    buffer.seek(0)
    return PdfReader(buffer)


def main():
    parser = argparse.ArgumentParser(description="Generate certificates from a PDF template and CSV.")
    parser.add_argument("--template", default=DEFAULT_TEMPLATE, help="Path to the one-page PDF template.")
    parser.add_argument("--csv", default=DEFAULT_CSV, help="Path to CSV containing a Name column.")
    parser.add_argument("--out", default=DEFAULT_OUTPUT_DIR, help="Output directory for generated certificates.")
    args = parser.parse_args()

    template_path = Path(args.template).expanduser()
    csv_path = Path(args.csv).expanduser()
    output_dir = Path(args.out).expanduser()

    if not template_path.is_file():
        raise FileNotFoundError(f"Template PDF not found: {template_path.resolve()}")
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV file not found: {csv_path.resolve()}")

    template_reader = PdfReader(str(template_path))
    if len(template_reader.pages) != 1:
        raise ValueError(
            f"The template should have exactly one page; found {len(template_reader.pages)}."
        )
    template_page = template_reader.pages[0]
    page_width = float(template_page.mediabox.width)
    page_height = float(template_page.mediabox.height)

    names = read_names(csv_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    font_path = find_font_path()
    if font_path:
        font_name = "CertificateSans"
        pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
        print(f"Using font: {font_path}")
    else:
        font_name = "Helvetica-Bold"
        print("WARNING: No TrueType font found; using built-in Helvetica.")

    combined_writer = PdfWriter()

    for index, name in enumerate(names, start=1):
        overlay_reader = make_overlay(page_width, page_height, name, font_name)
        output_page = PdfReader(str(template_path)).pages[0]
        output_page.merge_page(overlay_reader.pages[0])

        writer = PdfWriter()
        writer.add_page(output_page)

        output_path = output_dir / safe_filename(name, index)
        with output_path.open("wb") as file:
            writer.write(file)

        combined_writer.add_page(output_page)
        print(f"[{index}/{len(names)}] Created: {output_path.name}")

    if CREATE_COMBINED_PDF:
        combined_path = output_dir / COMBINED_FILENAME
        with combined_path.open("wb") as file:
            combined_writer.write(file)
        print(f"\nCombined PDF: {combined_path}")

    print(f"\nDone. Generated {len(names)} individual certificate(s) in: {output_dir.resolve()}")


if __name__ == "__main__":
    main()
