"""
Run this once to create the SEO Audit Tool documentation spreadsheet.
Usage:  python create_docs_sheet.py
"""

from main import authenticate, SCOPES
from googleapiclient.discovery import build

# ── Content ───────────────────────────────────────────────────────────────────

APP_TITLE = "SEO Analysis Automation Tool"

APP_DESCRIPTION = (
    "A Python tool that pulls SEO metrics from 5 data sources and writes them "
    "directly into a pre-formatted Google Sheet. Each run analyses one client "
    "domain at a time. Findings are also exported as bullet points into a "
    "Google Doc SEO Brief. The tool is controlled via a Gradio web UI."
)

INPUT_TEXT  = "Input: Domain selected from a GSC property dropdown in the Overview sheet (B45). City, neighborhoods, building name, and keyword filter are entered manually in B49, B51, B53, B57."
OUTPUT_TEXT = "Output: Data written across the Overview sheet (rows 3–42), an Organic Keywords sheet, a Keyword Mapping sheet per building, and a Google Doc SEO Brief with bullet-point findings."
RUNTIME_TEXT = "Run time: ~2–5 minutes for a full audit. PageSpeed is the slowest (~30s per strategy). SEMrush can take longer for large sites. WHOIS has a 10-second timeout per domain."
SOURCES_TEXT = "Data sources: Google Search Console · Google Analytics 4 · Ahrefs (via MCP) · SEMrush · Google PageSpeed Insights · WHOIS"
CREDENTIALS_TEXT = "Credentials required: Google OAuth token (token.json) · Ahrefs MCP key · SEMrush API key · PageSpeed API key"

HEADERS = ["Action Item", "How It Works", "Libraries / Access / Tokens Required"]

