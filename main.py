import gspread
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from datetime import date, timedelta
import os
import json
import requests
import whois

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/documents',
    'https://www.googleapis.com/auth/webmasters.readonly',
    'https://www.googleapis.com/auth/analytics.readonly',
    'https://www.googleapis.com/auth/analytics.manage.users.readonly'
]

SPREADSHEET_ID   = '17qIKtK9YS9JI0bhhSXUltleh5Lwnrc6xTjbceFtMjkg'
DOC_ID           = '17M22Ba_xKgsT8OTGbZIc5Pw5yS8Ap-1fy7OCorUr7PI'
GSC_ACCOUNT      = 'PPC@premieronlinemarketing.com'
CTR_CELL         = 'B45'  # GSC property dropdown
GA4_CELL         = 'B47'  # GA4 property dropdown
AHREFS_API_KEY     = "j_On.MbAOsd7LEWgStWIpQOSh6TpuZFdMVU91bGVxMWlobkhZa3NVSHJuemRicXJLT0pLSWlvSWhzdnRBZzl1dVdhNUtadWh5YVZHMGM4MUtzcDZZZXpDa0dFRDIrZzNCMmxaWmNhVTJ2Wm1LcllQOGRVT21CNDZsNUl0RjVLQXh3TTBzM1NRcnJTQTNnZ0E.FjLj" # MCP key
AHREFS_MCP_URL     = "https://api.ahrefs.com/mcp/mcp"
SEMRUSH_API_KEY    = "39d3c121bd5ef6b9ea25ab75e1210624"
SEMRUSH_BASE_URL   = "https://api.semrush.com/"
PAGESPEED_API_KEY  = "AIzaSyCSXyKUU7oiw7ZUAyOiqQk3Xpy5s8AAZEI"   # optional — leave empty to use without key (rate-limited)


# ── Auth ──────────────────────────────────────────────────────────────────────

def authenticate():
    # On HF Spaces, bootstrap credential files from environment secrets
    token_env = os.environ.get('GOOGLE_TOKEN_JSON')
    creds_env = os.environ.get('GOOGLE_CREDENTIALS_JSON')
    if token_env and not os.path.exists('token.json'):
        with open('token.json', 'w') as f:
            f.write(token_env)
    if creds_env and not os.path.exists('credentials.json'):
        with open('credentials.json', 'w') as f:
            f.write(creds_env)

    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
        else:
            if not os.path.exists('credentials.json'):
                raise RuntimeError(
                    "No credentials found. Set GOOGLE_TOKEN_JSON and "
                    "GOOGLE_CREDENTIALS_JSON as Space secrets."
                )
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0, prompt='select_account')
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
    return creds


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_sheets(creds):
    client   = gspread.authorize(creds)
    ss       = client.open_by_key(SPREADSHEET_ID)
    overview = ss.worksheet("Overview")
    return ss, overview


def get_ga4_property_id(creds):
    """Read selected property name from B47, look up its ID in 'GA4 properties' sheet."""
    ss, overview = get_sheets(creds)
    prop_name    = overview.acell(GA4_CELL).value
    if not prop_name:
        print(f"❌ No GA4 property selected in Overview!{GA4_CELL}. Run option 0 first.")
        return None, None
    try:
        ga4_sheet = ss.worksheet("GA4 properties")
    except:
        print("❌ 'GA4 properties' sheet not found. Run option 0 first.")
        return None, None
    for row in ga4_sheet.get('A2:B'):
        if row and row[0] == prop_name:
            return prop_name, row[1]
    print(f"❌ Could not find property ID for '{prop_name}'.")
    return None, None


def fmt_duration(seconds):
    """Convert seconds to Xm XXs string."""
    s    = round(float(seconds))
    mins = s // 60
    secs = s % 60
    return f"{mins}m {secs:02d}s"


def get_domain_age(domain):
    """Return domain age in years (float) via WHOIS, or None on failure."""
    import socket
    original_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(10)
        w = whois.whois(domain)
        creation_date = w.creation_date
        if isinstance(creation_date, list):
            creation_date = creation_date[0]
        if creation_date:
            return round((date.today() - creation_date.date()).days / 365.25, 1)
    except Exception as e:
        print(f"  ⚠️ WHOIS lookup failed: {e}")
    finally:
        socket.setdefaulttimeout(original_timeout)
    return None


# ── 1. Sync all properties (GSC + GA4) ───────────────────────────────────────

