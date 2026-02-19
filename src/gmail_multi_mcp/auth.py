"""OAuth authentication CLI for adding new Gmail accounts."""

import argparse
import json
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.settings.basic",
]

CONFIG_DIR = Path.home() / ".gmail-mcp"


def run_auth(argv: list[str]):
    parser = argparse.ArgumentParser(description="Authenticate a Gmail account")
    parser.add_argument("--name", required=True, help="Label for this account (e.g., 'work', 'personal')")
    parser.add_argument("--port", type=int, default=3000, help="Local server port for OAuth callback")
    args = parser.parse_args(argv)

    oauth_keys = CONFIG_DIR / "gcp-oauth.keys.json"
    if not oauth_keys.exists():
        print(f"Error: GCP OAuth keys not found at {oauth_keys}", file=sys.stderr)
        print("Place your OAuth client JSON at ~/.gmail-mcp/gcp-oauth.keys.json", file=sys.stderr)
        sys.exit(1)

    accounts_dir = CONFIG_DIR / "accounts"
    accounts_dir.mkdir(parents=True, exist_ok=True)

    print(f"Authenticating account: {args.name}")
    print("A browser window will open. Sign in with the Gmail account you want to add.")

    flow = InstalledAppFlow.from_client_secrets_file(str(oauth_keys), SCOPES)
    creds = flow.run_local_server(port=args.port)

    # Save credentials
    creds_data = {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "scope": " ".join(SCOPES),
        "token_type": "Bearer",
    }
    creds_path = accounts_dir / f"{args.name}.json"
    creds_path.write_text(json.dumps(creds_data, indent=2))
    print(f"Credentials saved to: {creds_path}")

    # Get the authenticated email address
    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId="me").execute()
    email = profile.get("emailAddress", "unknown")

    # Update config.json
    config_path = CONFIG_DIR / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
    else:
        config = {"accounts": {}}

    config["accounts"][args.name] = email
    if "default" not in config:
        config["default"] = args.name
    config_path.write_text(json.dumps(config, indent=2))

    print(f"Account '{args.name}' ({email}) added successfully!")


def main():
    run_auth(sys.argv[1:])