ROWS = [
    [
        "0 · Sync All Properties",
        "Fetches all GSC properties via the Search Console API and all GA4 properties via the Analytics Admin API. Populates 'GSC websites' and 'GA4 properties' tabs. Creates dropdown menus in Overview B45 (GSC) and B47 (GA4) so the user can select which property to audit.",
        "Google Search Console API v1 · Google Analytics Admin API v1alpha · OAuth 2.0 (token.json) · google-api-python-client"
    ],
    [
        "3 · Domain Age",
        "Reads the selected GSC property from B45, strips the protocol and sc-domain: prefix to get the bare domain, then performs a WHOIS lookup with a 10-second socket timeout. Calculates age in years from the earliest creation date found. Writes the numeric age to B3 and a commentary to G3.",
        "python-whois · standard library socket (timeout)"
    ],
    [
        "4 · Sync CTR from GSC",
        "Reads the selected GSC property URL from B45. Queries the Search Console Search Analytics API for the last 90 days with no dimension grouping to get the aggregate click-through rate. Writes the decimal CTR to B4 and a 'Good CTR' / 'Low CTR' label to G4.",
        "Google Search Console API v1 · OAuth 2.0 (token.json) · google-api-python-client"
    ],
    [
        "5 · GA4 Report",
        "Reads the GA4 property name from B47 and looks up its numeric property ID in the 'GA4 properties' sheet. Runs two GA4 Data API reports filtered to Organic Search sessions for the last 90 days: (1) aggregate traffic metrics — sessions, engagement rate, avg session duration, key events — written to B33:B36; (2) top 5 landing pages by sessions written to B38:D42. Writes an engagement commentary to G34 and a landing page summary to G38.",
        "Google Analytics Data API v1beta · OAuth 2.0 (token.json) · google-api-python-client"
    ],
    [
        "7 · Ahrefs Data",
        "Reads the bare domain from B45. Makes four sequential MCP JSON-RPC calls to the Ahrefs MCP endpoint (https://api.ahrefs.com/mcp/mcp) using a Bearer token. Handles both plain JSON and Server-Sent Events (SSE) responses. Fetches: Domain Rating → B11; URL Rating history (last 90 days, monthly) → C11; live referring domains count → B12; top 5 anchors by referring domains → B15:C19. Calculates the top anchor as a % of total referring domains → D15 and writes a backlink diversity commentary → G15.",
        "Ahrefs MCP API (https://api.ahrefs.com/mcp/mcp) · AHREFS_API_KEY (MCP Bearer token) · requests"
    ],
    [
        "8 · SEMrush Data",
        "Reads the bare domain from B45. Calls the SEMrush domain_organic report API with paginated requests (up to 10,000 rows per page) for the US database, retrieving keyword, position, search volume, URL, and intent. Maps numeric intent codes to labels (Commercial, Informational, Navigational, Transactional). Writes all rows to the 'Organic Keywords All & Keyword Mapping' sheet. Counts keywords in position ranges 1–3, 4–10, 11–100 → B22:B24. Finds the top 5 keywords in positions 4–20 filtered by the keyword in B57 + city/neighborhood, with two fallback levels, and writes them to B27:D31.",
        "SEMrush API (https://api.semrush.com/) · SEMRUSH_API_KEY · requests"
    ],
    [
        "9 · PageSpeed Insights",
        "Reads the bare domain from B45 and constructs the full https:// URL. Calls the Google PageSpeed Insights API v5 twice — once for desktop and once for mobile — requesting the performance category. Extracts the Lighthouse performance score (0–100) from the response. Writes the mobile score to B7, the desktop score to C7, and a speed commentary to G7.",
        "Google PageSpeed Insights API v5 · PAGESPEED_API_KEY · requests"
    ],
    [
        "10 · Keyword Mapping",
        "Reads all rows from the 'Organic Keywords All & Keyword Mapping' sheet (populated by SEMrush Data). Reads building name (B53), city (B49), neighborhoods (B51), and luxury mode (B55) from Overview. Classifies each keyword into: branded (contains building name tokens), primary (keyword filter + city), tracking only (keyword filter + neighborhood), or secondary (everything else). Creates a brand-new standalone Google Spreadsheet titled 'Keyword Mapping {building name}' with the first 5 SEMrush columns plus a Category column. Applies green row highlights to primary keywords.",
        "Google Sheets API v4 · OAuth 2.0 (token.json) · gspread · google-api-python-client"
    ],
    [
        "1 · Run All Auto-Analysis",
        "Reads pre-existing numeric values from the Overview sheet and writes commentary to column G. Checks: Trust Flow (B9) → backlink quality label (G9); Domain Rating (B11) → DR quality label (G11); Site Audit Health Score (B13) → health score label (G13). Does not call any external APIs — purely formula-based commentary on existing data.",
        "gspread (reads/writes Overview sheet only) · No external API"
    ],
    [
        "6 · Export Findings to SEO Brief",
        "Reads all non-empty cells in column G (rows 3–38) of the Overview sheet — these are the commentary strings written by other functions. Fetches the Google Doc body and locates the 'Findings' heading by scanning text runs. Inserts each finding as a bullet point after the heading using the Google Docs batchUpdate API, formatted in Host Grotesk 11pt. Items are inserted in reverse order so they appear in the correct sequence.",
        "Google Docs API v1 · OAuth 2.0 (token.json) · google-api-python-client"
    ],
    [
        "11 · Run Full Audit",
        "Master function that runs all audit steps in the correct order: Domain Age (3) → CTR from GSC (4) → PageSpeed (9) → SEMrush Data (8) → Keyword Mapping (10) → GA4 Report (5) → Ahrefs Data (7) → Auto-Analysis (1) → Export to SEO Brief (6). Each step is wrapped in a try/except so a failure in one step does not stop the rest. Prints progress with step numbers.",
        "All libraries from each individual function above"
    ],
    [
        "12 · Clean All Data",
        "Resets the workspace for a new client. Clears all data cells in Overview written by any function (B3:G38 relevant cells), plus the config cells B45, B47, B49, B51, B53, B55, B57. Clears the 'Organic Keywords All & Keyword Mapping' sheet and removes all green cell highlights from it. Deletes all bullet points below the 'Findings' heading in the Google Doc SEO Brief (scans paragraph-by-paragraph from bottom to top to preserve indices).",
        "Google Sheets API v4 · Google Docs API v1 · gspread · google-api-python-client"
    ],
]

# ── Create the spreadsheet ────────────────────────────────────────────────────