def sync_all_properties(creds):
    """Fetch all GSC and GA4 properties and populate their sheets + dropdowns."""
    ss, overview  = get_sheets(creds)
    sheets_svc    = build('sheets', 'v4', credentials=creds)
    overview_id   = overview._properties['sheetId']

    # ── GSC ──────────────────────────────────────────────────────────────────
    webmasters = build('searchconsole', 'v1', credentials=creds)
    sites      = webmasters.sites().list().execute().get('siteEntry', [])

    try:
        gsc_sheet = ss.worksheet("GSC websites")
    except:
        gsc_sheet = ss.add_worksheet(title="GSC websites", rows=100, cols=2)

    gsc_sheet.clear()
    gsc_sheet.update('A1', [['Property Name', 'URL']])
    gsc_rows = []
    for site in sites:
        url  = site.get('siteUrl', '')
        name = url.replace('https://', '').replace('http://', '').replace('sc-domain:', '').strip('/')
        gsc_rows.append([name, url])
    if gsc_rows:
        gsc_sheet.update(f'A2:B{1 + len(gsc_rows)}', gsc_rows)

    # ── GA4 ──────────────────────────────────────────────────────────────────
    admin      = build('analyticsadmin', 'v1alpha', credentials=creds)
    accounts   = []
    page_token = None
    while True:
        params = {'pageSize': 200}
        if page_token:
            params['pageToken'] = page_token
        resp       = admin.accounts().list(**params).execute()
        accounts  += resp.get('accounts', [])
        page_token = resp.get('nextPageToken')
        if not page_token:
            break

    ga4_props  = []
    for account in accounts:
        account_id = account['name']
        page_token = None
        while True:
            params = {'pageSize': 200, 'filter': f'parent:{account_id}'}
            if page_token:
                params['pageToken'] = page_token
            try:
                resp       = admin.properties().list(**params).execute()
                ga4_props += resp.get('properties', [])
                page_token = resp.get('nextPageToken')
                if not page_token:
                    break
            except Exception as e:
                print(f"  ⚠️ Skipped account {account_id}: {e}")
                break

    try:
        ga4_sheet = ss.worksheet("GA4 properties")
    except:
        ga4_sheet = ss.add_worksheet(title="GA4 properties", rows=1000, cols=3)

    ga4_sheet.clear()
    ga4_sheet.update('A1', [['Property Name', 'Property ID', 'Account']])
    ga4_rows = []
    for prop in ga4_props:
        ga4_rows.append([
            prop.get('displayName', ''),
            prop.get('name', '').replace('properties/', ''),
            prop.get('parent', '').replace('accounts/', '')
        ])
    if ga4_rows:
        ga4_sheet.update(f'A2:C{1 + len(ga4_rows)}', ga4_rows)

    # ── Dropdowns ─────────────────────────────────────────────────────────────
    requests = [
        {   # GSC dropdown → B45
            'setDataValidation': {
                'range': {'sheetId': overview_id, 'startRowIndex': 44, 'endRowIndex': 45,
                          'startColumnIndex': 1, 'endColumnIndex': 2},
                'rule': {
                    'condition': {'type': 'ONE_OF_RANGE',
                                  'values': [{'userEnteredValue': f"='GSC websites'!$B$2:$B${1 + len(gsc_rows)}"}]},
                    'showCustomUi': True, 'strict': True
                }
            }
        },
        {   # GA4 dropdown → B47
            'setDataValidation': {
                'range': {'sheetId': overview_id, 'startRowIndex': 46, 'endRowIndex': 47,
                          'startColumnIndex': 1, 'endColumnIndex': 2},
                'rule': {
                    'condition': {'type': 'ONE_OF_RANGE',
                                  'values': [{'userEnteredValue': f"='GA4 properties'!$A$2:$A${1 + len(ga4_rows)}"}]},
                    'showCustomUi': True, 'strict': True
                }
            }
        }
    ]
    sheets_svc.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID, body={'requests': requests}
    ).execute()

    print(f"✅ {len(gsc_rows)} GSC properties synced → 'GSC websites' | Dropdown → Overview!B45")
    print(f"✅ {len(ga4_rows)} GA4 properties synced → 'GA4 properties' | Dropdown → Overview!B47")


# ── 2. Run all auto-analysis (col B → col G) ─────────────────────────────────

def run_auto_analysis(creds):
    """Run all 6 auto-analysis checks in one shot (reads col B, writes col G)."""
    _, overview = get_sheets(creds)

    # Backlink Quality (Trust Flow) — B9
    val = overview.acell('B9').value
    if val:
        tf = float(val)
        if tf > 50:    msg = "Trust flow is excellent. Keep it by fixing NAP errors if needed."
        elif tf >= 10: msg = "Trust flow is average; building relevant authority citations is important for ranking."
        else:          msg = "Trust flow is poor; building relevant authority citations is important for ranking."
        overview.update('G9', [[msg]])
        print("✅ Backlink Quality done.")

    # Domain Rating — B11
    val = overview.acell('B11').value
    if val:
        dr = float(val)
        if dr >= 30:   msg = "Excellent domain rating"
        elif dr >= 20: msg = "Good domain rating"
        elif dr >= 10: msg = "Average domain rating"
        else:          msg = "Low domain rating. It needs improvement by acquiring do-follow backlinks."
        overview.update('G11', [[msg]])
        print("✅ Domain Overview done.")

    # Site Audit Health Score — B13
    val = overview.acell('B13').value
    if val:
        score = float(val)
        if score >= 89:   msg = "Good website health score."
        elif score < 85:  msg = "Bad website health score. Improve it by fixing technical errors."
        else:             msg = ""
        if msg:
            overview.update('G13', [[msg]])
        print("✅ Site Audit Health Score done.")

    print("✅ All auto-analysis complete.")


# ── 3. Domain Age ────────────────────────────────────────────────────────────

def domain_age(creds):
    _, overview = get_sheets(creds)
    raw = overview.acell(CTR_CELL).value
    if not raw:
        print("❌ No domain selected.")
        return

    domain = raw.strip().replace("sc-domain:", "").replace("https://", "").replace("http://", "").strip("/")
    age = get_domain_age(domain)
    if age is not None:
        overview.update('B3', [[age]])
        msg = ("Young domain. A new domain will take longer to rank." if age < 1
               else f"Domain age of {age}. Good domain age.")
        overview.update('G3', [[msg]])
        print(f"✅ Domain age written to B3: {age} years")


# ── 5. Sync CTR from GSC ──────────────────────────────────────────────────────

def ctr_percentage(creds):
    """Read selected GSC property from B45, pull last 3 months CTR, write to B4."""
    _, overview = get_sheets(creds)
    site_url    = overview.acell(CTR_CELL).value
    if not site_url:
        print(f"❌ No website selected in Overview!{CTR_CELL}. Run option 0 first.")
        return

    end_date   = date.today() - timedelta(days=3)
    start_date = end_date - timedelta(days=90)

    webmasters = build('searchconsole', 'v1', credentials=creds)
    response   = webmasters.searchanalytics().query(
        siteUrl=site_url,
        body={'startDate': start_date.isoformat(), 'endDate': end_date.isoformat(), 'dimensions': []}
    ).execute()

    rows = response.get('rows', [])
    if not rows:
        print(f"❌ No Search Console data found for {site_url}.")
        return

    ctr = rows[0].get('ctr', 0)
    overview.update('B4', [[ctr]])
    overview.update('G4', [["Good CTR" if ctr >= 0.03 else "Low CTR"]])
    print(f"✅ CTR pulled from GSC for {site_url}: {ctr:.2%}")


