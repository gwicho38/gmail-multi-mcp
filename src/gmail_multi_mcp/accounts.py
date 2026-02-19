"""Account manager for multi-Gmail credential handling."""

import json
import logging
from dataclasses import dataclass
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
        if account is None and self._active is None:
            raise AccountNotFoundError("No accounts configured.")
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

        client_id, client_secret = self._get_client_credentials()
        creds = Credentials(
            token=creds_data.get("access_token"),
            refresh_token=creds_data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES,
        )

        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                creds_data["access_token"] = creds.token
                acct.credentials_path.write_text(json.dumps(creds_data))
                logger.info("Refreshed token for account: %s", name)
            else:
                raise ValueError(
                    f"Credentials for '{name}' are invalid and cannot be refreshed."
                )

        service = build("gmail", "v1", credentials=creds)
        self._services[name] = service
        return service

    def _get_client_credentials(self) -> tuple[str, str]:
        keys = json.loads(self._oauth_keys_path.read_text())
        installed = keys["installed"]
        return installed["client_id"], installed["client_secret"]

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
        self._services.pop(name, None)

        config_path = self._config_dir / "config.json"
        config = (
            json.loads(config_path.read_text())
            if config_path.exists()
            else {"accounts": {}}
        )
        config["accounts"][name] = email
        config_path.write_text(json.dumps(config, indent=2))

        logger.info("Added account: %s (%s)", name, email)
