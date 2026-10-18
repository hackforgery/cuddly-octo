# CertMailer

CertMailer is a terminal user interface (TUI) for matching participant records to individual PDF certificates, previewing a personalized email, sending a test message through Gmail, and sending certificates only to records the matching engine considers safe.

> **Important:** CertMailer sends real email. Always scan and review the preflight report, verify the test email, and check the recipient-to-certificate mapping before authorizing a live batch.

## Contents

- [What it does](#what-it-does)
- [Requirements](#requirements)
- [1. Install the project](#1-install-the-project)
- [2. Configure Google Cloud and Gmail OAuth](#2-configure-google-cloud-and-gmail-oauth)
- [3. Prepare the participant sheet](#3-prepare-the-participant-sheet)
- [4. Prepare the certificate directory](#4-prepare-the-certificate-directory)
- [5. Launch the application](#5-launch-the-application)
- [6. Scan and match](#6-scan-and-match)
- [7. Review and export the preflight report](#7-review-and-export-the-preflight-report)
- [8. Customize and preview the email](#8-customize-and-preview-the-email)
- [9. Authenticate and send a test](#9-authenticate-and-send-a-test)
- [10. Send the live batch](#10-send-the-live-batch)
- [11. Reports and local data](#11-reports-and-local-data)
- [Troubleshooting](#troubleshooting)
- [Safety notes and known limitations](#safety-notes-and-known-limitations)
- [Official documentation](#official-documentation)

## What it does

- Reads participant lists from CSV, XLSX, and XLSM files.
- Detects common name, email, and index column headers; manual column overrides are available.
- Discovers PDF certificate files in a selected directory.
- Uses conservative normalized-name matching to propose participant-to-certificate assignments.
- Displays ready, unmatched, ambiguous, email-issue, and orphan-PDF counts.
- Exports a preflight CSV report.
- Supports an HTML email body personalized with `{{ name }}`.
- Uses Gmail API OAuth; it never asks for your Gmail password.
- Supports test sending and requires the exact word `SEND` before live sending.
- Stores delivery attempt history locally and does not automatically retry failed or uncertain submissions.

## Requirements

- Python 3.11 or newer.
- Internet access for Google OAuth and Gmail API delivery.
- A Google account with Gmail.
- A participant CSV, XLSX, or XLSM file and a directory containing individual PDF certificates.
- Google Cloud OAuth credentials for sending. Matching and preflight export can be used without Gmail credentials.

## 1. Install the project

Clone your repository (replace the example URL with your actual repository URL), or download and extract its ZIP. Run commands from the project directory containing `pyproject.toml`.

```bash
git clone https://github.com/YOUR-USERNAME/YOUR-REPOSITORY.git
cd YOUR-REPOSITORY
```

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pytest
certmailer
```

### Windows PowerShell

Install Python 3.11 or newer, then run:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pytest
certmailer
```

If PowerShell blocks activation, invoke the environment's Python directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m certmailer.app
```

On Linux or WSL, use the Linux commands. In WSL, Windows files are often available under `/mnt/c/Users/...`; use the actual path in your environment. The app can be launched with `certmailer` or `python -m certmailer.app`.

## 2. Configure Google Cloud and Gmail OAuth

This setup is required to send messages. Google occasionally changes the console layout and labels; if the names differ, consult the official links in [Official documentation](#official-documentation).

### 2.1 Create or select a Google Cloud project

1. Open the [Google Cloud Console](https://console.cloud.google.com/).
2. Sign in with the Google account you will use to manage the integration.
3. Open the project selector at the top of the page.
4. Select an existing project or choose **New Project**.
5. Give the project a recognizable name, such as `CertMailer`, and create it.
6. Confirm that this project is selected before continuing.

The project holds the enabled API and OAuth configuration. You do **not** need a service account for this desktop workflow.

### 2.2 Enable the Gmail API

1. Open the [Gmail API page in the API Library](https://console.cloud.google.com/apis/library/gmail.googleapis.com).
2. Confirm the correct project is selected.
3. Click **Enable**. If it is already enabled, continue.

Enabling the API does not itself authorize access to a mailbox. The OAuth consent steps below are still required.

### 2.3 Configure Google Auth / OAuth consent

1. In the Cloud Console, open **Google Auth Platform**. In some console versions, this is labelled **OAuth consent screen**.
2. If prompted, choose **Get started** or the equivalent setup action.
3. Enter an app name, for example `CertMailer`.
4. Select a user-support email address you control.
5. Under **Audience**, choose the appropriate user type:
   - **External** is generally used for consumer Google accounts or users outside a Google Workspace organization.
   - **Internal** is only for eligible Google Workspace organizations and limits access to users within that organization.
6. Enter a developer contact email address.
7. Review the applicable Google API Services User Data Policy prompt and finish setup.
8. Save the configuration.

In the current Google Auth Platform layout, **Branding**, **Audience**, and **Data Access** may be separate sections. Follow the console's sequence if it differs from these steps.

### 2.4 Add a test user if the app is in Testing

For an **External** app that remains in **Testing** status:

1. Open **Google Auth Platform → Audience**.
2. Find **Test users** and choose **Add users**.
3. Add the exact Google account that will authorize CertMailer and send the messages.
4. Save the changes.

Only accounts allowed by the app's audience and publishing status can authorize it. If Google says your account is not an authorized test user, confirm that you are using the intended Cloud project and add the correct account here. Apps left in Testing may be subject to Google's testing restrictions, including refresh-token expiry rules. For regular use beyond the test audience, review Google's current verification and publishing requirements.

### 2.5 Understand the requested permission

CertMailer requests the Gmail `gmail.send` scope. This permission allows it to send messages on the user's behalf; the app is not designed to read or manage the mailbox. If the console asks you to configure data access, follow its prompts and make sure you understand the requested scope. Do not add broader Gmail permissions as a workaround.

### 2.6 Create Desktop-app OAuth credentials

1. Open **Google Auth Platform → Clients**. In older console layouts, use **APIs & Services → Credentials**.
2. Click **Create client** or **Create credentials → OAuth client ID**.
3. Set **Application type** to **Desktop app**.
4. Give it a name such as `CertMailer Desktop`.
5. Create the client.
6. Download the client JSON using the download option provided by the console.
7. Store it privately, outside your repository. Example paths:
   - Linux/macOS: `~/private/certmailer-oauth.json`
   - Windows: `C:\Users\YOUR-USER\private\certmailer-oauth.json`

The JSON should be a Desktop/installed-app configuration, commonly containing an `installed` object. Do not use a Web application OAuth client for this local terminal app, and do not create a service-account key for this workflow.

**Never commit the downloaded JSON to Git.** Treat it as private configuration. Also never commit the OAuth token created by the application.

### 2.7 Authorize CertMailer for the first time

1. Start CertMailer and enter the full path to the downloaded JSON in **OAuth client JSON**.
2. Enter the participant sheet and certificate directory paths as described below.
3. Enter an email address you control in the test-recipient field.
4. Click **Authenticate + Send Test**.
5. CertMailer displays the Google authorization URL in the TUI. Click **Copy URL**, then paste it into a browser if it does not open automatically.
6. Sign in with the Google account you intend to send from (and that you added as a test user, if applicable).
7. Review Google's consent screen and the requested send permission.
8. Approve it only if you trust the app and expect it to send email from that account.
9. Return to CertMailer and inspect the TUI log for the test-send result.

The app uses a local loopback callback for desktop OAuth. If the browser says authorization succeeded and that you can return to the application, go back to the TUI and check its log. After successful authorization, the app stores token data in the operating system's user configuration directory. You should not normally need to repeat consent unless the token is revoked, expires, the OAuth configuration changes, or Google requires reauthorization.

## 3. Prepare the participant sheet

CertMailer supports **CSV**, **XLSX**, and **XLSM** files. Each intended recipient needs a participant name and email address. An index/sequence column is optional, but the application does not assume it is zero-based or one-based.

Example CSV:

```csv
Name,Email,Index
Arpana Oraon,arpana@example.com,1
Rohan Kumar,rohan@example.com,2
Meera Das,meera@example.com,3
```

The addresses are examples only; use the actual intended recipient addresses in your file.

### Column detection and overrides

The app attempts to detect common name, email, and index header names. The TUI also provides optional fields for the exact **Name column**, **Email column**, and **Index column** headers. Leave a field blank for automatic detection. If the wrong column is detected, enter the exact header text from the sheet.

### Data preparation checklist

- One participant per row.
- Correct spelling in the name column.
- Correct email address for each participant.
- No accidental duplicate rows.
- Clear, unique column headers.
- A saved backup of the final input file.
- Do not edit the source file during a batch.

## 4. Prepare the certificate directory

Put the individual participant PDFs in one directory and avoid including unrelated PDFs. For example:

```text
certificates/
├── 001_Arpana_Oraon.pdf
├── 002_Rohan_Kumar.pdf
└── 003_Meera_Das.pdf
```

The matching engine normalizes names to handle differences such as capitalization and separators, but it intentionally uses conservative matching rather than guessing from fuzzy similarity.

**Important:** CertMailer does not silently apply an index offset. For example, it will not automatically assume spreadsheet index `0` maps to PDF sequence `001`. If the sheet and filenames use different numbering conventions, verify the proposed mapping and correct the source data or filenames before sending.

## 5. Launch the application

From the project directory, activate the virtual environment and run:

```bash
certmailer
```

Or:

```bash
python -m certmailer.app
```

If the environment is not activated on Windows:

```powershell
.\.venv\Scripts\python.exe -m certmailer.app
```

The dashboard includes path fields, optional column overrides, matching actions, email content, test delivery, OAuth authorization, and live-send confirmation. Depending on terminal size, you may need to scroll through the dashboard.

## 6. Scan and match

1. In **Participant CSV/XLSX**, enter the full path to the participant file.
2. In **Certificate directory**, enter the full path to the PDF folder.
3. In **OAuth client JSON**, enter the full path to the Desktop-app JSON if you plan to send email.
4. Optionally enter exact name, email, and index column headers.
5. Click **Scan & Match**.
6. Read the summary and inspect the table.

**Scan & Match does not send email.** It proposes a mapping between participant records and certificate files. The summary can include:

- **Ready** — records considered eligible by the current matching and validation rules.
- **Unmatched** — participant records without a confident certificate match.
- **Ambiguous** — records that cannot safely be matched to one certificate.
- **Email issues** — invalid or duplicate email addresses.
- **Orphan PDFs** — certificate files not assigned to a participant.

A `Ready` status means the record passed the application's checks; it does not prove that the PDF's contents belong to that person. Check the name and filename yourself before sending.

## 7. Review and export the preflight report

1. Review every row in the match table.
2. Pay special attention to duplicate or similar names, ambiguous matches, missing certificates, duplicate emails, and invalid addresses.
3. Click **Export Preflight CSV**.
4. Open the CSV in a spreadsheet program.
5. Compare participant names, email addresses, statuses, and PDF filenames with your source data and certificates.
6. Correct the source sheet or filenames if needed.
7. After any correction, return to CertMailer and click **Scan & Match** again.

Ambiguous, unmatched, and otherwise ineligible records are not intended to be sent as ready matches. Do not force a questionable match by editing names unless you have independently verified the correct certificate. Orphan PDFs are not automatically sent; investigate them if you expected every PDF to belong to someone.

## 8. Customize and preview the email

### Subject

Edit **Email subject** to the subject line recipients should see, for example:

```text
Your Certificate of Participation
```

The test-send action prefixes the subject with `[TEST]`.

### HTML body

Edit **HTML email body**. The default body is a simple certificate-delivery message. Use `{{ name }}` where the participant's name should appear:

```html
<p>Hello {{ name }},</p>
<p>Thank you for participating.</p>
<p>Please find your certificate attached to this email.</p>
<p>Best regards,<br>Event Team</p>
```

The supported personalization placeholder is `{{ name }}`. Do not assume placeholders such as `{{ email }}` or `{{ index }}` are supported.

### Preview

1. Click **Preview Sample**.
2. Check the TUI log for the sample recipient, subject, attachment filename, and rendered body.
3. Confirm the content looks right.

Previewing does not send email. It is a log-based preview, so inspect the actual test message as the final check.

## 9. Authenticate and send a test

Always test before a live batch.

1. Enter a test-recipient email address in the test-recipient field. Use an inbox you control.
2. Confirm the OAuth client JSON path is correct.
3. Click **Authenticate + Send Test**.
4. If an authorization URL appears, click **Copy URL** and paste it into your browser.
5. Sign in with the intended sending account and approve the requested permission.
6. Return to CertMailer and check the log for success or an error.
7. Open the destination inbox and verify:
   - The message arrived.
   - The subject is correct and has the `[TEST]` prefix.
   - The body and participant name are correct.
   - The PDF attachment is present, opens, and belongs to the expected sample participant.
   - The sender is the expected Google account.

A successful test confirms the authorization and test-send path works. It does not validate every participant mapping or guarantee delivery for all subsequent messages.

## 10. Send the live batch

Only continue after reviewing the preflight report and verifying the test email.

1. Confirm the participant sheet and certificate directory are the intended final versions.
2. Run **Scan & Match** again if either input changed.
3. Review the counts and exported report.
4. Confirm the subject and body are final.
5. Confirm the test email arrived with the correct attachment.
6. Type the exact word `SEND` in the live-send confirmation field.
7. Click **Send Valid Matches**.
8. Review the log and delivery report when the operation finishes.
9. Store the report securely for reconciliation.

The app is designed to send only eligible, confidently matched records. Ambiguous and otherwise ineligible records should be skipped rather than guessed. Check the final report to determine what was actually attempted.

A result marked `accepted` means Gmail accepted the API submission; it does **not** guarantee that the message reached the recipient's inbox. Delivery can be delayed, filtered as spam, or rejected later.

If a batch is interrupted or its outcome is uncertain, do not immediately rerun the whole batch. Review the delivery report and history first. The app intentionally avoids automatically retrying failed or uncertain submissions because a network error can occur after Gmail accepted a message, and a retry could create duplicates.

## 11. Reports and local data

CertMailer uses operating-system-specific user directories through `platformdirs` and prints the resolved paths in the TUI log at startup.

The app data directory contains reports and SQLite delivery history, including preflight/delivery CSVs and `delivery.sqlite3`, which records attempts and helps reconcile previous sends. The app configuration directory contains stored OAuth token data.

On Linux, these paths are commonly below `~/.local/share/` and `~/.config/`, but use the exact paths printed by the app because locations vary by operating system and environment.

Treat reports as private: they can contain participant names, email addresses, filenames, timestamps, and error text.

## Troubleshooting

### Google says the app is not authorized or I am not a test user

- Confirm you signed in with the account listed in **Google Auth Platform → Audience → Test users**.
- Confirm the intended Cloud project is selected.
- Check the app audience and publishing status.
- If the app is being used beyond its test audience, review Google's current OAuth verification requirements.

### The authorization URL does not open automatically

Use **Copy URL**, paste it into your browser, finish Google's consent flow, then return to the TUI. Do not share the full authorization URL publicly.

### Browser authorization succeeds, but CertMailer reports an error

- Return to the TUI and read the latest error line.
- Confirm the JSON is a Desktop/installed-app client configuration.
- Check whether a firewall or endpoint-security tool blocked the local callback.
- Ensure the application and dependencies are installed in the same Python environment.
- Never post access tokens, refresh tokens, client secrets, or full authorization URLs in an issue report.

### Gmail API or permission errors

- Verify the Gmail API is enabled in the correct Cloud project.
- Reauthorize if the OAuth client or requested permission changed.
- Check whether a Google Workspace administrator restricts third-party OAuth applications.
- Do not add unrelated broad scopes as a workaround.

### No participants are Ready

- Check the participant file and PDF directory paths.
- Verify sheet headers or enter exact column overrides.
- Check that PDF filenames contain recognizable participant names.
- Inspect the preflight CSV for missing/duplicate names, invalid emails, or unmatched records.
- Remember that the app does not guess index offsets.

### A participant or PDF is ambiguous/unmatched

Compare the participant name and filename manually, check for duplicate names/candidates, correct the source data or filenames, and scan again. Do not send a certificate if you cannot establish that it belongs to the recipient.

### The TUI appears frozen during a large send

The current prototype sends the live batch sequentially from the UI thread. During a batch, the TUI may stop repainting or responding and may not show live progress. This is a known limitation and does not prove the process has stopped.

- Give the operation time to finish; avoid immediately closing the terminal.
- Do not launch a second batch while the first may still be sending.
- If the process stops or you must interrupt it, inspect the delivery report and SQLite attempt history before deciding whether to resend anything.
- Reconcile uncertain messages individually to reduce duplicate-send risk.

Background sending, live progress, and a responsive/cancellable UI are future improvements and are not implemented in this version.

### A send fails or delivery is uncertain

Check the report and local history before taking action. The app does not automatically retry failed or uncertain submissions. A network error can happen after the provider accepted the message, so retrying blindly may duplicate it.

## Safety notes and known limitations

- **Verify every live batch.** The app cannot know whether the source spreadsheet or filenames are correct.
- **Ambiguous records are intentionally skipped.** Skipped does not mean delivered.
- **No automatic index offset.** Check zero-based versus one-based numbering yourself.
- **Sequential sending can make the TUI appear frozen.** Live progress/background sending is not implemented in this version.
- **No exactly-once guarantee.** History helps reconcile sends but cannot eliminate every uncertain outcome.
- **No automatic retries for uncertain messages.** Reconcile before acting again.
- **Basic email validation.** A plausible address may not exist or accept messages.
- **Limited email templating.** The documented `{{ name }}` placeholder is supported; this is not a general-purpose template engine.
- **Gmail sending limits apply.** Check limits and organizational policies before large batches.
- **Protect personal data.** Keep participant sheets, certificates, OAuth JSON, stored tokens, reports, and the SQLite database private.
- **Keep secrets out of Git.** Do not commit OAuth files, tokens, participant data, reports, or local databases. Review `git status` before committing.

## Official documentation

- [Google Cloud Console](https://console.cloud.google.com/)
- [Gmail API in the API Library](https://console.cloud.google.com/apis/library/gmail.googleapis.com)
- [OAuth 2.0 for Desktop Apps](https://developers.google.com/identity/protocols/oauth2/native-app)
- [Configure the OAuth consent screen](https://developers.google.com/workspace/guides/configure-oauth-consent)
- [Gmail API Python quickstart](https://developers.google.com/workspace/gmail/api/quickstart/python)
- [Send Gmail messages](https://developers.google.com/workspace/gmail/api/guides/sending)

---

CertMailer is a prototype. Test with a controlled recipient and review the manifest before every live send.
