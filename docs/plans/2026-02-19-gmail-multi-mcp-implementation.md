# gmail-multi-mcp Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Python MCP server that manages multiple Gmail accounts with JIT switching and full Gmail API feature parity.

**Architecture:** Python FastMCP server with three modules — `accounts.py` (credential/account management), `gmail_client.py` (Gmail API wrapper), `server.py` (MCP tools). Accounts stored in `~/.gmail-mcp/accounts/` with a `config.json` registry. Every Gmail tool accepts an optional `account` param.

**Tech Stack:** Python 3.11+, FastMCP (mcp[cli]), google-api-python-client, google-auth-oauthlib, pydantic, pytest

---

## Task 1: Project Scaffolding

**Files:**
- Create: `~/repos/gmail-multi-mcp/pyproject.toml`
- Create: `~/repos/gmail-multi-mcp/src/gmail_multi_mcp/__init__.py`
- Create: `~/repos/gmail-multi-mcp/src/gmail_multi_mcp/accounts.py` (empty placeholder)
- Create: `~/repos/gmail-multi-mcp/src/gmail_multi_mcp/gmail_client.py` (empty placeholder)
- Create: `~/repos/gmail-multi-mcp/src/gmail_multi_mcp/server.py` (empty placeholder)
- Create: `~/repos/gmail-multi-mcp/.gitignore`
- Create: `~/repos/gmail-multi-mcp/tests/__init__.py`
- Create: `~/repos/gmail-multi-mcp/tests/conftest.py`

**Step 1: Initialize git repo**

```bash
cd ~/repos/gmail-multi-mcp
git init
```

**Step 2: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "gmail-multi-mcp"
version = "0.1.0"
description = "Multi-account Gmail MCP server with JIT account switching for Claude Code."
requires-python = ">=3.11"
dependencies = [
    "mcp[cli]>=1.0.0",
    "google-api-python-client>=2.100.0",
    "google-auth-oauthlib>=1.2.0",
    "google-auth>=2.25.0",
    "pydantic>=2.0.0",
]

[project.scripts]
gmail-multi-mcp = "gmail_multi_mcp.server:main"

[project.optional-dependencies]
dev = ["pytest>=8.0.0", "pytest-asyncio>=0.23.0"]