# ── 5. GA4 Report (Traffic + Landing Pages) ───────────────────────────────────

def ga4_report(creds):
    """Pull organic traffic metrics and top 5 landing pages from GA4 in one call."""
    _, overview       = get_sheets(creds)
    prop_name, prop_id = get_ga4_property_id(creds)
    if not prop_id:
        return

    end_date   = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=90)
    analytics  = build('analyticsdata', 'v1beta', credentials=creds)

    organic_filter = {
        'filter': {
            'fieldName': 'sessionDefaultChannelGroup',
            'stringFilter': {'matchType': 'EXACT', 'value': 'Organic Search'}
        }
    }

    # ── Traffic metrics ───────────────────────────────────────────────────────
    traffic = analytics.properties().runReport(
        property=f'properties/{prop_id}',
        body={
            'dateRanges':      [{'startDate': start_date.isoformat(), 'endDate': end_date.isoformat()}],
            'metrics':         [{'name': 'sessions'}, {'name': 'engagementRate'},
                                {'name': 'averageSessionDuration'}, {'name': 'keyEvents'}],
            'dimensionFilter': organic_filter
        }
    ).execute()

    t_rows = traffic.get('rows', [])
    if t_rows:
        vals         = t_rows[0]['metricValues']
        sessions     = int(float(vals[0]['value']))
        eng_rate_num = round(float(vals[1]['value']), 4)
        eng_rate     = f"{round(eng_rate_num * 100, 2)}%"
        avg_time     = fmt_duration(vals[2]['value'])
        key_events   = int(float(vals[3]['value']))

        overview.update('B33', [[sessions]])
        overview.update('B34', [[eng_rate]])
        overview.update('B35', [[avg_time]])
        overview.update('B36', [[key_events]])
        overview.update('G34', [[
            "Healthy engagement rate." if eng_rate_num >= 0.6
            else "Low engagement rate. Improve conversion rate optimization."
        ]])
        print(f"✅ GA4 Traffic: Sessions={sessions} | Engagement={eng_rate} | Avg Duration={avg_time} | Key Events={key_events}")

    # ── Top 5 landing pages ───────────────────────────────────────────────────
    lp = analytics.properties().runReport(
        property=f'properties/{prop_id}',
        body={
            'dateRanges':      [{'startDate': start_date.isoformat(), 'endDate': end_date.isoformat()}],
            'dimensions':      [{'name': 'landingPage'}],
            'metrics':         [{'name': 'sessions'}, {'name': 'averageSessionDuration'}],
            'dimensionFilter': organic_filter,
            'orderBys':        [{'metric': {'metricName': 'sessions'}, 'desc': True}],
            'limit':           5
        }
    ).execute()

    lp_rows = lp.get('rows', [])
    if lp_rows:
        pages   = []
        cleaned = []
        for row in lp_rows:
            path     = row['dimensionValues'][0]['value']
            sessions = int(row['metricValues'][0]['value'])
            avg_dur  = fmt_duration(row['metricValues'][1]['value'])
            pages.append([path, sessions, avg_dur])
            if not path or '(not set)' in path.lower():
                continue
            cleaned.append('homepage' if path == '/' else path.strip('/').split('/')[-1].replace('-', ' '))

        overview.update('B38:B42', [[p[0]] for p in pages])
        overview.update('C38:C42', [[p[1]] for p in pages])
        overview.update('D38:D42', [[p[2]] for p in pages])
        if cleaned:
            overview.update('G38', [[f"The core pages are {', '.join(cleaned)}"]])
        print(f"✅ Top 5 Landing Pages written for '{prop_name}'.")


# ── 7. Ahrefs Data ────────────────────────────────────────────────────────────

