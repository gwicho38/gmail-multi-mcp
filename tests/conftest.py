"""Shared fixtures for gmail-multi-mcp tests."""

import json
import pytest
from pathlib import Path


@pytest.fixture
def tmp_config_dir(tmp_path):
    """Create a temporary ~/.gmail-mcp structure."""
    accounts_dir = tmp_path / "accounts"
    accounts_dir.mkdir()

    # Fake GCP OAuth keys
    oauth_keys = {
        "installed": {
            "client_id": "test-client-id.apps.googleusercontent.com",
            "project_id": "test-project",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_secret": "test-secret",
            "redirect_uris": ["http://localhost"],
        }
    }
    (tmp_path / "gcp-oauth.keys.json").write_text(json.dumps(oauth_keys))

    # Fake account credentials
    for name in ["work", "personal"]:
        creds = {
            "access_token": f"ya29.fake-{name}",
            "refresh_token": f"1//fake-refresh-{name}",
            "scope": "https://www.googleapis.com/auth/gmail.modify https://www.googleapis.com/auth/gmail.settings.basic",
            "token_type": "Bearer",
            "expiry_date": 9999999999999,
        }
        (accounts_dir / f"{name}.json").write_text(json.dumps(creds))

    # Config registry
    config = {
        "accounts": {
            "work": "work@example.com",
            "personal": "personal@gmail.com",
        },
        "default": "work",
    }
    (tmp_path / "config.json").write_text(json.dumps(config))

    return tmp_path


@pytest.fixture
def mock_gmail_service():
    """Return a mocked Gmail API service."""
    from unittest.mock import MagicMock
    service = MagicMock()
    service.users.return_value = service
    return service
