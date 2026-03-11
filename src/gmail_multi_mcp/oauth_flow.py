"""OAuth flow utilities for in-tool authentication (without local server)."""

import json
import logging
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.settings.basic",
]


def get_oauth_url(oauth_keys_path: Path) -> tuple[InstalledAppFlow, str]:
    """
    Generate an OAuth consent URL without requiring a local server.

    Returns:
        Tuple of (flow object, authorization_url)
    """
    if not oauth_keys_path.exists():
        raise FileNotFoundError(f"GCP OAuth keys not found at {oauth_keys_path}")

    flow = InstalledAppFlow.from_client_secrets_file(str(oauth_keys_path), SCOPES)
    flow.redirect_uri = "http://localhost"
    authorization_url, state = flow.authorization_url(
        include_granted_scopes='true'
    )
    return flow, authorization_url


def exchange_code_for_credentials(flow: InstalledAppFlow, auth_code: str) -> dict:
    """
    Exchange authorization code for credentials.

    Args:
        flow: InstalledAppFlow object from get_oauth_url
        auth_code: Authorization code returned from OAuth consent screen

    Returns:
        Dictionary with access_token, refresh_token, and scope
    """
    try:
        # Handle if user pasted full redirect URL instead of just the code
        if auth_code.startswith("http"):
            parsed = urlparse(auth_code)
            code_params = parse_qs(parsed.query).get("code", [])
            if code_params:
                auth_code = code_params[0]
            else:
                raise ValueError("Could not extract 'code' parameter from URL")
        creds = flow.fetch_token(code=auth_code)

        creds_data = {
            "access_token": creds.get("access_token"),
            "refresh_token": creds.get("refresh_token"),
            "scope": " ".join(SCOPES),
            "token_type": "Bearer",
        }
        return creds_data
    except Exception as e:
        raise ValueError(f"Failed to exchange authorization code: {str(e)}")


def verify_and_get_email(credentials: dict, oauth_keys_path: Path) -> str:
    """
    Verify credentials by fetching Gmail profile and return email address.

    Args:
        credentials: Credentials dictionary from exchange_code_for_credentials
        oauth_keys_path: Path to GCP OAuth keys (for client_id/secret)

    Returns:
        Email address associated with the account
    """
    try:
        oauth_keys = json.loads(oauth_keys_path.read_text())
        installed = oauth_keys["installed"]

        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        creds = Credentials(
            token=credentials.get("access_token"),
            refresh_token=credentials.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=installed["client_id"],
            client_secret=installed["client_secret"],
            scopes=SCOPES,
        )

        service = build("gmail", "v1", credentials=creds)
        profile = service.users().getProfile(userId="me").execute()
        return profile.get("emailAddress", "unknown")
    except Exception as e:
        raise ValueError(f"Failed to verify credentials: {str(e)}")