def ahrefs_data(creds):
    """Pull DR, UR, referring domains and top 5 anchors via Ahrefs API v3.

    Reads domain from Overview!B45.
    Writes:
      B11 → Domain Rating (DR)
      C11 → URL Rating (UR, homepage)
      B12 → Referring domains count
      B15:B19 → Top 5 anchor texts
      C15:C19 → Top 5 anchor referring domains
      D15 → Top anchor % of total referring domains
    """
    _, overview = get_sheets(creds)
    raw = overview.acell(CTR_CELL).value
    if not raw or not raw.strip():
        print(f"❌ No domain found in Overview!{CTR_CELL}. Select a GSC website first (run option 0).")
        return

    domain = raw.strip().replace("sc-domain:", "").replace("https://", "").replace("http://", "").strip("/")
    print(f"  Fetching Ahrefs data for: {domain}...")

    today            = date.today().strftime("%Y-%m-%d")
    three_months_ago = (date.today() - timedelta(days=90)).strftime("%Y-%m-%d")

    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {AHREFS_API_KEY}",
        "Content-Type":  "application/json",
        "Accept":        "application/json, text/event-stream",
    })

    def mcp_call(req_id, tool_name, arguments):
        resp = session.post(
            AHREFS_MCP_URL,
            json={"jsonrpc": "2.0", "id": req_id, "method": "tools/call",
                  "params": {"name": tool_name, "arguments": arguments}},
            timeout=30
        )
        if resp.status_code != 200:
            raise ValueError(f"MCP {resp.status_code}: {resp.text[:200]}")

        # MCP server may respond with SSE (text/event-stream) or plain JSON
        if "text/event-stream" in resp.headers.get("Content-Type", ""):
            payload = None
            for line in resp.text.splitlines():
                line = line.strip()
                if line.startswith("data:"):
                    data = line[5:].strip()
                    if data and data != "[DONE]":
                        payload = json.loads(data)
                        break
            if payload is None:
                raise ValueError("Empty SSE response from MCP")
        else:
            payload = resp.json()

        if "error" in payload:
            raise ValueError(f"MCP error: {payload['error']}")

        content = payload.get("result", {}).get("content", [])
        if not content:
            raise ValueError("Empty content in MCP result")
        return json.loads(content[0]["text"])

    try:
        # Domain Rating
        print("  Fetching DR...")
        dr_data       = mcp_call(1, "site-explorer-domain-rating",
                                  {"target": domain, "mode": "domain", "date": today})
        domain_rating = dr_data.get("domain_rating", {}).get("domain_rating")

        # URL Rating (most recent monthly snapshot)
        print("  Fetching UR...")
        ur_data     = mcp_call(2, "site-explorer-url-rating-history",
                                {"target": f"https://{domain}/",
                                 "date_from": three_months_ago, "date_to": today,
                                 "history_grouping": "monthly"})
        url_ratings = ur_data.get("url_ratings", [])
        url_rating  = url_ratings[-1]["url_rating"] if url_ratings else None

        # Referring domains (live count)
        print("  Fetching referring domains...")
        bs_data    = mcp_call(3, "site-explorer-backlinks-stats",
                               {"target": domain, "mode": "domain", "date": today})
        refdomains = bs_data.get("metrics", {}).get("live_refdomains")

        # Top 5 anchors
        print("  Fetching top anchors...")
        anch_data   = mcp_call(4, "site-explorer-anchors",
                                {"target": domain, "mode": "domain",
                                 "select": "anchor,refdomains",
                                 "limit": 5, "order_by": "refdomains:desc",
                                 "history": "live"})
        top_anchors = anch_data.get("anchors", [])

    except Exception as e:
        print(f"❌ Ahrefs error: {e}")
        return

    # ── Write to Overview ────────────────────────────────────────────────────
    if domain_rating is not None:
        overview.update('B11', [[domain_rating]])
    if url_rating is not None:
        overview.update('C11', [[url_rating]])
    if refdomains is not None:
        overview.update('B12', [[refdomains]])

    # Top 5 anchors — pad to 5 rows so stale data is always cleared
    anchor_texts = [[a.get("anchor", "")] for a in top_anchors]
    anchor_refs  = [[a.get("refdomains", "")] for a in top_anchors]
    while len(anchor_texts) < 5:
        anchor_texts.append([""])
        anchor_refs.append([""])
    overview.update('B15:B19', anchor_texts)
    overview.update('C15:C19', anchor_refs)

    # D15 + G15 — top anchor as % of total referring domains + commentary
    if top_anchors and refdomains:
        top_refs = top_anchors[0].get("refdomains", 0)
        pct      = round((top_refs / refdomains) * 100, 2)
        overview.update('D15', [[f"{pct}%"]])
        if pct > 50:
            g15 = ("High percentage of branded anchors. A healthy balance would be 50% branded anchors, "
                   "20% naked URLs, 15% generic anchors, 10% partial match anchors, 5% exact-match anchors. "
                   "Disavow spammy links if needed.")
        else:
            g15 = "Low percentage of branded anchors. Build authoritative backlinks using the brand name. Disavow spammy links if needed."
        overview.update('G15', [[g15]])

    # ── Print summary ────────────────────────────────────────────────────────
    print(f"\n── Ahrefs Data: {domain} ──────────────────────")
    print(f"  DR: {domain_rating}  |  UR: {url_rating}  |  Referring Domains: {refdomains}")
    print(f"  Top 5 Anchors:")
    for a in top_anchors:
        print(f"    {a.get('anchor', '(none)'):<40}  {a.get('refdomains', 0)} refdomains")
    print("✅ Ahrefs data written → B11 (DR) | C11 (UR) | B12 (ref domains) | B15:C19 (anchors) | D15 (%) | G15 (analysis)")


# ── 8. SEMrush Data ───────────────────────────────────────────────────────────

INTENT_MAP = {
    "0": "Commercial",
    "1": "Informational",
    "2": "Navigational",
    "3": "Transactional"
}

def map_intent(intent_str):
    intents = intent_str.split(",")
    mapped = []
    for i in intents:
        i = i.strip().split(".")[0]  # take only the part before the decimal
        mapped.append(INTENT_MAP.get(i, i))
    return ", ".join(mapped)

