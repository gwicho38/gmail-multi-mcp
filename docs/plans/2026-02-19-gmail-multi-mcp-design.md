# gmail-multi-mcp Design

**Date:** 2026-02-19
**Status:** Approved

## Problem

The current Gmail MCP (`@gongrzhe/server-gmail-autoauth-mcp`) supports only one Gmail account at a time. Switching requires manually swapping credential files and restarting the server. We need just-in-time (JIT) account switching within a single conversation.

## Solution

A Python MCP server using `FastMCP` that manages multiple Gmail accounts and exposes all Gmail operations with per-operation account selection.

## Accounts (Initial)

| Label | Email |
|-------|-------|
| lefv | luis@lefv.io |
| everlong | luis@everlongtech.com |
| personal | luis.e.fernandezdelavara@gmail.com |

Designed for easy addition of new accounts via CLI auth command.

## Architecture

### File Layout

```
~/.gmail-mcp/
├── gcp-oauth.keys.json          # Shared GCP OAuth client (existing)
├── accounts/
│   ├── lefv.json                # OAuth tokens for luis@lefv.io
│   ├── everlong.json            # OAuth tokens for luis@everlongtech.com
│   └── personal.json            # OAuth tokens for luis.e.fernandezdelavara@gmail.com
└── config.json                  # Account registry {name: email, ...}

~/repos/gmail-multi-mcp/
├── pyproject.toml
├── src/gmail_multi_mcp/
│   ├── __init__.py
│   ├── server.py                # FastMCP server + tool definitions
│   ├── accounts.py              # Account manager (load, switch, auth)
│   └── gmail_client.py          # Gmail API wrapper
└── tests/
```

### Account Switching

Two mechanisms:
1. **`gmail_switch_account` tool** - Sets the active account for all subsequent calls
2. **Per-operation `account` parameter** - Every Gmail tool accepts an optional `account` param for one-off overrides

### Credential Management

- Reuses the existing `~/.gmail-mcp/gcp-oauth.keys.json` (GCP OAuth client ID/secret)
- Each account has its own token file in `~/.gmail-mcp/accounts/<label>.json`
- Tokens auto-refresh using the Google Auth library
- `config.json` maps labels to email addresses

### Server Lifespan

On startup:
1. Read `~/.gmail-mcp/config.json` for account registry
2. Load OAuth credentials for each account
3. Set first account as default active
4. Build Gmail API service objects per account

On shutdown:
- Persist any refreshed tokens back to disk

## Tools

### Account Management

| Tool | Parameters | Description |
|------|-----------|-------------|
| `gmail_list_accounts` | — | List all accounts + active indicator |
| `gmail_switch_account` | `account` | Switch active account |
| `gmail_current_account` | — | Show active account |

### Email Operations

All accept optional `account` parameter for per-op override.

| Tool | Key Parameters | Description |
|------|---------------|-------------|
| `gmail_search` | `query`, `max_results?` | Search emails |
| `gmail_read` | `message_id` | Read a specific email |
| `gmail_send` | `to`, `subject`, `body`, `cc?`, `bcc?` | Send email |
| `gmail_draft` | `to`, `subject`, `body` | Create draft |
| `gmail_delete` | `message_id` | Delete email |
| `gmail_batch_delete` | `message_ids` | Batch delete |
| `gmail_modify` | `message_id`, `add_labels?`, `remove_labels?` | Modify labels |
| `gmail_batch_modify` | `message_ids`, `add_labels?`, `remove_labels?` | Batch modify |
| `gmail_list_labels` | — | List labels |
| `gmail_create_label` | `name` | Create label |
| `gmail_delete_label` | `label_id` | Delete label |
| `gmail_update_label` | `label_id`, `name?` | Update label |
| `gmail_list_filters` | — | List filters |
| `gmail_create_filter` | `criteria`, `actions` | Create filter |
| `gmail_delete_filter` | `filter_id` | Delete filter |
| `gmail_download_attachment` | `message_id`, `attachment_id` | Download attachment |

## MCP Registration

```json
{
  "gmail-multi": {
    "type": "stdio",
    "command": "/Users/home/repos/gmail-multi-mcp/.venv/bin/gmail-multi-mcp",
    "args": []
  }
}
```

Coexists alongside the existing `gmail` MCP server.

## Dependencies

```
mcp[cli]>=1.0.0
google-api-python-client>=2.100.0
google-auth-oauthlib>=1.2.0
google-auth>=2.25.0
pydantic>=2.0.0
```

## Auth Flow

Adding a new account:
```bash
gmail-multi-mcp auth --name <label>
```

1. Reads GCP OAuth keys from `~/.gmail-mcp/gcp-oauth.keys.json`
2. Spins up local HTTP server on port 3000 for OAuth callback
3. Opens browser for Google sign-in
4. Exchanges auth code for tokens
5. Saves tokens to `~/.gmail-mcp/accounts/<label>.json`
6. Updates `~/.gmail-mcp/config.json`

## Server Instructions (for Claude)

The MCP instructions field tells Claude to:
- Use `gmail_list_accounts` when the user asks about their email accounts
- Switch accounts when user context implies a specific account (e.g., "check my work email")
- Use the `account` parameter for cross-account operations
- Default to the active account when no context is given

## Deployment Strategy

- Coexist with existing `gmail` MCP (npm-based)
- Register as `gmail-multi` in `~/.claude.json`
- Migrate existing `credentials-luis@lefv.io.json` to `accounts/lefv.json`
