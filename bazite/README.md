# Certificate Studio

A Python terminal wizard that adds participant names to a certificate template. It creates one PDF per participant and can also combine them into a single PDF.

> **Current version:** Adds names only. Name placement is set with numbers. There is no visual editor, automatic placement detection, or saved template profiles.

## 1. Requirements

- Python 3.9 or newer
- A one-page PDF certificate template, or a PNG/JPG/JPEG image
- A CSV file containing participant names

Install the required libraries:

```bash
python -m pip install pypdf reportlab pillow
```

## 2. Project files

Keep these files together, or provide their paths when prompted:

```text
certificate-project/
├── certificate_tui.py
├── certificate-template.pdf
├── participants.csv
└── certificates/        # generated automatically
```

## 3. Prepare your files

### Certificate template

Supported formats: PDF, PNG, JPG, JPEG.

- A PDF must contain **exactly one page**.
- Use the final certificate artwork and leave room for the participant's name.
- The program adds text over the template; it does not edit the artwork or find the correct name position for you.

### Participant CSV

The file must have a column named exactly `Name`.

```csv
Name
Aarav Sharma
Diya Patel
Kabir Mehta
```

Save your spreadsheet as `.csv`. Check that every row has a name and remove blank rows. Other columns are ignored. Names are processed in row order; duplicate names are allowed.

## 4. Start the program

Run this command in the folder containing `certificate_tui.py`:

```bash
python certificate_tui.py
```

If your system uses `python3`, use `python3 certificate_tui.py` instead.

**At each prompt:** press Enter to accept the suggested default, or type a new value and press Enter.

## 5. Answer the wizard prompts

### A. Files and output

1. **Template:** path to your PDF or image.
2. **CSV:** path to your participant list.
3. **Output folder:** where generated PDFs should be saved. The default is `certificates`.

Defaults are suggestions, not automatic file discovery. If a file is elsewhere, enter its path.

### B. Font

Choose one of the built-in fonts:

1. Helvetica
2. Helvetica-Bold
3. Times-Roman
4. Times-Bold
5. Courier
6. Courier-Bold
7. Load a custom `.ttf` or `.otf` font file

The default is **Helvetica-Bold**.

### C. Text appearance

- **Starting font size:** default `26` points.
- **Minimum font size:** default `15` points. Long names can shrink to this size.
- **Text color:** hexadecimal RGB, for example `#073D3B`, `#000000`, or `#FFFFFF`. The default is `#073D3B`.

### D. Name placement

- **Horizontal position:** percentage across the page. `50` centers the name; lower values move it left, higher values move it right.
- **Top offset:** distance in points from the top of the page to the text baseline. **Lower the value to move the name up; raise it to move the name down.** Default: `303` points.
- **Maximum name width:** maximum width allowed before the font shrinks. Default: `520` points.

These defaults may not fit your template. Use the test workflow below to align the name.

### E. Combined PDF

Choose whether to create one PDF containing every certificate. The default is yes. The default filename is `All_Participation_Certificates.pdf`.

### F. Review and generate

The wizard shows a summary of the settings and number of participants. Confirm to start, or cancel if anything needs changing. A progress bar and current filename are displayed during generation.

## 6. Test alignment before generating everything

1. Make a small CSV with one typical name and one long name.
2. Run the wizard and generate the test certificates.
3. Open the PDFs and check the name's position, size, color, and readability.
4. If the name is too high, **increase** the top offset. If too low, **decrease** it.
5. Adjust the horizontal position if needed. Change it in small steps and test again.
6. Once the test looks correct, run the full participant list.

The program does not automatically detect the correct placement. Always inspect samples when using a new template.

## 7. How long names fit

The program reduces the font size in 0.5-point steps when a name exceeds the maximum width. It stops at the minimum font size. If the name still does not fit, generation can stop with an error; the current version does not reliably skip that name and continue.

If a name does not fit, try a wider name area, a narrower font, or a lower minimum font size.

## 8. Output

Example output folder:

```text
certificates/
├── 001_Aarav_Sharma.pdf
├── 002_Diya_Patel.pdf
├── 003_Kabir_Mehta.pdf
└── All_Participation_Certificates.pdf
```

Each participant gets an individual PDF. The number follows the CSV row order and distinguishes duplicate names. The combined PDF, if enabled, contains one page per participant in that same order.

**Caution:** Files with the same output names may be overwritten. Use a new output folder to preserve an earlier batch.

## 9. Common problems

| Problem | What to do |
|---|---|
| Template not found | Check the path and file extension. |
| PDF has multiple pages | Export the required page as a separate one-page PDF. |
| `Name` column not found | Rename the CSV header to exactly `Name`. |
| Blank name reported | Fill in or remove the blank row. |
| Name too high or low | Adjust the top offset: higher number = lower name. |
| Name too far left or right | Adjust the horizontal percentage. |
| Name too large or small | Change the starting font size. |
| Long name does not fit | Increase maximum width, choose a narrower font, or lower the minimum size. |
| No output files | Check that you confirmed generation and read any error shown in the terminal. |

## 10. Current limitations

This version does **not** support:

- Automatic name placement or OCR
- A visual editor or live graphical preview
- Saved settings for different templates
- Personalizing multiple fields, such as dates or certificate IDs
- Excel `.xlsx` input or multi-page PDF templates
- Reliable skip-and-continue behavior after a participant's rendering error
- Emailing or distributing certificates

## Before publishing

Add the license you choose for the project. Make sure you have permission to distribute the certificate artwork and any custom fonts included with the repository.