def semrush_data(creds):
    _, overview = get_sheets(creds)
    raw = overview.acell(CTR_CELL).value
    if not raw or not raw.strip():
        print(f"❌ No domain found in Overview!{CTR_CELL}. Select a GSC website first (run option 0).")
        return

    domain = raw.strip().replace("sc-domain:", "").replace("https://", "").replace("http://", "").strip("/")

    city          = (overview.acell('B49').value or "").strip()
    neighborhoods = [n.strip() for n in (overview.acell('B51').value or "").split(",") if n.strip()]
    kw_filter     = (overview.acell('B57').value or "").strip().lower()
    missing = []
    if not city:
        missing.append("City (Overview!B49)")
    if not neighborhoods:
        missing.append("Neighborhood (Overview!B51)")
    if not kw_filter:
        missing.append("Keyword filter (Overview!B57)")
    if missing:
        print(f"❌ Missing required fields: {', '.join(missing)}. Please fill them in before running.")
        return

    print(f"  Analysing domain: {domain} | City: {city} | Neighborhoods: {', '.join(neighborhoods)}")

    all_rows = []
    headers  = None
    offset   = 0
    limit    = 10000

    while True:
        response = requests.get(SEMRUSH_BASE_URL, params={
            "type":           "domain_organic",
            "key":            SEMRUSH_API_KEY,
            "domain":         domain,
            "database":       "us",
            "export_columns": "Ph,Po,Nq,Ur,In",
            "display_limit":  limit,
            "display_offset": offset,
        })
        text = response.text.strip()

        if not text or text.startswith("ERROR"):
            if offset == 0:
                print(f"❌ SEMrush error: {text}")
            break

        lines = [l for l in text.splitlines() if l.strip()]
        if headers is None:
            headers = lines[0].split(";")

        rows = [line.split(";") for line in lines[1:]]
        all_rows.extend(rows)

        if len(rows) < limit:
            break
        offset += limit

    if not all_rows:
        print("❌ No data returned from SEMrush.")
        return

    # Map intent numbers to names
    try:
        intent_idx = headers.index("Intents")
        for row in all_rows:
            if len(row) > intent_idx:
                row[intent_idx] = map_intent(row[intent_idx])
    except ValueError:
        print("⚠️ 'Intents' column not found in headers, skipping intent mapping.")

    ss, _ = get_sheets(creds)
    try:
        kw_sheet = ss.worksheet("Organic Keywords All & Keyword Mapping")
        kw_sheet.clear()
    except Exception:
        kw_sheet = ss.add_worksheet(title="Organic Keywords All & Keyword Mapping", rows=len(all_rows) + 2, cols=len(headers))

    kw_sheet.update('A1', [headers] + all_rows)
    print(f"✅ {len(all_rows)} keywords written to 'Organic Keywords All & Keyword Mapping' for {domain}.")

    # Count keywords by position range (column B = Position)
    top3 = top10 = top100 = 0
    for row in all_rows:
        try:
            pos = int(row[1])
        except (ValueError, IndexError):
            continue
        if pos <= 3:
            top3  += 1
        if pos <= 10:
            top10 += 1
        if pos <= 100:
            top100 += 1

    overview.update('B22', [[top3]])
    overview.update('B23', [[top10 - top3]])
    overview.update('B24', [[top100 - top10]])
    print(f"✅ Position counts → B22: {top3} (1-3) | B23: {top10 - top3} (4-10) | B24: {top100 - top10} (11-100)")

    # Top 5 keywords (pos 4-20) sorted by search volume descending → B27:D31
    # Filter: B57 keyword + any neighborhood; fallback: B57 keyword only; fallback: top by SV
    # Guard: skip entirely if the keyword sheet has no data
    if not all_rows:
        print("⚠️ 'Organic Keywords All & Keyword Mapping' is empty — skipping B27:D31.")
        return

    mid_range = []
    for row in all_rows:
        try:
            pos = int(row[1])
            sv  = int(row[2])
        except (ValueError, IndexError):
            continue
        if 4 <= pos <= 20:
            mid_range.append((row[0], pos, sv))

    # Always clear first so old data never lingers
    overview.batch_clear(['B27:B31', 'C27:C31', 'D27:D31'])

    location_terms = [city.lower()] + [n.lower() for n in neighborhoods]
    filtered = [
        (kw, pos, sv) for kw, pos, sv in mid_range
        if kw_filter in kw.lower()
        and any(loc in kw.lower() for loc in location_terms)
    ]
    if not filtered:
        # Fallback 1: kw_filter mandatory, no location requirement
        filtered = [(kw, pos, sv) for kw, pos, sv in mid_range if kw_filter in kw.lower()]
    if not filtered:
        # Fallback 2: no match found — use top keywords by search volume
        filtered = mid_range
        print(f"⚠️ No '{kw_filter}' keywords found in positions 4-20 — using top keywords by search volume.")

    filtered.sort(key=lambda x: x[2], reverse=True)
    top5 = filtered[:5]

    if top5:
        overview.update('B27:B31', [[kw]  for kw, _, _  in top5])
        overview.update('C27:C31', [[pos] for _, pos, _ in top5])
        overview.update('D27:D31', [[sv]  for _, _, sv  in top5])
        print(f"✅ Top 5 keywords (pos 4-20 by SV) written to Overview B27:D31")
        total_sv = sum(sv for _, _, sv in top5)
        if total_sv >= 100:
            overview.update('G27', [["Plenty of opportunities in the top 4-20 to increase rankings for high SV terms."]])
        else:
            overview.update('G27', [["Good opportunities in the top 4-20 to increase rankings for good terms."]])
    else:
        overview.update('G27', [['']])
        print("⚠️ No keywords found in positions 4-20.")


# ── 9. PageSpeed Insights ─────────────────────────────────────────────────────

def pagespeed_data(creds):
    _, overview = get_sheets(creds)
    raw = overview.acell(CTR_CELL).value
    if not raw or not raw.strip():
        print(f"❌ No domain found in Overview!{CTR_CELL}. Select a GSC website first (run option 0).")
        return

    domain = raw.strip().replace("sc-domain:", "").replace("https://", "").replace("http://", "").strip("/")
    url    = f"https://{domain}"

    scores = {}
    for strategy in ("desktop", "mobile"):
        print(f"  Fetching {strategy} score (this may take ~30s)...", flush=True)
        params = {"url": url, "strategy": strategy, "category": "performance"}
        if PAGESPEED_API_KEY:
            params["key"] = PAGESPEED_API_KEY
        resp = requests.get("https://www.googleapis.com/pagespeedonline/v5/runPagespeed", params=params)
        if resp.status_code != 200:
            print(f"❌ PageSpeed API error ({strategy}): {resp.status_code} — {resp.text[:200]}")
            return
        score = resp.json().get("lighthouseResult", {}).get("categories", {}).get("performance", {}).get("score")
        scores[strategy] = round(score * 100) if score is not None else None

    desktop = scores.get("desktop")
    mobile  = scores.get("mobile")

    print(f"\n── PageSpeed Insights: {url} ──────────────────")
    print(f"  Desktop: {desktop}")
    print(f"  Mobile:  {mobile}")

    if mobile is not None:
        overview.update('B7', [[mobile]])
        if mobile >= 90:   msg = "Excellent page speed"
        elif mobile >= 50: msg = "Average page speed"
        else:              msg = "Poor page speed. Fix core web vitals."
        overview.update('G7', [[msg]])
    if desktop is not None:
        overview.update('C7', [[desktop]])

    print("✅ PageSpeed scores written → B7 (mobile) | C7 (desktop)")


