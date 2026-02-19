"""Tests for auth CLI command."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from gmail_multi_mcp.auth import run_auth


class TestAuth:
    def test_auth_requires_name(self):
        with pytest.raises(SystemExit):
            run_auth([])

    @patch("gmail_multi_mcp.auth.build")
    @patch("gmail_multi_mcp.auth.InstalledAppFlow")
    def test_auth_saves_credentials(self, mock_flow_cls, mock_build, tmp_path):
        # Mock OAuth flow
        mock_flow = MagicMock()
        mock_creds = MagicMock()
        mock_creds.token = "ya29.new-token"
        mock_creds.refresh_token = "1//new-refresh"
        mock_flow.run_local_server.return_value = mock_creds
        mock_flow_cls.from_client_secrets_file.return_value = mock_flow

        # Mock Gmail API for profile fetch
        mock_service = MagicMock()
        mock_service.users().getProfile().execute.return_value = {"emailAddress": "test@gmail.com"}
        mock_build.return_value = mock_service

        # Set up tmp dir structure
        (tmp_path / "gcp-oauth.keys.json").write_text(json.dumps({
            "installed": {"client_id": "test", "client_secret": "test",
                          "auth_uri": "https://a", "token_uri": "https://t",
                          "redirect_uris": ["http://localhost"]}
        }))
        (tmp_path / "accounts").mkdir()
        (tmp_path / "config.json").write_text(json.dumps({"accounts": {}}))

        with patch("gmail_multi_mcp.auth.CONFIG_DIR", tmp_path):
            run_auth(["--name", "newacct"])

        # Verify credentials saved
        assert (tmp_path / "accounts" / "newacct.json").exists()
        creds = json.loads((tmp_path / "accounts" / "newacct.json").read_text())
        assert creds["access_token"] == "ya29.new-token"
        assert creds["refresh_token"] == "1//new-refresh"

        # Verify config updated
        config = json.loads((tmp_path / "config.json").read_text())
        assert "newacct" in config["accounts"]
        assert config["accounts"]["newacct"] == "test@gmail.com"

    @patch("gmail_multi_mcp.auth.build")
    @patch("gmail_multi_mcp.auth.InstalledAppFlow")
    def test_auth_sets_default_when_none(self, mock_flow_cls, mock_build, tmp_path):
        mock_flow = MagicMock()
        mock_creds = MagicMock()
        mock_creds.token = "token"
        mock_creds.refresh_token = "refresh"
        mock_flow.run_local_server.return_value = mock_creds
        mock_flow_cls.from_client_secrets_file.return_value = mock_flow

        mock_service = MagicMock()
        mock_service.users().getProfile().execute.return_value = {"emailAddress": "test@gmail.com"}
        mock_build.return_value = mock_service

        (tmp_path / "gcp-oauth.keys.json").write_text(json.dumps({
            "installed": {"client_id": "t", "client_secret": "t",
                          "auth_uri": "https://a", "token_uri": "https://t",
                          "redirect_uris": ["http://localhost"]}
        }))
        (tmp_path / "accounts").mkdir()
        # No config.json exists yet

        with patch("gmail_multi_mcp.auth.CONFIG_DIR", tmp_path):
            run_auth(["--name", "first"])

        config = json.loads((tmp_path / "config.json").read_text())
        assert config["default"] == "first"