[tool.hatch.build.targets.wheel]
packages = ["src/gmail_multi_mcp"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

**Step 3: Create .gitignore**

```
__pycache__/
*.pyc
.venv/
dist/
*.egg-info/
.pytest_cache/
```

**Step 4: Create __init__.py**

```python
"""Multi-account Gmail MCP server with JIT account switching."""

__version__ = "0.1.0"
```

**Step 5: Create empty module placeholders**

`src/gmail_multi_mcp/accounts.py`:
```python
"""Account manager for multi-Gmail credential handling."""
```

`src/gmail_multi_mcp/gmail_client.py`:
```python
"""Gmail API wrapper functions."""
```

`src/gmail_multi_mcp/server.py`:
```python
"""FastMCP server with Gmail tools."""


def main():
    pass
```

**Step 6: Create test scaffolding**

`tests/__init__.py`: empty file

`tests/conftest.py`:
```python
"""Shared fixtures for gmail-multi-mcp tests."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


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
    service = MagicMock()
    service.users.return_value = service
    return service
```

**Step 7: Create venv and install deps**

```bash
cd ~/repos/gmail-multi-mcp
uv venv
uv pip install -e ".[dev]"
```

**Step 8: Run pytest to verify scaffolding**

```bash
cd ~/repos/gmail-multi-mcp
uv run pytest --co -q
```

Expected: `no tests ran` (collection succeeds, no tests yet)

**Step 9: Commit**

```bash
cd ~/repos/gmail-multi-mcp
git add -A
git commit -m "feat: project scaffolding for gmail-multi-mcp"
```

---

## Task 2: Account Manager

**Files:**
- Create: `~/repos/gmail-multi-mcp/src/gmail_multi_mcp/accounts.py`
- Create: `~/repos/gmail-multi-mcp/tests/test_accounts.py`

**Step 1: Write failing tests for AccountManager**

`tests/test_accounts.py`:
```python
"""Tests for account manager."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from gmail_multi_mcp.accounts import AccountManager, AccountNotFoundError


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
        mock_creds_cls.return_value = mock_creds

        mgr = AccountManager(tmp_config_dir)
        mgr.get_service("work")

        mock_creds.refresh.assert_called_once()
```

**Step 2: Run tests to verify they fail**

```bash
cd ~/repos/gmail-multi-mcp
uv run pytest tests/test_accounts.py -v
```

Expected: FAIL — `ImportError: cannot import name 'AccountManager'`

**Step 3: Implement AccountManager**

`src/gmail_multi_mcp/accounts.py`:
```python
"""Account manager for multi-Gmail credential handling."""

import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.settings.basic",
]


class AccountNotFoundError(Exception):
    """Raised when a requested account does not exist."""


@dataclass
class Account:
    name: str
    email: str
    credentials_path: Path


class AccountManager:
    """Manages multiple Gmail accounts and their API service objects."""

    def __init__(self, config_dir: Path):
        self._config_dir = Path(config_dir)
        self._accounts: dict[str, Account] = {}
        self._services: dict[str, object] = {}
        self._active: str | None = None
        self._oauth_keys_path = self._config_dir / "gcp-oauth.keys.json"
        self._load_config()

    def _load_config(self):
        config_path = self._config_dir / "config.json"
        if not config_path.exists():
            raise FileNotFoundError(f"Config not found: {config_path}")

        config = json.loads(config_path.read_text())
        accounts_dir = self._config_dir / "accounts"

        for name, email in config.get("accounts", {}).items():
            creds_path = accounts_dir / f"{name}.json"
            self._accounts[name] = Account(
                name=name, email=email, credentials_path=creds_path
            )

        default = config.get("default")
        if default and default in self._accounts:
            self._active = default
        elif self._accounts:
            self._active = next(iter(self._accounts))

    @property
    def active_account(self) -> str | None:
        return self._active

    @property
    def account_names(self) -> list[str]:
        return list(self._accounts.keys())

    def get_email(self, name: str) -> str:
        if name not in self._accounts:
            raise AccountNotFoundError(f"Account not found: {name}")
        return self._accounts[name].email

    def switch(self, name: str):
        if name not in self._accounts:
            raise AccountNotFoundError(
                f"Account '{name}' not found. Available: {', '.join(self._accounts)}"
            )
        self._active = name
        logger.info("Switched active account to: %s", name)

    def resolve(self, account: str | None) -> str:
        name = account or self._active
        if name not in self._accounts:
            raise AccountNotFoundError(
                f"Account '{name}' not found. Available: {', '.join(self._accounts)}"
            )
        return name

    def get_service(self, account: str | None = None):
        name = self.resolve(account)
        if name in self._services:
            return self._services[name]

        acct = self._accounts[name]
        creds_data = json.loads(acct.credentials_path.read_text())

        creds = Credentials(
            token=creds_data.get("access_token"),
            refresh_token=creds_data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self._get_client_id(),
            client_secret=self._get_client_secret(),
            scopes=SCOPES,
        )

        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                # Persist refreshed token
                creds_data["access_token"] = creds.token
                acct.credentials_path.write_text(json.dumps(creds_data))
                logger.info("Refreshed token for account: %s", name)

        service = build("gmail", "v1", credentials=creds)
        self._services[name] = service
        return service

    def _get_client_id(self) -> str:
        keys = json.loads(self._oauth_keys_path.read_text())
        return keys["installed"]["client_id"]

    def _get_client_secret(self) -> str:
        keys = json.loads(self._oauth_keys_path.read_text())
        return keys["installed"]["client_secret"]

    def list_accounts_info(self) -> list[dict]:
        return [
            {
                "name": name,
                "email": acct.email,
                "active": name == self._active,
            }
            for name, acct in self._accounts.items()
        ]

    def add_account(self, name: str, email: str, credentials: dict):
        accounts_dir = self._config_dir / "accounts"
        accounts_dir.mkdir(exist_ok=True)
        creds_path = accounts_dir / f"{name}.json"
        creds_path.write_text(json.dumps(credentials))

        self._accounts[name] = Account(
            name=name, email=email, credentials_path=creds_path
        )

        # Update config.json
        config_path = self._config_dir / "config.json"
        config = json.loads(config_path.read_text()) if config_path.exists() else {"accounts": {}}
        config["accounts"][name] = email
        config_path.write_text(json.dumps(config, indent=2))

        logger.info("Added account: %s (%s)", name, email)
```

**Step 4: Run tests to verify they pass**

```bash
cd ~/repos/gmail-multi-mcp
uv run pytest tests/test_accounts.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
cd ~/repos/gmail-multi-mcp
git add src/gmail_multi_mcp/accounts.py tests/test_accounts.py
git commit -m "feat: account manager with load, switch, resolve, service building"
```

---

## Task 3: Gmail Client — Core Email Operations

**Files:**
- Create: `~/repos/gmail-multi-mcp/src/gmail_multi_mcp/gmail_client.py`
- Create: `~/repos/gmail-multi-mcp/tests/test_gmail_client.py`

**Step 1: Write failing tests for search, read, send, draft**

`tests/test_gmail_client.py`:
```python
"""Tests for Gmail API client wrapper."""

import json
import base64
import pytest
from unittest.mock import MagicMock, patch, call
from email.mime.text import MIMEText

from gmail_multi_mcp.gmail_client import (
    search_emails,
    read_email,
    send_email,
    draft_email,
    delete_email,
    batch_delete_emails,
    modify_email,
    batch_modify_emails,
    list_labels,
    create_label,
    update_label,
    delete_label,
    list_filters,
    get_filter,
    create_filter,
    delete_filter,
    download_attachment,
)


def _mock_service():
    """Build a deeply-mocked Gmail service."""
    svc = MagicMock()
    return svc


class TestSearch:
    def test_search_returns_messages(self):
        svc = _mock_service()
        svc.users().messages().list().execute.return_value = {
            "messages": [{"id": "msg1", "threadId": "t1"}],
            "resultSizeEstimate": 1,
        }
        svc.users().messages().get().execute.return_value = {
            "id": "msg1",
            "snippet": "Hello world",
            "payload": {"headers": [
                {"name": "From", "value": "alice@test.com"},
                {"name": "Subject", "value": "Test"},
                {"name": "Date", "value": "Mon, 1 Jan 2026 00:00:00 +0000"},
            ]},
            "labelIds": ["INBOX"],
        }
        result = search_emails(svc, "from:alice", max_results=5)
        assert len(result) == 1
        assert result[0]["id"] == "msg1"

    def test_search_empty_results(self):
        svc = _mock_service()
        svc.users().messages().list().execute.return_value = {
            "resultSizeEstimate": 0,
        }
        result = search_emails(svc, "nonexistent")
        assert result == []


class TestRead:
    def test_read_returns_message_detail(self):
        svc = _mock_service()
        svc.users().messages().get().execute.return_value = {
            "id": "msg1",
            "snippet": "Hello",
            "payload": {
                "headers": [
                    {"name": "From", "value": "bob@test.com"},
                    {"name": "Subject", "value": "Hi"},
                    {"name": "Date", "value": "Tue, 2 Jan 2026 12:00:00 +0000"},
                ],
                "body": {"data": base64.urlsafe_b64encode(b"Hello body").decode()},
                "mimeType": "text/plain",
            },
            "labelIds": ["INBOX"],
        }
        result = read_email(svc, "msg1")
        assert result["id"] == "msg1"
        assert "body" in result


class TestSend:
    def test_send_returns_message_id(self):
        svc = _mock_service()
        svc.users().messages().send().execute.return_value = {
            "id": "sent1",
            "threadId": "t1",
            "labelIds": ["SENT"],
        }
        result = send_email(svc, to=["alice@test.com"], subject="Hi", body="Hello")
        assert result["id"] == "sent1"


class TestDraft:
    def test_draft_returns_draft_id(self):
        svc = _mock_service()
        svc.users().drafts().create().execute.return_value = {
            "id": "draft1",
            "message": {"id": "msg1"},
        }
        result = draft_email(svc, to=["alice@test.com"], subject="Hi", body="Hello")
        assert result["id"] == "draft1"


class TestDelete:
    def test_delete_calls_trash(self):
        svc = _mock_service()
        svc.users().messages().trash().execute.return_value = {"id": "msg1"}
        result = delete_email(svc, "msg1")
        assert result["id"] == "msg1"


class TestBatchDelete:
    def test_batch_delete_calls_trash_for_each(self):
        svc = _mock_service()
        svc.users().messages().trash().execute.return_value = {}
        result = batch_delete_emails(svc, ["msg1", "msg2"])
        assert result["deleted"] == 2


class TestModify:
    def test_modify_adds_labels(self):
        svc = _mock_service()
        svc.users().messages().modify().execute.return_value = {
            "id": "msg1",
            "labelIds": ["INBOX", "STARRED"],
        }
        result = modify_email(svc, "msg1", add_labels=["STARRED"])
        assert "STARRED" in result["labelIds"]


class TestBatchModify:
    def test_batch_modify(self):
        svc = _mock_service()
        svc.users().messages().modify().execute.return_value = {"id": "msg1"}
        result = batch_modify_emails(svc, ["msg1", "msg2"], add_labels=["STARRED"])
        assert result["modified"] == 2


class TestLabels:
    def test_list_labels(self):
        svc = _mock_service()
        svc.users().labels().list().execute.return_value = {
            "labels": [{"id": "INBOX", "name": "INBOX"}]
        }
        result = list_labels(svc)
        assert len(result) == 1

    def test_create_label(self):
        svc = _mock_service()
        svc.users().labels().create().execute.return_value = {
            "id": "Label_1", "name": "MyLabel"
        }
        result = create_label(svc, "MyLabel")
        assert result["name"] == "MyLabel"

    def test_update_label(self):
        svc = _mock_service()
        svc.users().labels().update().execute.return_value = {
            "id": "Label_1", "name": "Renamed"
        }
        result = update_label(svc, "Label_1", name="Renamed")
        assert result["name"] == "Renamed"

    def test_delete_label(self):
        svc = _mock_service()
        svc.users().labels().delete().execute.return_value = None
        result = delete_label(svc, "Label_1")
        assert result["deleted"] is True


class TestFilters:
    def test_list_filters(self):
        svc = _mock_service()
        svc.users().settings().filters().list().execute.return_value = {
            "filter": [{"id": "f1", "criteria": {}, "action": {}}]
        }
        result = list_filters(svc)
        assert len(result) == 1

    def test_get_filter(self):
        svc = _mock_service()
        svc.users().settings().filters().get().execute.return_value = {
            "id": "f1", "criteria": {"from": "a@b.com"}, "action": {}
        }
        result = get_filter(svc, "f1")
        assert result["id"] == "f1"

    def test_create_filter(self):
        svc = _mock_service()
        svc.users().settings().filters().create().execute.return_value = {
            "id": "f2", "criteria": {"from": "x@y.com"}, "action": {"addLabelIds": ["STARRED"]}
        }
        result = create_filter(svc, criteria={"from": "x@y.com"}, action={"addLabelIds": ["STARRED"]})
        assert result["id"] == "f2"

    def test_delete_filter(self):
        svc = _mock_service()
        svc.users().settings().filters().delete().execute.return_value = None
        result = delete_filter(svc, "f1")
        assert result["deleted"] is True


class TestAttachment:
    def test_download_attachment(self, tmp_path):
        svc = _mock_service()
        data = base64.urlsafe_b64encode(b"file content").decode()
        svc.users().messages().attachments().get().execute.return_value = {
            "data": data, "size": 12
        }
        result = download_attachment(
            svc, "msg1", "att1", save_path=str(tmp_path), filename="test.txt"
        )
        assert (tmp_path / "test.txt").exists()
        assert (tmp_path / "test.txt").read_bytes() == b"file content"
```

**Step 2: Run tests to verify they fail**

```bash
cd ~/repos/gmail-multi-mcp
uv run pytest tests/test_gmail_client.py -v
```

Expected: FAIL — `ImportError: cannot import name 'search_emails'`

**Step 3: Implement gmail_client.py**

`src/gmail_multi_mcp/gmail_client.py`:
```python
"""Gmail API wrapper functions.

All functions are stateless — they take a Gmail service object and parameters,
call the API, and return processed results. The server module handles account
resolution and passes the correct service.
"""

import base64
import logging
import mimetypes
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

logger = logging.getLogger(__name__)


# --- Email Operations ---


def search_emails(service, query: str, max_results: int = 10) -> list[dict]:
    resp = service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()

    messages = resp.get("messages", [])
    if not messages:
        return []

    results = []
    for msg_ref in messages:
        msg = service.users().messages().get(
            userId="me", id=msg_ref["id"], format="metadata",
            metadataHeaders=["From", "To", "Subject", "Date"],
        ).execute()
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        results.append({
            "id": msg["id"],
            "threadId": msg.get("threadId"),
            "snippet": msg.get("snippet", ""),
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "labelIds": msg.get("labelIds", []),
        })
    return results


def read_email(service, message_id: str) -> dict:
    msg = service.users().messages().get(
        userId="me", id=message_id, format="full"
    ).execute()

    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
    body = _extract_body(msg.get("payload", {}))
    attachments = _extract_attachments(msg.get("payload", {}))

    return {
        "id": msg["id"],
        "threadId": msg.get("threadId"),
        "snippet": msg.get("snippet", ""),
        "from": headers.get("From", ""),
        "to": headers.get("To", ""),
        "subject": headers.get("Subject", ""),
        "date": headers.get("Date", ""),
        "labelIds": msg.get("labelIds", []),
        "body": body,
        "attachments": attachments,
    }


def send_email(
    service,
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    html_body: str | None = None,
    mime_type: str = "text/plain",
    attachments: list[str] | None = None,
    in_reply_to: str | None = None,
    thread_id: str | None = None,
) -> dict:
    message = _build_message(
        to=to, subject=subject, body=body, cc=cc, bcc=bcc,
        html_body=html_body, mime_type=mime_type,
        attachments=attachments, in_reply_to=in_reply_to,
    )
    send_body = {"raw": base64.urlsafe_b64encode(message.as_bytes()).decode()}
    if thread_id:
        send_body["threadId"] = thread_id

    return service.users().messages().send(userId="me", body=send_body).execute()


def draft_email(
    service,
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    html_body: str | None = None,
    mime_type: str = "text/plain",
    attachments: list[str] | None = None,
    in_reply_to: str | None = None,
    thread_id: str | None = None,
) -> dict:
    message = _build_message(
        to=to, subject=subject, body=body, cc=cc, bcc=bcc,
        html_body=html_body, mime_type=mime_type,
        attachments=attachments, in_reply_to=in_reply_to,
    )
    draft_body = {"message": {"raw": base64.urlsafe_b64encode(message.as_bytes()).decode()}}
    if thread_id:
        draft_body["message"]["threadId"] = thread_id

    return service.users().drafts().create(userId="me", body=draft_body).execute()


def delete_email(service, message_id: str) -> dict:
    return service.users().messages().trash(userId="me", id=message_id).execute()


def batch_delete_emails(
    service, message_ids: list[str], batch_size: int = 50
) -> dict:
    deleted = 0
    for i in range(0, len(message_ids), batch_size):
        batch = message_ids[i : i + batch_size]
        for mid in batch:
            service.users().messages().trash(userId="me", id=mid).execute()
            deleted += 1
    return {"deleted": deleted}


def modify_email(
    service,
    message_id: str,
    add_labels: list[str] | None = None,
    remove_labels: list[str] | None = None,
) -> dict:
    body = {}
    if add_labels:
        body["addLabelIds"] = add_labels
    if remove_labels:
        body["removeLabelIds"] = remove_labels
    return service.users().messages().modify(
        userId="me", id=message_id, body=body
    ).execute()


def batch_modify_emails(
    service,
    message_ids: list[str],
    add_labels: list[str] | None = None,
    remove_labels: list[str] | None = None,
    batch_size: int = 50,
) -> dict:
    modified = 0
    body = {}
    if add_labels:
        body["addLabelIds"] = add_labels
    if remove_labels:
        body["removeLabelIds"] = remove_labels

    for i in range(0, len(message_ids), batch_size):
        batch = message_ids[i : i + batch_size]
        for mid in batch:
            service.users().messages().modify(
                userId="me", id=mid, body=body
            ).execute()
            modified += 1
    return {"modified": modified}


# --- Labels ---


def list_labels(service) -> list[dict]:
    resp = service.users().labels().list(userId="me").execute()
    return resp.get("labels", [])


def create_label(
    service,
    name: str,
    label_list_visibility: str = "labelShow",
    message_list_visibility: str = "show",
) -> dict:
    body = {
        "name": name,
        "labelListVisibility": label_list_visibility,
        "messageListVisibility": message_list_visibility,
    }
    return service.users().labels().create(userId="me", body=body).execute()


def update_label(
    service,
    label_id: str,
    name: str | None = None,
    label_list_visibility: str | None = None,
    message_list_visibility: str | None = None,
) -> dict:
    body = {}
    if name is not None:
        body["name"] = name
    if label_list_visibility is not None:
        body["labelListVisibility"] = label_list_visibility
    if message_list_visibility is not None:
        body["messageListVisibility"] = message_list_visibility
    return service.users().labels().update(
        userId="me", id=label_id, body=body
    ).execute()


def delete_label(service, label_id: str) -> dict:
    service.users().labels().delete(userId="me", id=label_id).execute()
    return {"deleted": True, "label_id": label_id}


# --- Filters ---


def list_filters(service) -> list[dict]:
    resp = service.users().settings().filters().list(userId="me").execute()
    return resp.get("filter", [])


def get_filter(service, filter_id: str) -> dict:
    return service.users().settings().filters().get(
        userId="me", id=filter_id
    ).execute()


def create_filter(service, criteria: dict, action: dict) -> dict:
    body = {"criteria": criteria, "action": action}
    return service.users().settings().filters().create(
        userId="me", body=body
    ).execute()


def delete_filter(service, filter_id: str) -> dict:
    service.users().settings().filters().delete(
        userId="me", id=filter_id
    ).execute()
    return {"deleted": True, "filter_id": filter_id}


# --- Attachments ---


def download_attachment(
    service,
    message_id: str,
    attachment_id: str,
    save_path: str = ".",
    filename: str | None = None,
) -> dict:
    att = service.users().messages().attachments().get(
        userId="me", messageId=message_id, id=attachment_id
    ).execute()

    data = base64.urlsafe_b64decode(att["data"])
    out_name = filename or f"attachment-{attachment_id}"
    out_path = Path(save_path) / out_name
    out_path.write_bytes(data)

    return {
        "filename": out_name,
        "path": str(out_path),
        "size": len(data),
    }


# --- Helpers ---


def _build_message(
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    html_body: str | None = None,
    mime_type: str = "text/plain",
    attachments: list[str] | None = None,
    in_reply_to: str | None = None,
):
    has_attachments = attachments and len(attachments) > 0

    if mime_type == "multipart/alternative" or (html_body and not has_attachments):
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body, "plain"))
        if html_body:
            msg.attach(MIMEText(html_body, "html"))
    elif has_attachments:
        msg = MIMEMultipart("mixed")
        if html_body:
            alt = MIMEMultipart("alternative")
            alt.attach(MIMEText(body, "plain"))
            alt.attach(MIMEText(html_body, "html"))
            msg.attach(alt)
        else:
            msg.attach(MIMEText(body, "plain" if mime_type == "text/plain" else "html"))
    else:
        subtype = "html" if mime_type == "text/html" else "plain"
        msg = MIMEText(body, subtype)

    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = ", ".join(cc)
    if bcc:
        msg["Bcc"] = ", ".join(bcc)
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to

    if has_attachments:
        for filepath in attachments:
            path = Path(filepath)
            content_type, _ = mimetypes.guess_type(str(path))
            if content_type is None:
                content_type = "application/octet-stream"
            main_type, sub_type = content_type.split("/", 1)
            att = MIMEBase(main_type, sub_type)
            att.set_payload(path.read_bytes())
            encoders.encode_base64(att)
            att.add_header("Content-Disposition", "attachment", filename=path.name)
            msg.attach(att)

    return msg


def _extract_body(payload: dict) -> str:
    if payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

    parts = payload.get("parts", [])
    for part in parts:
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")

    for part in parts:
        if part.get("mimeType") == "text/html" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")

    for part in parts:
        nested = _extract_body(part)
        if nested:
            return nested

    return ""


def _extract_attachments(payload: dict) -> list[dict]:
    attachments = []
    parts = payload.get("parts", [])
    for part in parts:
        if part.get("filename") and part.get("body", {}).get("attachmentId"):
            attachments.append({
                "filename": part["filename"],
                "mimeType": part.get("mimeType", "application/octet-stream"),
                "attachmentId": part["body"]["attachmentId"],
                "size": part["body"].get("size", 0),
            })
        if part.get("parts"):
            attachments.extend(_extract_attachments(part))
    return attachments
```

**Step 4: Run tests to verify they pass**

```bash
cd ~/repos/gmail-multi-mcp
uv run pytest tests/test_gmail_client.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
cd ~/repos/gmail-multi-mcp
git add src/gmail_multi_mcp/gmail_client.py tests/test_gmail_client.py
git commit -m "feat: gmail client with full API coverage (search, read, send, draft, labels, filters, attachments)"
```

---

## Task 4: MCP Server — Account Management Tools

**Files:**
- Modify: `~/repos/gmail-multi-mcp/src/gmail_multi_mcp/server.py`
- Create: `~/repos/gmail-multi-mcp/tests/test_server.py`

**Step 1: Write failing tests for account tools**

`tests/test_server.py`:
```python
"""Tests for the MCP server tools."""

import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from gmail_multi_mcp.server import (
    gmail_list_accounts,
    gmail_switch_account,
    gmail_current_account,
)
from gmail_multi_mcp.accounts import AccountManager


@pytest.fixture
def account_manager(tmp_config_dir):
    return AccountManager(tmp_config_dir)


class TestAccountTools:
    @pytest.mark.asyncio
    async def test_list_accounts(self, account_manager):
        with patch("gmail_multi_mcp.server._manager", account_manager):
            result = json.loads(await gmail_list_accounts())
            assert len(result["accounts"]) == 2
            active = [a for a in result["accounts"] if a["active"]]
            assert len(active) == 1

    @pytest.mark.asyncio
    async def test_switch_account(self, account_manager):
        with patch("gmail_multi_mcp.server._manager", account_manager):
            result = json.loads(await gmail_switch_account("personal"))
            assert result["active_account"] == "personal"

    @pytest.mark.asyncio
    async def test_switch_to_invalid_account(self, account_manager):
        with patch("gmail_multi_mcp.server._manager", account_manager):
            result = json.loads(await gmail_switch_account("nonexistent"))
            assert "error" in result

    @pytest.mark.asyncio
    async def test_current_account(self, account_manager):
        with patch("gmail_multi_mcp.server._manager", account_manager):
            result = json.loads(await gmail_current_account())
            assert result["name"] == "work"
            assert result["email"] == "work@example.com"
```

**Step 2: Run tests to verify they fail**

```bash
cd ~/repos/gmail-multi-mcp
uv run pytest tests/test_server.py -v
```

Expected: FAIL

**Step 3: Implement server.py with account tools**

`src/gmail_multi_mcp/server.py`:
```python
"""FastMCP server with multi-account Gmail tools."""

import json
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, ConfigDict

from .accounts import AccountManager, AccountNotFoundError
from . import gmail_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# Module-level state
_manager: Optional[AccountManager] = None

CONFIG_DIR = Path.home() / ".gmail-mcp"


@asynccontextmanager
async def server_lifespan(mcp_server):
    global _manager
    config_dir = CONFIG_DIR
    if len(sys.argv) > 1 and sys.argv[1] != "auth":
        config_dir = Path(sys.argv[1])

    _manager = AccountManager(config_dir)
    logger.info(
        "Gmail Multi MCP ready: %d accounts, active=%s",
        len(_manager.account_names),
        _manager.active_account,
    )
    yield {"manager": _manager}


mcp = FastMCP(
    "gmail_multi_mcp",
    lifespan=server_lifespan,
    instructions=(
        "Multi-account Gmail MCP server. Manages multiple Gmail accounts with JIT switching.\n\n"
        "ACCOUNT RESOLUTION:\n"
        "- Every Gmail tool accepts an optional 'account' parameter (account label name)\n"
        "- If 'account' is omitted, the currently active account is used\n"
        "- Use gmail_list_accounts to see available accounts and which is active\n"
        "- Use gmail_switch_account to change the default active account\n\n"
        "WHEN TO SWITCH:\n"
        "- When the user mentions a specific email address or domain, match it to an account\n"
        "- When the user says 'work email', 'personal email', etc., infer the right account\n"
        "- When doing cross-account operations, use the 'account' parameter on individual tools\n"
    ),
)


# --- Account Management Tools ---


@mcp.tool(name="gmail_list_accounts")
async def gmail_list_accounts() -> str:
    """List all configured Gmail accounts and which one is currently active."""
    if _manager is None:
        return json.dumps({"error": "Server not initialized."})
    return json.dumps({"accounts": _manager.list_accounts_info()}, indent=2)


@mcp.tool(name="gmail_switch_account")
async def gmail_switch_account(account: str = Field(description="Account label to switch to")) -> str:
    """Switch the active Gmail account. All subsequent operations will use this account by default."""
    if _manager is None:
        return json.dumps({"error": "Server not initialized."})
    try:
        _manager.switch(account)
        return json.dumps({
            "active_account": _manager.active_account,
            "email": _manager.get_email(account),
            "message": f"Switched to {account}",
        })
    except AccountNotFoundError as e:
        return json.dumps({"error": str(e)})


@mcp.tool(name="gmail_current_account")
async def gmail_current_account() -> str:
    """Show the currently active Gmail account."""
    if _manager is None:
        return json.dumps({"error": "Server not initialized."})
    name = _manager.active_account
    return json.dumps({
        "name": name,
        "email": _manager.get_email(name) if name else None,
    })


# --- Helper to resolve account and get service ---


def _get_service(account: str | None = None):
    """Resolve account name and return Gmail API service."""
    if _manager is None:
        raise RuntimeError("Server not initialized")
    return _manager.get_service(account)


# (Email operation tools added in Task 5)


def main():
    """Entry point — handles both 'auth' subcommand and normal MCP server."""
    if len(sys.argv) > 1 and sys.argv[1] == "auth":
        from .auth import run_auth
        run_auth(sys.argv[2:])
    else:
        mcp.run()


if __name__ == "__main__":
    main()
```

**Step 4: Run tests to verify they pass**

```bash
cd ~/repos/gmail-multi-mcp
uv run pytest tests/test_server.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
cd ~/repos/gmail-multi-mcp
git add src/gmail_multi_mcp/server.py tests/test_server.py
git commit -m "feat: MCP server with account management tools (list, switch, current)"
```

---

## Task 5: MCP Server — Email Operation Tools

**Files:**
- Modify: `~/repos/gmail-multi-mcp/src/gmail_multi_mcp/server.py`
- Modify: `~/repos/gmail-multi-mcp/tests/test_server.py`

**Step 1: Write failing tests for email tools**

Append to `tests/test_server.py`:
```python
class TestEmailTools:
    @pytest.mark.asyncio
    @patch("gmail_multi_mcp.server._manager")
    async def test_search_delegates_to_client(self, mock_mgr):
        mock_svc = MagicMock()
        mock_mgr.get_service.return_value = mock_svc
        mock_mgr.resolve.return_value = "work"
        mock_mgr.get_email.return_value = "work@example.com"

        with patch("gmail_multi_mcp.server.gmail_client.search_emails", return_value=[{"id": "m1"}]) as mock_search:
            from gmail_multi_mcp.server import gmail_search_emails
            result = json.loads(await gmail_search_emails("from:test"))
            mock_search.assert_called_once_with(mock_svc, "from:test", max_results=10)
            assert result["results"][0]["id"] == "m1"

    @pytest.mark.asyncio
    @patch("gmail_multi_mcp.server._manager")
    async def test_search_with_account_override(self, mock_mgr):
        mock_svc = MagicMock()
        mock_mgr.get_service.return_value = mock_svc
        mock_mgr.resolve.return_value = "personal"
        mock_mgr.get_email.return_value = "personal@gmail.com"

        with patch("gmail_multi_mcp.server.gmail_client.search_emails", return_value=[]) as mock_search:
            from gmail_multi_mcp.server import gmail_search_emails
            result = json.loads(await gmail_search_emails("test", account="personal"))
            mock_mgr.get_service.assert_called_with("personal")

    @pytest.mark.asyncio
    @patch("gmail_multi_mcp.server._manager")
    async def test_send_delegates_to_client(self, mock_mgr):
        mock_svc = MagicMock()
        mock_mgr.get_service.return_value = mock_svc
        mock_mgr.resolve.return_value = "work"
        mock_mgr.get_email.return_value = "work@example.com"

        with patch("gmail_multi_mcp.server.gmail_client.send_email", return_value={"id": "sent1"}) as mock_send:
            from gmail_multi_mcp.server import gmail_send_email
            result = json.loads(await gmail_send_email(
                to=["bob@test.com"], subject="Hi", body="Hello"
            ))
            assert result["result"]["id"] == "sent1"
```

**Step 2: Run tests to verify they fail**

```bash
cd ~/repos/gmail-multi-mcp
uv run pytest tests/test_server.py::TestEmailTools -v
```

Expected: FAIL

**Step 3: Add all email operation tools to server.py**

Append to `src/gmail_multi_mcp/server.py` (after the account tools):
```python
# --- Email Operation Tools ---


@mcp.tool(name="gmail_search_emails")
async def gmail_search_emails(
    query: str = Field(description="Gmail search query (e.g., 'from:example@gmail.com')"),
    max_results: int = Field(default=10, description="Maximum results to return (1-50)", ge=1, le=50),
    account: Optional[str] = Field(default=None, description="Account label to use (omit for active account)"),
) -> str:
    """Search emails using Gmail search syntax."""
    try:
        svc = _get_service(account)
        resolved = _manager.resolve(account)
        results = gmail_client.search_emails(svc, query, max_results=max_results)
        return json.dumps({
            "account": resolved,
            "email": _manager.get_email(resolved),
            "query": query,
            "result_count": len(results),
            "results": results,
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool(name="gmail_read_email")
async def gmail_read_email(
    message_id: str = Field(description="ID of the email message to retrieve"),
    account: Optional[str] = Field(default=None, description="Account label to use"),
) -> str:
    """Read a specific email by its message ID."""
    try:
        svc = _get_service(account)
        result = gmail_client.read_email(svc, message_id)
        return json.dumps({"account": _manager.resolve(account), "message": result}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool(name="gmail_send_email")
async def gmail_send_email(
    to: list[str] = Field(description="Recipient email addresses"),
    subject: str = Field(description="Email subject"),
    body: str = Field(description="Email body content"),
    cc: Optional[list[str]] = Field(default=None, description="CC recipients"),
    bcc: Optional[list[str]] = Field(default=None, description="BCC recipients"),
    html_body: Optional[str] = Field(default=None, description="HTML version of the body"),
    mime_type: str = Field(default="text/plain", description="Content type"),
    attachments: Optional[list[str]] = Field(default=None, description="File paths to attach"),
    in_reply_to: Optional[str] = Field(default=None, description="Message ID being replied to"),
    thread_id: Optional[str] = Field(default=None, description="Thread ID to reply to"),
    account: Optional[str] = Field(default=None, description="Account label to use"),
) -> str:
    """Send an email from the specified account."""
    try:
        svc = _get_service(account)
        result = gmail_client.send_email(
            svc, to=to, subject=subject, body=body, cc=cc, bcc=bcc,
            html_body=html_body, mime_type=mime_type, attachments=attachments,
            in_reply_to=in_reply_to, thread_id=thread_id,
        )
        return json.dumps({"account": _manager.resolve(account), "result": result}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool(name="gmail_draft_email")
async def gmail_draft_email(
    to: list[str] = Field(description="Recipient email addresses"),
    subject: str = Field(description="Email subject"),
    body: str = Field(description="Email body content"),
    cc: Optional[list[str]] = Field(default=None, description="CC recipients"),
    bcc: Optional[list[str]] = Field(default=None, description="BCC recipients"),
    html_body: Optional[str] = Field(default=None, description="HTML version of the body"),
    mime_type: str = Field(default="text/plain", description="Content type"),
    attachments: Optional[list[str]] = Field(default=None, description="File paths to attach"),
    in_reply_to: Optional[str] = Field(default=None, description="Message ID being replied to"),
    thread_id: Optional[str] = Field(default=None, description="Thread ID to reply to"),
    account: Optional[str] = Field(default=None, description="Account label to use"),
) -> str:
    """Create a draft email in the specified account."""
    try:
        svc = _get_service(account)
        result = gmail_client.draft_email(
            svc, to=to, subject=subject, body=body, cc=cc, bcc=bcc,
            html_body=html_body, mime_type=mime_type, attachments=attachments,
            in_reply_to=in_reply_to, thread_id=thread_id,
        )
        return json.dumps({"account": _manager.resolve(account), "result": result}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool(name="gmail_delete_email")
async def gmail_delete_email(
    message_id: str = Field(description="ID of the email to delete"),
    account: Optional[str] = Field(default=None, description="Account label to use"),
) -> str:
    """Move an email to trash."""
    try:
        svc = _get_service(account)
        result = gmail_client.delete_email(svc, message_id)
        return json.dumps({"account": _manager.resolve(account), "result": result}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool(name="gmail_batch_delete_emails")
async def gmail_batch_delete_emails(
    message_ids: list[str] = Field(description="List of message IDs to delete"),
    batch_size: int = Field(default=50, description="Batch size for processing"),
    account: Optional[str] = Field(default=None, description="Account label to use"),
) -> str:
    """Batch delete (trash) multiple emails."""
    try:
        svc = _get_service(account)
        result = gmail_client.batch_delete_emails(svc, message_ids, batch_size)
        return json.dumps({"account": _manager.resolve(account), "result": result}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool(name="gmail_modify_email")
async def gmail_modify_email(
    message_id: str = Field(description="ID of the email to modify"),
    add_label_ids: Optional[list[str]] = Field(default=None, description="Label IDs to add"),
    remove_label_ids: Optional[list[str]] = Field(default=None, description="Label IDs to remove"),
    account: Optional[str] = Field(default=None, description="Account label to use"),
) -> str:
    """Modify labels on an email."""
    try:
        svc = _get_service(account)
        result = gmail_client.modify_email(svc, message_id, add_label_ids, remove_label_ids)
        return json.dumps({"account": _manager.resolve(account), "result": result}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool(name="gmail_batch_modify_emails")
async def gmail_batch_modify_emails(
    message_ids: list[str] = Field(description="List of message IDs to modify"),
    add_label_ids: Optional[list[str]] = Field(default=None, description="Label IDs to add"),
    remove_label_ids: Optional[list[str]] = Field(default=None, description="Label IDs to remove"),
    batch_size: int = Field(default=50, description="Batch size"),
    account: Optional[str] = Field(default=None, description="Account label to use"),
) -> str:
    """Batch modify labels on multiple emails."""
    try:
        svc = _get_service(account)
        result = gmail_client.batch_modify_emails(
            svc, message_ids, add_label_ids, remove_label_ids, batch_size
        )
        return json.dumps({"account": _manager.resolve(account), "result": result}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool(name="gmail_list_labels")
async def gmail_list_labels(
    account: Optional[str] = Field(default=None, description="Account label to use"),
) -> str:
    """List all Gmail labels for the account."""
    try:
        svc = _get_service(account)
        labels = gmail_client.list_labels(svc)
        return json.dumps({"account": _manager.resolve(account), "labels": labels}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool(name="gmail_create_label")
async def gmail_create_label(
    name: str = Field(description="Name for the new label"),
    label_list_visibility: str = Field(default="labelShow", description="Label list visibility"),
    message_list_visibility: str = Field(default="show", description="Message list visibility"),
    account: Optional[str] = Field(default=None, description="Account label to use"),
) -> str:
    """Create a new Gmail label."""
    try:
        svc = _get_service(account)
        result = gmail_client.create_label(svc, name, label_list_visibility, message_list_visibility)
        return json.dumps({"account": _manager.resolve(account), "result": result}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool(name="gmail_update_label")
async def gmail_update_label(
    label_id: str = Field(description="ID of the label to update"),
    name: Optional[str] = Field(default=None, description="New name"),
    label_list_visibility: Optional[str] = Field(default=None, description="Label list visibility"),
    message_list_visibility: Optional[str] = Field(default=None, description="Message list visibility"),
    account: Optional[str] = Field(default=None, description="Account label to use"),
) -> str:
    """Update an existing Gmail label."""
    try:
        svc = _get_service(account)
        result = gmail_client.update_label(svc, label_id, name, label_list_visibility, message_list_visibility)
        return json.dumps({"account": _manager.resolve(account), "result": result}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool(name="gmail_delete_label")
async def gmail_delete_label(
    label_id: str = Field(description="ID of the label to delete"),
    account: Optional[str] = Field(default=None, description="Account label to use"),
) -> str:
    """Delete a Gmail label."""
    try:
        svc = _get_service(account)
        result = gmail_client.delete_label(svc, label_id)
        return json.dumps({"account": _manager.resolve(account), "result": result}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool(name="gmail_list_filters")
async def gmail_list_filters(
    account: Optional[str] = Field(default=None, description="Account label to use"),
) -> str:
    """List all Gmail filters for the account."""
    try:
        svc = _get_service(account)
        filters = gmail_client.list_filters(svc)
        return json.dumps({"account": _manager.resolve(account), "filters": filters}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool(name="gmail_get_filter")
async def gmail_get_filter(
    filter_id: str = Field(description="ID of the filter to retrieve"),
    account: Optional[str] = Field(default=None, description="Account label to use"),
) -> str:
    """Get details of a specific Gmail filter."""
    try:
        svc = _get_service(account)
        result = gmail_client.get_filter(svc, filter_id)
        return json.dumps({"account": _manager.resolve(account), "filter": result}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool(name="gmail_create_filter")
async def gmail_create_filter(
    criteria: dict = Field(description="Filter criteria (from, to, subject, query, etc.)"),
    action: dict = Field(description="Filter actions (addLabelIds, removeLabelIds, forward)"),
    account: Optional[str] = Field(default=None, description="Account label to use"),
) -> str:
    """Create a new Gmail filter."""
    try:
        svc = _get_service(account)
        result = gmail_client.create_filter(svc, criteria, action)
        return json.dumps({"account": _manager.resolve(account), "result": result}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool(name="gmail_delete_filter")
async def gmail_delete_filter(
    filter_id: str = Field(description="ID of the filter to delete"),
    account: Optional[str] = Field(default=None, description="Account label to use"),
) -> str:
    """Delete a Gmail filter."""
    try:
        svc = _get_service(account)
        result = gmail_client.delete_filter(svc, filter_id)
        return json.dumps({"account": _manager.resolve(account), "result": result}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool(name="gmail_download_attachment")
async def gmail_download_attachment(
    message_id: str = Field(description="ID of the email containing the attachment"),
    attachment_id: str = Field(description="ID of the attachment"),
    save_path: str = Field(default=".", description="Directory to save the attachment"),
    filename: Optional[str] = Field(default=None, description="Filename to save as"),
    account: Optional[str] = Field(default=None, description="Account label to use"),
) -> str:
    """Download an email attachment to a specified location."""
    try:
        svc = _get_service(account)
        result = gmail_client.download_attachment(svc, message_id, attachment_id, save_path, filename)
        return json.dumps({"account": _manager.resolve(account), "result": result}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})
```

**Step 4: Run all tests**

```bash
cd ~/repos/gmail-multi-mcp
uv run pytest -v
```

Expected: All PASS

**Step 5: Commit**

```bash
cd ~/repos/gmail-multi-mcp
git add src/gmail_multi_mcp/server.py tests/test_server.py
git commit -m "feat: all email operation tools with per-op account override"
```

---

## Task 6: Auth CLI Command

**Files:**
- Create: `~/repos/gmail-multi-mcp/src/gmail_multi_mcp/auth.py`
- Create: `~/repos/gmail-multi-mcp/tests/test_auth.py`

**Step 1: Write failing test**

`tests/test_auth.py`:
```python
"""Tests for auth CLI command."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from gmail_multi_mcp.auth import run_auth


class TestAuth:
    def test_auth_requires_name(self, capsys):
        with pytest.raises(SystemExit):
            run_auth([])

    @patch("gmail_multi_mcp.auth.InstalledAppFlow")
    def test_auth_saves_credentials(self, mock_flow_cls, tmp_path):
        mock_flow = MagicMock()
        mock_creds = MagicMock()
        mock_creds.token = "ya29.new-token"
        mock_creds.refresh_token = "1//new-refresh"
        mock_creds.expiry = None
        mock_flow.run_local_server.return_value = mock_creds
        mock_flow_cls.from_client_secrets_file.return_value = mock_flow

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

        assert (tmp_path / "accounts" / "newacct.json").exists()
        config = json.loads((tmp_path / "config.json").read_text())
        assert "newacct" in config["accounts"]
```

**Step 2: Run test to verify it fails**

```bash
cd ~/repos/gmail-multi-mcp
uv run pytest tests/test_auth.py -v
```

Expected: FAIL

**Step 3: Implement auth.py**

`src/gmail_multi_mcp/auth.py`:
```python
"""OAuth authentication CLI for adding new Gmail accounts."""

import argparse
import json
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

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
    creds_path.write_text(json.dumps(creds_data))
    print(f"Credentials saved to: {creds_path}")

    # Get the authenticated email address
    from googleapiclient.discovery import build
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
    print(f"To use it: gmail_switch_account(account='{args.name}')")
```

**Step 4: Run tests**

```bash
cd ~/repos/gmail-multi-mcp
uv run pytest tests/test_auth.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
cd ~/repos/gmail-multi-mcp
git add src/gmail_multi_mcp/auth.py tests/test_auth.py
git commit -m "feat: OAuth auth CLI for adding new Gmail accounts"
```

---

## Task 7: MCP Registration + Credential Migration

**Files:**
- Modify: `~/.claude.json` (add gmail-multi MCP server)
- Migrate: `~/.gmail-mcp/credentials-luis@lefv.io.json` → `~/.gmail-mcp/accounts/lefv.json`
- Create: `~/.gmail-mcp/config.json`
- Create: `~/.gmail-mcp/accounts/` directory

**Step 1: Create accounts directory and migrate existing credentials**

```bash
mkdir -p ~/.gmail-mcp/accounts
cp ~/.gmail-mcp/credentials-luis@lefv.io.json ~/.gmail-mcp/accounts/lefv.json
```

**Step 2: Create config.json**

Write `~/.gmail-mcp/config.json`:
```json
{
  "accounts": {
    "lefv": "luis@lefv.io"
  },
  "default": "lefv"
}
```

**Step 3: Install the package in the venv**

```bash
cd ~/repos/gmail-multi-mcp
uv venv
uv pip install -e ".[dev]"
```

**Step 4: Run all tests to verify**

```bash
cd ~/repos/gmail-multi-mcp
uv run pytest -v
```

Expected: All PASS

**Step 5: Register MCP server**

```bash
claude mcp add --transport stdio --scope user gmail-multi -- \
  /Users/home/repos/gmail-multi-mcp/.venv/bin/gmail-multi-mcp
```

**Step 6: Authenticate remaining accounts**

```bash
cd ~/repos/gmail-multi-mcp
uv run gmail-multi-mcp auth --name everlong
# Browser opens → sign in with luis@everlongtech.com

uv run gmail-multi-mcp auth --name personal
# Browser opens → sign in with luis.e.fernandezdelavara@gmail.com
```

**Step 7: Verify config.json has all three accounts**

```bash
cat ~/.gmail-mcp/config.json
```

Expected:
```json
{
  "accounts": {
    "lefv": "luis@lefv.io",
    "everlong": "luis@everlongtech.com",
    "personal": "luis.e.fernandezdelavara@gmail.com"
  },
  "default": "lefv"
}
```

**Step 8: Commit**

```bash
cd ~/repos/gmail-multi-mcp
git add -A
git commit -m "feat: complete gmail-multi-mcp with 3 accounts registered"
```

---

## Task 8: Integration Smoke Test

**Step 1: Start a new Claude Code session and verify the MCP loads**

In a new Claude Code session, run:
- `gmail_list_accounts` → should show all 3 accounts
- `gmail_switch_account(account="everlong")` → should switch
- `gmail_search_emails(query="is:unread", max_results=3)` → should return results from everlong
- `gmail_search_emails(query="is:unread", max_results=3, account="lefv")` → per-op override to lefv

**Step 2: Verify coexistence with old Gmail MCP**

The old `gmail` MCP and new `gmail-multi` MCP should both appear in tool lists without conflict.

**Step 3: Final commit**

```bash
cd ~/repos/gmail-multi-mcp
git add -A
git commit -m "docs: implementation plan and design docs"
```