# ── 10. Keyword Mapping ───────────────────────────────────────────────────────

# Words too generic to use as branded signals when doing partial matching
_GENERIC_RE_WORDS = {
    "the", "at", "of", "in", "and", "for", "by", "on",
    "apartments", "apartment", "luxury", "suite", "suites",
    "residence", "residences", "living", "homes", "home"
}

def keyword_mapping(creds):
    """
    Classify every keyword in 'Organic Keywords All & Keyword Mapping' and write the result to
    column F.  Branded rows are also highlighted green.

    Precedence:
      1. branded       – keyword contains the building name (fully or partially)
      2. primary       – keyword contains 'apartments' + city
      3. tracking only – keyword contains 'apartments' + a neighborhood
      4. secondary     – everything else
    """
    ss, overview = get_sheets(creds)
    sheets_svc   = build('sheets', 'v4', credentials=creds)

    # ── Read metadata from Overview ───────────────────────────────────────────
    building_name = (overview.acell('B53').value or "").strip()
    city          = (overview.acell('B49').value or "").strip().lower()
    neighborhoods = [n.strip().lower() for n in (overview.acell('B51').value or "").split(",") if n.strip()]
    luxury_mode   = (overview.acell('B55').value or "").strip().upper() == "YES"

    missing = []
    if not building_name:
        missing.append("Building name (Overview!B53)")
    if not city:
        missing.append("City (Overview!B49)")
    if not neighborhoods:
        missing.append("Neighborhoods (Overview!B51)")
    if missing:
        print(f"❌ Missing required fields: {', '.join(missing)}. Please fill them in first.")
        return

    # Significant tokens from the building name (skip tiny / generic words)
    bldg_tokens = [
        t for t in building_name.lower().split()
        if len(t) >= 4 and t not in _GENERIC_RE_WORDS
    ]
    bldg_full = building_name.lower()

    print(f"  Building : '{building_name}' | Match tokens: {bldg_tokens or [bldg_full]}")
    print(f"  City     : {city}")
    print(f"  Neighborhoods: {', '.join(neighborhoods)}")

    # ── Read raw data from SEMrush sheet ─────────────────────────────────────
    try:
        src_sheet = ss.worksheet("Organic Keywords All & Keyword Mapping")
    except Exception:
        print("❌ 'Organic Keywords All & Keyword Mapping' sheet not found. Run option 8 (SEMrush Data) first.")
        return

    all_data = src_sheet.get_all_values()
    if not all_data or len(all_data) < 2:
        print("❌ No keyword data found in the SEMrush sheet.")
        return

    # ── Classify each keyword ─────────────────────────────────────────────────
    headers      = (all_data[0] + [""] * 6)[:5]
    headers      = headers + ["Category"]
    output_rows  = [headers]
    branded_rows = []   # 1-based row indices in the new spreadsheet

    for i, row in enumerate(all_data[1:], start=1):
        kw = row[0].lower() if row else ""

        is_branded = (bldg_full in kw) or (bldg_tokens and any(t in kw for t in bldg_tokens))

        if is_branded:
            category = "branded"
        elif "apartments" in kw and city in kw:
            category = "primary"
            branded_rows.append(i)
        elif luxury_mode and "apartments" in kw and "luxury" in kw and city in kw:
            category = "primary"
            branded_rows.append(i)
        elif "apartments" in kw and any(n in kw for n in neighborhoods):
            category = "tracking only"
        else:
            category = "secondary"

        data_cols = (row + [""] * 5)[:5]
        output_rows.append(data_cols + [category])

    # ── Create a brand-new standalone spreadsheet ─────────────────────────────
    map_title    = f"Keyword Mapping {building_name}".strip()
    new_ss       = sheets_svc.spreadsheets().create(body={
        "properties": {"title": map_title},
        "sheets": [{"properties": {"title": map_title}}]
    }).execute()
    new_ss_id    = new_ss["spreadsheetId"]
    new_sheet_id = new_ss["sheets"][0]["properties"]["sheetId"]
    new_url      = f"https://docs.google.com/spreadsheets/d/{new_ss_id}"
    print(f"  Created new spreadsheet: {new_url}")

    # ── Write all rows ────────────────────────────────────────────────────────
    sheets_svc.spreadsheets().values().update(
        spreadsheetId=new_ss_id,
        range=f"A1:F{len(output_rows)}",
        valueInputOption="RAW",
        body={"values": output_rows}
    ).execute()

    # ── Apply row formatting ──────────────────────────────────────────────────
    GREEN = {"red": 0.714, "green": 0.843, "blue": 0.659}
    WHITE = {"red": 1.0,   "green": 1.0,   "blue": 1.0}
    num_cols = 6

    format_requests = [{
        "repeatCell": {
            "range": {
                "sheetId": new_sheet_id,
                "startRowIndex": 1, "endRowIndex": len(output_rows),
                "startColumnIndex": 0, "endColumnIndex": num_cols
            },
            "cell": {"userEnteredFormat": {"backgroundColor": WHITE}},
            "fields": "userEnteredFormat.backgroundColor"
        }
    }]

    for row_idx in branded_rows:
        format_requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": new_sheet_id,
                    "startRowIndex": row_idx, "endRowIndex": row_idx + 1,
                    "startColumnIndex": 0, "endColumnIndex": num_cols
                },
                "cell": {"userEnteredFormat": {"backgroundColor": GREEN}},
                "fields": "userEnteredFormat.backgroundColor"
            }
        })

    sheets_svc.spreadsheets().batchUpdate(
        spreadsheetId=new_ss_id,
        body={"requests": format_requests}
    ).execute()

    # ── Summary ───────────────────────────────────────────────────────────────
    counts = {}
    for row in output_rows[1:]:
        cat = row[5] if len(row) > 5 else ""
        counts[cat] = counts.get(cat, 0) + 1

    total = len(output_rows) - 1
    print(f"✅ Keyword mapping complete — {total} keywords in new spreadsheet '{map_title}':")
    print(f"   Branded:       {counts.get('branded', 0)}")
    print(f"   Primary:       {counts.get('primary', 0)}  (green highlight)")
    print(f"   Tracking only: {counts.get('tracking only', 0)}")
    print(f"   Secondary:     {counts.get('secondary', 0)}")
    print(f"   🔗 {new_url}")


