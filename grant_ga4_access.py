from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import os

# ── Config ────────────────────────────────────────────────────────────────────

SCOPES = [
    'https://www.googleapis.com/auth/analytics.manage.users',
    'https://www.googleapis.com/auth/analytics.readonly'
]

GRANT_TO_EMAIL = 'ppc@premieronlinemarketing.com'

ACCOUNTS_TO_PROCESS = [
    {'email': 'ppc1@premieronlinemarketing.com', 'token': 'token_ppc1.json'},
    {'email': 'ppc3@premieronlinemarketing.com', 'token': 'token_ppc3.json'},
    {'email': 'ppc4@premieronlinemarketing.com', 'token': 'token_ppc4.json'},
]


# ── Auth ──────────────────────────────────────────────────────────────────────

def authenticate(token_file, email):
    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            print(f"\n🔐 Please log in with: {email}")
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES
            )
            creds = flow.run_local_server(port=0, prompt='select_account')
        with open(token_file, 'w') as f:
            f.write(creds.to_json())
    return creds


# ── Grant access ──────────────────────────────────────────────────────────────

def grant_access_for_account(creds, email):
    admin = build('analyticsadmin', 'v1alpha', credentials=creds)

    # List all GA4 accounts accessible by this login
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

    if not accounts:
        print(f"  ⚠️  No GA4 accounts found for {email}")
        return 0

    print(f"  Found {len(accounts)} GA4 accounts under {email}")

    granted = 0
    skipped = 0
    errors  = 0

    for account in accounts:
        account_name = account['name']  # e.g. "accounts/123456789"
        display_name = account.get('displayName', account_name)

        try:
            # Check if ppc@ already has access
            existing = admin.accounts().accessBindings().list(
                parent=account_name
            ).execute().get('accessBindings', [])

            already_has_access = any(
                binding.get('user') == GRANT_TO_EMAIL
                for binding in existing
            )

            if already_has_access:
                skipped += 1
                continue

            # Grant viewer access
            admin.accounts().accessBindings().create(
                parent=account_name,
                body={
                    'user': GRANT_TO_EMAIL,
                    'roles': ['predefinedRoles/viewer']
                }
            ).execute()

            print(f"  ✅ Granted access to: {display_name}")
            granted += 1

        except Exception as e:
            print(f"  ❌ Failed for {display_name}: {e}")
            errors += 1

    print(f"\n  Summary for {email}:")
    print(f"  ✅ Granted: {granted} | ⏭️  Already had access: {skipped} | ❌ Errors: {errors}")
    return granted


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 50)
    print("  GA4 Access Grant Setup")
    print(f"  Granting viewer access to: {GRANT_TO_EMAIL}")
    print("=" * 50)

    total_granted = 0

    for account in ACCOUNTS_TO_PROCESS:
        print(f"\n📧 Processing: {account['email']}")
        creds         = authenticate(account['token'], account['email'])
        total_granted += grant_access_for_account(creds, account['email'])

    print("\n" + "=" * 50)
    print(f"✅ Done! Total accounts granted: {total_granted}")
    print(f"   {GRANT_TO_EMAIL} now has viewer access across all GA4 accounts.")
    print("   You can now run the main script with option 0 to sync properties.")
    print("=" * 50)


if __name__ == '__main__':
    main()