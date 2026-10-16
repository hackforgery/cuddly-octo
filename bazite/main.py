#!/usr/bin/env python3
"""Interactive terminal wizard for batch certificate PDFs.

Install: python -m pip install pypdf reportlab pillow
Run:     python certificate_tui.py

CSV must contain a column named exactly: Name
"""
import csv, re
from io import BytesIO
from pathlib import Path
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader

FONTS = [
    ("Helvetica (regular)", "Helvetica"),
    ("Helvetica-Bold", "Helvetica-Bold"),
    ("Times-Roman (regular)", "Times-Roman"),
    ("Times-Bold", "Times-Bold"),
    ("Courier (regular)", "Courier"),
    ("Courier-Bold", "Courier-Bold"),
]

def ask(prompt, default=""):
    value = input(f"{prompt} [{default}]: ").strip()
    return value or str(default)

def yesno(prompt, default=True):
    value = input(f"{prompt} [{'Y/n' if default else 'y/N'}]: ").strip().lower()
    return default if not value else value in ("y", "yes")

def existing_file(prompt, default, extensions):
    while True:
        p = Path(ask(prompt, default)).expanduser()
        if p.is_file() and p.suffix.lower() in extensions:
            return p.resolve()
        print(f"File not found or unsupported. Allowed: {', '.join(sorted(extensions))}")

def number(prompt, default, low, high):
    while True:
        try:
            value = float(ask(prompt, default))
            if low <= value <= high:
                return value
        except ValueError:
            pass
        print(f"Enter a number from {low} to {high}.")

def read_names(path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "Name" not in reader.fieldnames:
            raise ValueError(f'CSV needs a column named "Name". Found: {reader.fieldnames}')
        names = []
        for rownum, row in enumerate(reader, 2):
            name = (row.get("Name") or "").strip()
            if not name:
                raise ValueError(f"Blank name on CSV row {rownum}.")
            names.append(name)
    if not names:
        raise ValueError("No names found in CSV.")
    return names

def safe_name(name, i):
    clean = re.sub(r"[^\w.-]+", "_", name, flags=re.UNICODE).strip("._")[:70] or "Participant"
    return f"{i:03d}_{clean}.pdf"

def load_template(path):
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(str(path))
        if len(reader.pages) != 1:
            raise ValueError(f"PDF template must be one page; found {len(reader.pages)}.")
        return reader.pages[0], None
    from PIL import Image
    image = Image.open(path).convert("RGB")
    wpx, hpx = image.size
    # Map image pixels to points at 96 DPI while preserving aspect ratio.
    w, h = wpx * 0.75, hpx * 0.75
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(w, h))
    c.drawImage(ImageReader(image), 0, 0, width=w, height=h)
    c.save()
    buf.seek(0)
    return PdfReader(buf).pages[0], buf

def choose_font():
    print("\nFont options:")
    for i, (label, _) in enumerate(FONTS, 1):
        print(f"  {i}. {label}")
    print(f"  {len(FONTS)+1}. Load custom .ttf/.otf font")
    while True:
        try:
            choice = int(ask("Choose font number", 2))
            if 1 <= choice <= len(FONTS):
                return FONTS[choice-1][1]
            if choice == len(FONTS)+1:
                path = existing_file("Font file path", "", {".ttf", ".otf"})
                try:
                    pdfmetrics.registerFont(TTFont("CustomFont", str(path)))
                    return "CustomFont"
                except Exception as e:
                    print(f"Couldn't load font: {e}")
        except ValueError:
            pass
        print("Choose one of the listed numbers.")

def make_overlay(w, h, name, cfg):
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(w, h))
    size = cfg["size"]
    maxw = min(cfg["max_width"], w - 40)
    while pdfmetrics.stringWidth(name, cfg["font"], size) > maxw and size > cfg["min_size"]:
        size = max(cfg["min_size"], size - 0.5)
    if pdfmetrics.stringWidth(name, cfg["font"], size) > maxw:
        raise ValueError(f'Name "{name}" cannot fit at minimum size {cfg["min_size"]} pt.')
    c.setFillColor(HexColor(cfg["color"]))
    c.setFont(cfg["font"], size)
    c.drawCentredString(w * cfg["x_pct"] / 100, h - cfg["top"], name)
    c.save()
    buf.seek(0)
    return PdfReader(buf).pages[0], buf

def main():
    print("="*56 + "\n       CERTIFICATE GENERATOR — TERMINAL WIZARD\n" + "="*56)
    print("Press Enter to accept each default value.")
    template = existing_file("Template/background PDF or image", "Official Certificate Templates.pdf",
                             {".pdf", ".png", ".jpg", ".jpeg"})
    csvpath = existing_file("Participant CSV", "participants.csv", {".csv"})
    out = Path(ask("Output folder", "certificates")).expanduser()
    out.mkdir(parents=True, exist_ok=True)

    font = choose_font()
    size = number("Starting font size (pt)", 26, 1, 200)
    min_size = number("Minimum font size for long names (pt)", 15, 1, size)
    color = ask("Text colour in hex", "#073D3B")
    if not re.fullmatch(r"#?[0-9a-fA-F]{6}", color):
        print("Invalid hex colour; using #073D3B.")
        color = "#073D3B"
    if not color.startswith("#"):
        color = "#" + color

    print("\nPlacement settings:")
    x_pct = number("Horizontal position (% of page width; 50 = centre)", 50, 0, 100)
    top = number("Name baseline distance down from TOP edge (points)", 303, 0, 100000)
    max_width = number("Maximum name width (points)", 520, 10, 100000)
    combined = yesno("Also create a combined PDF?", True)
    combined_name = ask("Combined PDF filename", "All_Participation_Certificates.pdf")

    try:
        names = read_names(csvpath)
        template_page, template_buf = load_template(template)
        w, h = float(template_page.mediabox.width), float(template_page.mediabox.height)
        if top >= h:
            raise ValueError(f"Top offset {top} is outside page height {h:.1f} pt.")
        cfg = dict(font=font, size=size, min_size=min_size, color=color,
                   x_pct=x_pct, top=top, max_width=max_width)
        print(f"\nParticipants: {len(names)} | Page: {w:.1f} × {h:.1f} pt")
        print(f"Font: {font} | Size: {size} pt | Colour: {color}")
        if not yesno("Generate certificates now?", True):
            print("Cancelled.")
            return

        merged_pages = []
        for i, name in enumerate(names, 1):
            overlay, overlay_buf = make_overlay(w, h, name, cfg)
            if template.suffix.lower() == ".pdf":
                base = PdfReader(str(template)).pages[0]
            else:
                base = PdfReader(BytesIO(template_buf.getvalue())).pages[0]
            base.merge_page(overlay)
            writer = PdfWriter()
            writer.add_page(base)
            target = out / safe_name(name, i)
            with target.open("wb") as f:
                writer.write(f)
            merged_pages.append(base)
            print(f"[{i}/{len(names)}] {target.name}")
            overlay_buf.close()

        if combined:
            writer = PdfWriter()
            for page in merged_pages:
                writer.add_page(page)
            target = out / combined_name
            with target.open("wb") as f:
                writer.write(f)
            print(f"\nCombined PDF: {target}")
        print(f"\nFinished. Certificates saved to: {out.resolve()}")
    except Exception as e:
        print(f"\nERROR: {e}\nCheck the file paths and settings, then try again.")

if __name__ == "__main__":
    main()