# ── 11. Export to Doc ─────────────────────────────────────────────────────────

def export_findings_to_doc(creds):
    _, overview = get_sheets(creds)
    findings    = overview.get('G3:G38')
    cleaned     = [row[0] for row in findings if row and row[0].strip()]
    if not cleaned:
        print("❌ No findings found in column G to export.")
        return

    docs    = build('docs', 'v1', credentials=creds)
    doc     = docs.documents().get(documentId=DOC_ID).execute()
    content = doc.get('body', {}).get('content', [])

    findings_index = None
    for elem in content:
        para = elem.get('paragraph')
        if para:
            for pe in para.get('elements', []):
                if 'Findings' in pe.get('textRun', {}).get('content', ''):
                    findings_index = elem.get('endIndex', 1) - 1
                    break

    if findings_index is None:
        print("❌ Could not find 'Findings' heading in the document.")
        return

    requests = []
    for item in reversed(cleaned):
        text    = f'\n{item}'
        end_idx = findings_index + len(text)
        requests.append({'insertText': {'location': {'index': findings_index}, 'text': text}})
        requests.append({
            'updateTextStyle': {
                'range': {'startIndex': findings_index + 1, 'endIndex': end_idx},
                'textStyle': {'fontSize': {'magnitude': 11, 'unit': 'PT'},
                              'weightedFontFamily': {'fontFamily': 'Host Grotesk'}, 'bold': False},
                'fields': 'fontSize,weightedFontFamily,bold'
            }
        })
        requests.append({
            'createParagraphBullets': {
                'range': {'startIndex': findings_index + 1, 'endIndex': end_idx},
                'bulletPreset': 'BULLET_DISC_CIRCLE_SQUARE'
            }
        })

    docs.documents().batchUpdate(documentId=DOC_ID, body={'requests': requests}).execute()
    print("✅ Findings exported to SEO Brief doc!")


# ── 11. Run Full Audit ────────────────────────────────────────────────────────

def run_full_audit(creds):
    """Run all audit steps in the correct order."""
    steps = [
        ("3",  "Domain Age",         domain_age),
        ("4",  "CTR from GSC",       ctr_percentage),
        ("9",  "PageSpeed Insights", pagespeed_data),
        ("8",  "SEMrush Data",       semrush_data),
        ("10", "Keyword Mapping",    keyword_mapping),
        ("5",  "GA4 Report",         ga4_report),
        ("7",  "Ahrefs Data",        ahrefs_data),
        ("1",  "Auto-Analysis",      run_auto_analysis),
        ("6",  "Export to SEO Brief",export_findings_to_doc),
    ]
    total = len(steps)
    for i, (num, label, fn) in enumerate(steps, 1):
        print(f"\n[{i}/{total}] ── {label} (option {num}) ──────────────────────")
        try:
            fn(creds)
        except Exception as e:
            print(f"❌ {label} failed: {e} — continuing...")
    print("\n✅ Full audit complete.")


# ── 12. Clean All Data ────────────────────────────────────────────────────────

