"""Tests for account manager."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from gmail_multi_mcp.accounts import AccountManager, AccountNotFoundError, Account


class TestAccountManagerInit:
    def test_loads_accounts_from_config(self, tmp_config_dir):
        mgr = AccountManager(tmp_config_dir)
        assert set(mgr.account_names) == {"work", "personal"}

    def test_sets_default_account(self, tmp_config_dir):
        mgr = AccountManager(tmp_config_dir)
        assert mgr.active_account == "work"

    def test_sets_first_account_when_no_default(self, tmp_config_dir):
        config = json.loads((tmp_config_dir / "config.json").read_text())
        del config["default"]
        (tmp_config_dir / "config.json").write_text(json.dumps(config))
        mgr = AccountManager(tmp_config_dir)
        assert mgr.active_account in {"work", "personal"}

    def test_raises_on_missing_config(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            AccountManager(tmp_path)

    def test_account_email_mapping(self, tmp_config_dir):
        mgr = AccountManager(tmp_config_dir)
        assert mgr.get_email("work") == "work@example.com"
        assert mgr.get_email("personal") == "personal@gmail.com"


class TestAccountManagerSwitch:
    def test_switch_account(self, tmp_config_dir):
        mgr = AccountManager(tmp_config_dir)
        mgr.switch("personal")
        assert mgr.active_account == "personal"

    def test_switch_to_unknown_account_raises(self, tmp_config_dir):
        mgr = AccountManager(tmp_config_dir)
        with pytest.raises(AccountNotFoundError):
            mgr.switch("nonexistent")


class TestAccountManagerResolve:
    def test_resolve_returns_explicit_account(self, tmp_config_dir):
        mgr = AccountManager(tmp_config_dir)
        assert mgr.resolve("personal") == "personal"

    def test_resolve_returns_active_when_none(self, tmp_config_dir):
        mgr = AccountManager(tmp_config_dir)
        assert mgr.resolve(None) == "work"

    def test_resolve_raises_on_unknown(self, tmp_config_dir):
        mgr = AccountManager(tmp_config_dir)
        with pytest.raises(AccountNotFoundError):
            mgr.resolve("nonexistent")

    def test_resolve_raises_when_no_accounts_configured(self, tmp_config_dir):
        mgr = AccountManager(tmp_config_dir)
        mgr._accounts.clear()
        mgr._active = None
        with pytest.raises(AccountNotFoundError, match="No accounts configured"):
            mgr.resolve(None)


class TestAccountManagerService:
    @patch("gmail_multi_mcp.accounts.build")
    @patch("gmail_multi_mcp.accounts.Credentials")
    def test_get_service_builds_gmail_service(self, mock_creds_cls, mock_build, tmp_config_dir):
        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_creds_cls.return_value = mock_creds
        mock_build.return_value = MagicMock()

        mgr = AccountManager(tmp_config_dir)
        service = mgr.get_service("work")

        mock_build.assert_called_once_with("gmail", "v1", credentials=mock_creds)
        assert service is not None

    @patch("gmail_multi_mcp.accounts.build")
    @patch("gmail_multi_mcp.accounts.Credentials")
    def test_get_service_caches_service(self, mock_creds_cls, mock_build, tmp_config_dir):
        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_creds_cls.return_value = mock_creds
        mock_build.return_value = MagicMock()

        mgr = AccountManager(tmp_config_dir)
        s1 = mgr.get_service("work")
        s2 = mgr.get_service("work")
        assert s1 is s2
        assert mock_build.call_count == 1

    @patch("gmail_multi_mcp.accounts.build")
    @patch("gmail_multi_mcp.accounts.Credentials")
    def test_get_service_refreshes_expired_token(self, mock_creds_cls, mock_build, tmp_config_dir):
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "fake-refresh"
        mock_creds.token = "ya29.refreshed-token"
        mock_creds_cls.return_value = mock_creds

        mgr = AccountManager(tmp_config_dir)
        mgr.get_service("work")

        mock_creds.refresh.assert_called_once()

        # Issue 5: verify the refreshed token is persisted to disk
        creds_data = json.loads((tmp_config_dir / "accounts" / "work.json").read_text())
        assert creds_data["access_token"] == "ya29.refreshed-token"

    @patch("gmail_multi_mcp.accounts.build")
    @patch("gmail_multi_mcp.accounts.Credentials")
    def test_get_service_raises_when_invalid_and_no_refresh_token(
        self, mock_creds_cls, mock_build, tmp_config_dir
    ):
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = False
        mock_creds.refresh_token = None
        mock_creds_cls.return_value = mock_creds

        mgr = AccountManager(tmp_config_dir)
        with pytest.raises(ValueError, match="invalid and cannot be refreshed"):
            mgr.get_service("work")


class TestAccountManagerAddAccount:
    def test_add_account_appears_in_account_names(self, tmp_config_dir):
        mgr = AccountManager(tmp_config_dir)
        mgr.add_account("new", "new@example.com", {"access_token": "tok", "refresh_token": "ref"})
        assert "new" in mgr.account_names

    def test_add_account_writes_credentials_file(self, tmp_config_dir):
        mgr = AccountManager(tmp_config_dir)
        creds = {"access_token": "tok", "refresh_token": "ref"}
        mgr.add_account("new", "new@example.com", creds)
        creds_path = tmp_config_dir / "accounts" / "new.json"
        assert creds_path.exists()
        assert json.loads(creds_path.read_text()) == creds

    def test_add_account_updates_config_json(self, tmp_config_dir):
        mgr = AccountManager(tmp_config_dir)
        mgr.add_account("new", "new@example.com", {"access_token": "tok", "refresh_token": "ref"})
        config = json.loads((tmp_config_dir / "config.json").read_text())
        assert config["accounts"]["new"] == "new@example.com"

    @patch("gmail_multi_mcp.accounts.build")
    @patch("gmail_multi_mcp.accounts.Credentials")
    def test_add_account_invalidates_service_cache(self, mock_creds_cls, mock_build, tmp_config_dir):
        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_creds_cls.return_value = mock_creds
        mock_build.return_value = MagicMock()

        mgr = AccountManager(tmp_config_dir)
        # Prime the cache for "work"
        s1 = mgr.get_service("work")
        assert mock_build.call_count == 1

        # Re-adding "work" should evict the cached service
        mgr.add_account("work", "work@example.com", {"access_token": "new-tok", "refresh_token": "ref"})
        assert "work" not in mgr._services

        # Next call must rebuild the service (build called a second time)
        mgr.get_service("work")
        assert mock_build.call_count == 2