def create_docs_spreadsheet():
    creds      = authenticate()
    sheets_svc = build('sheets', 'v4', credentials=creds)

    # Create new spreadsheet
    ss = sheets_svc.spreadsheets().create(body={
        "properties": {"title": "SEO Audit Tool — Documentation"},
        "sheets": [{"properties": {"title": "Overview"}}]
    }).execute()

    ss_id    = ss["spreadsheetId"]
    sheet_id = ss["sheets"][0]["properties"]["sheetId"]
    url      = f"https://docs.google.com/spreadsheets/d/{ss_id}"
    print(f"  Created: {url}")

    # ── Build all values ──────────────────────────────────────────────────────
    values = [
        [APP_TITLE],
        [""],
        [APP_DESCRIPTION],
        [""],
        [INPUT_TEXT],
        [OUTPUT_TEXT],
        [RUNTIME_TEXT],
        [SOURCES_TEXT],
        [CREDENTIALS_TEXT],
        [""],
        HEADERS,
    ] + ROWS

    sheets_svc.spreadsheets().values().update(
        spreadsheetId=ss_id,
        range="A1",
        valueInputOption="RAW",
        body={"values": values}
    ).execute()

    # ── Formatting requests ───────────────────────────────────────────────────
    DARK_BLUE  = {"red": 0.122, "green": 0.259, "blue": 0.490}   # #1F4279
    WHITE      = {"red": 1.0,   "green": 1.0,   "blue": 1.0}
    LIGHT_GRAY = {"red": 0.949, "green": 0.949, "blue": 0.949}   # #F2F2F2

    header_row_idx = 10   # row 11 (0-indexed = 10)
    first_data_row = 11

    format_requests = [
        # ── Title row (A1): large bold ────────────────────────────────────────
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1,
                          "startColumnIndex": 0, "endColumnIndex": 3},
                "cell": {"userEnteredFormat": {
                    "textFormat": {"bold": True, "fontSize": 16},
                    "backgroundColor": WHITE
                }},
                "fields": "userEnteredFormat(textFormat,backgroundColor)"
            }
        },
        # ── Description / meta rows (rows 3–9): italic gray background ───────
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 2, "endRowIndex": 9,
                          "startColumnIndex": 0, "endColumnIndex": 3},
                "cell": {"userEnteredFormat": {
                    "textFormat": {"italic": True, "fontSize": 10},
                    "backgroundColor": LIGHT_GRAY,
                    "wrapStrategy": "WRAP"
                }},
                "fields": "userEnteredFormat(textFormat,backgroundColor,wrapStrategy)"
            }
        },
        # ── Header row: dark blue background, white bold text ─────────────────
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id,
                          "startRowIndex": header_row_idx, "endRowIndex": header_row_idx + 1,
                          "startColumnIndex": 0, "endColumnIndex": 3},
                "cell": {"userEnteredFormat": {
                    "backgroundColor": DARK_BLUE,
                    "textFormat": {"bold": True, "fontSize": 11,
                                   "foregroundColor": WHITE},
                    "horizontalAlignment": "CENTER"
                }},
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"
            }
        },
        # ── Data rows: wrap text, normal size ────────────────────────────────
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id,
                          "startRowIndex": first_data_row,
                          "endRowIndex": first_data_row + len(ROWS),
                          "startColumnIndex": 0, "endColumnIndex": 3},
                "cell": {"userEnteredFormat": {
                    "wrapStrategy": "WRAP",
                    "textFormat": {"fontSize": 10},
                    "verticalAlignment": "TOP"
                }},
                "fields": "userEnteredFormat(wrapStrategy,textFormat,verticalAlignment)"
            }
        },
        # ── Alternate row shading ─────────────────────────────────────────────
        *[
            {
                "repeatCell": {
                    "range": {"sheetId": sheet_id,
                              "startRowIndex": first_data_row + i,
                              "endRowIndex": first_data_row + i + 1,
                              "startColumnIndex": 0, "endColumnIndex": 3},
                    "cell": {"userEnteredFormat": {
                        "backgroundColor": LIGHT_GRAY if i % 2 == 0 else WHITE
                    }},
                    "fields": "userEnteredFormat.backgroundColor"
                }
            }
            for i in range(len(ROWS))
        ],
        # ── Column widths ─────────────────────────────────────────────────────
        {"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                      "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 220},
            "fields": "pixelSize"
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                      "startIndex": 1, "endIndex": 2},
            "properties": {"pixelSize": 500},
            "fields": "pixelSize"
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                      "startIndex": 2, "endIndex": 3},
            "properties": {"pixelSize": 320},
            "fields": "pixelSize"
        }},
        # ── Merge A1:C1 for title ─────────────────────────────────────────────
        {"mergeCells": {
            "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1,
                      "startColumnIndex": 0, "endColumnIndex": 3},
            "mergeType": "MERGE_ALL"
        }},
    ]

    sheets_svc.spreadsheets().batchUpdate(
        spreadsheetId=ss_id,
        body={"requests": format_requests}
    ).execute()

    print(f"✅ Documentation spreadsheet created:\n   {url}")


if __name__ == "__main__":
    create_docs_spreadsheet()