def clean_all_data(creds):
    """Clear all generated data from Overview, keyword sheet, and SEO Brief doc."""
    ss, overview = get_sheets(creds)

    # ── Overview: clear every cell written by any function ───────────────────
    overview.batch_clear([
        'B3',  'G3',                              # Domain Age
        'B4',  'G4',                              # CTR
        'B7',  'C7',  'G7',                      # PageSpeed
        'G9',                                     # Backlink Quality commentary
        'B11', 'C11', 'G11',                     # DR / UR / commentary
        'B12',                                    # Referring domains
        'G13',                                    # Site Audit commentary
        'B15:B19', 'C15:C19', 'D15', 'G15',     # Anchors
        'B22', 'B23', 'B24',                     # Keyword position counts
        'B45', 'B47', 'B49', 'B51', 'B53',  # Property/config fields
        'B27:B31', 'C27:C31', 'D27:D31', 'G27', # Top keywords
        'B33', 'B34', 'B35', 'B36', 'G34',      # GA4 Traffic
        'B38:B42', 'C38:C42', 'D38:D42', 'G38', # Landing Pages
    ])
    # Reset dropdown selections to "None" without removing the dropdown itself
    overview.update('B55', [['None']])
    overview.update('B57', [['None']])
    print("✅ Overview data cleared.")

    # ── Organic Keywords sheet ────────────────────────────────────────────────
    try:
        kw_sheet  = ss.worksheet("Organic Keywords All & Keyword Mapping")
        sheet_id  = kw_sheet._properties['sheetId']
        row_count = kw_sheet.row_count
        col_count = kw_sheet.col_count
        sheets_svc = build('sheets', 'v4', credentials=creds)
        sheets_svc.spreadsheets().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body={'requests': [{
                'repeatCell': {
                    'range': {
                        'sheetId': sheet_id,
                        'startRowIndex': 0, 'endRowIndex': row_count,
                        'startColumnIndex': 0, 'endColumnIndex': col_count
                    },
                    'cell': {'userEnteredFormat': {'backgroundColor': {'red': 1, 'green': 1, 'blue': 1}}},
                    'fields': 'userEnteredFormat.backgroundColor'
                }
            }]}
        ).execute()
        kw_sheet.clear()
        print("✅ Organic Keywords sheet cleared.")
    except Exception:
        pass  # sheet doesn't exist yet — nothing to clear

    # ── SEO Brief doc: delete all bullet points below the Findings heading ──────
    docs    = build('docs', 'v1', credentials=creds)
    doc     = docs.documents().get(documentId=DOC_ID).execute()
    content = doc.get('body', {}).get('content', [])

    # Step 1: find position of the Findings paragraph in the content list
    findings_pos = None
    for i, elem in enumerate(content):
        para = elem.get('paragraph')
        if not para:
            continue
        for pe in para.get('elements', []):
            if 'Findings' in pe.get('textRun', {}).get('content', ''):
                findings_pos = i
                break
        if findings_pos is not None:
            break

    if findings_pos is None:
        print("⚠️ 'Findings' heading not found in doc — skipping doc cleanup.")
    else:
        # Step 2: collect every paragraph after Findings until the next heading
        to_delete = []
        for elem in content[findings_pos + 1:]:
            para = elem.get('paragraph')
            if not para:
                continue
            style = para.get('paragraphStyle', {}).get('namedStyleType', '')
            if style.startswith('HEADING'):
                break
            to_delete.append(elem)

        if to_delete:
            # Step 3: delete bottom-to-top so earlier indices stay valid
            delete_requests = []
            for elem in reversed(to_delete):
                delete_requests.append({'deleteContentRange': {
                    'range': {
                        'startIndex': elem.get('startIndex'),
                        'endIndex':   elem.get('endIndex')
                    }
                }})
            docs.documents().batchUpdate(
                documentId=DOC_ID,
                body={'requests': delete_requests}
            ).execute()
            print(f"✅ SEO Brief findings cleared ({len(to_delete)} items removed).")
        else:
            print("  No findings content in doc to clear.")

    print("✅ All data cleared. Ready to start over.")


# ── Menu ──────────────────────────────────────────────────────────────────────

def menu():
    print("""
╔══════════════════════════════════════╗
║         SEO AUDIT ACTIONS           ║
╠══════════════════════════════════════╣
║  0.  Sync All Properties            ║
║      (GSC → B45 | GA4 → B47)       ║
╠══════════════════════════════════════╣
║  11. ★ Run Full Audit               ║
║      (all steps in order)           ║
║  12. ✖ Clean All Data               ║
║      (reset sheet + doc)            ║
╠══════════════════════════════════════╣
║  Individual steps                   ║
║  1.  Run All Auto-Analysis          ║
║  3.  Domain Age (B3)                ║
║  4.  Sync CTR from GSC (B4)         ║
║  5.  Run GA4 Report                 ║
║      (Traffic B33:B36 +             ║
║       Landing Pages B38:D42)        ║
║  6.  Export Findings to SEO Brief   ║
║  7.  Ahrefs Data                    ║
║  8.  SEMrush Data                   ║
║  9.  PageSpeed Insights             ║
║      (Mobile → B7 | Desktop → C7)  ║
║  10. Keyword Mapping                ║
║      (col F)                        ║
║  99. Exit                           ║
╚══════════════════════════════════════╝
    """)

actions = {
    '0':  sync_all_properties,
    '1':  run_auto_analysis,
    '3':  domain_age,
    '11': run_full_audit,
    '12': clean_all_data,
    '4':  ctr_percentage,
    '5':  ga4_report,
    '6':  export_findings_to_doc,
    '7':  ahrefs_data,
    '8':  semrush_data,
    '9':  pagespeed_data,
    '10': keyword_mapping,
}

# ── Gradio UI ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import io
    import contextlib
    import gradio as gr

    ACTION_CHOICES = [
        ("⭐ Run Full Audit",    "11"),
        ("Sync All Properties", "0"),
        ("✖ Clean All Data",    "12"),
        ("Keyword Mapping",     "10"),
    ]

    try:
        creds = authenticate()
    except Exception as e:
        creds = None
        print(f"⚠️ Auth failed: {e}")

    def run_action(action_key):
        if creds is None:
            return "❌ Authentication failed. Check that GOOGLE_TOKEN_JSON and GOOGLE_CREDENTIALS_JSON secrets are set in Space settings."
        fn = actions.get(action_key)
        if not fn:
            return "❌ Unknown action."
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                fn(creds)
            except Exception as e:
                print(f"❌ Error: {e}")
        return buf.getvalue() or "✅ Done (no output)"

    with gr.Blocks(title="SEO Audit") as demo:
        gr.Markdown("# 🔍 SEO Audit")
        action = gr.Dropdown(
            choices=ACTION_CHOICES,
            value="11",
            label="Select action",
        )
        run_btn = gr.Button("▶ Run", variant="primary")
        output  = gr.Textbox(label="Output", lines=20, interactive=False)
        run_btn.click(fn=run_action, inputs=action, outputs=output)

    demo.launch(server_name="0.0.0.0")