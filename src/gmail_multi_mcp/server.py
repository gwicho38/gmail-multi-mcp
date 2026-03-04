"""FastMCP server with multi-account Gmail tools."""

import json
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .accounts import AccountManager, AccountNotFoundError
from . import gmail_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

_manager: Optional[AccountManager] = None
CONFIG_DIR = Path.home() / ".gmail-mcp"


@asynccontextmanager
async def server_lifespan(mcp_server):
    """Load AccountManager on startup."""
    global _manager
    config_dir = CONFIG_DIR
    if len(sys.argv) > 1 and sys.argv[1] not in ("auth",) and Path(sys.argv[1]).is_dir():
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
        "CROSS-ACCOUNT SEARCH (DEFAULT):\n"
        "- gmail_search_emails searches ALL accounts when 'account' is omitted\n"
        "- For vague queries like 'emails from dylan', ALWAYS omit the account param to search everywhere\n"
        "- Only specify 'account' when the user explicitly asks about a specific account\n"
        "- Results include '_account' and '_email' fields to identify which account each result came from\n\n"
        "WHEN TO SPECIFY ACCOUNT:\n"
        "- When the user mentions a specific email address or domain, match it to an account\n"
        "- When the user says 'work email', 'personal email', etc., infer the right account\n"
        "- For write operations (send, draft, delete), always resolve to a specific account\n"
    ),
)


def _get_service(account: str | None = None):
    """Get a Gmail API service object, optionally for a specific account."""
    if _manager is None:
        raise RuntimeError("Server not initialized")
    return _manager.get_service(account)


# ---------------------------------------------------------------------------
# Account Management Tools
# ---------------------------------------------------------------------------


@mcp.tool(name="gmail_list_accounts")
async def gmail_list_accounts() -> str:
    """List all configured Gmail accounts and which one is currently active."""
    try:
        if _manager is None:
            raise RuntimeError("Server not initialized")
        return json.dumps(
            {
                "active": _manager.active_account,
                "accounts": _manager.list_accounts_info(),
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool(name="gmail_switch_account")
async def gmail_switch_account(
    account: Annotated[str, Field(description="Account label name to switch to")],
) -> str:
    """Switch the active Gmail account. All subsequent operations will use this account by default."""
    try:
        if _manager is None:
            raise RuntimeError("Server not initialized")
        _manager.switch(account)
        return json.dumps(
            {
                "switched_to": account,
                "email": _manager.get_email(account),
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool(name="gmail_current_account")
async def gmail_current_account() -> str:
    """Show the currently active Gmail account name and email."""
    try:
        if _manager is None:
            raise RuntimeError("Server not initialized")
        active = _manager.active_account
        email = _manager.get_email(active) if active else None
        return json.dumps(
            {"account": active, "email": email},
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Email Operation Tools
# ---------------------------------------------------------------------------


@mcp.tool(name="gmail_search_emails")
async def gmail_search_emails(
    query: Annotated[str, Field(description="Gmail search query (e.g. 'is:unread', 'from:alice@example.com')")],
    max_results: Annotated[int, Field(default=10, description="Maximum results to return per account (1-50)", ge=1, le=50)] = 10,
    account: Annotated[Optional[str], Field(description="Account label to search. Omit to search ALL accounts.")] = None,
) -> str:
    """Search emails using Gmail search syntax. Searches ALL accounts when no account is specified."""
    try:
        if _manager is None:
            raise RuntimeError("Server not initialized")

        if account is not None:
            # Single-account search
            svc = _get_service(account)
            resolved = _manager.resolve(account)
            results = gmail_client.search_emails(svc, query, max_results=max_results)
            return json.dumps(
                {
                    "account": resolved,
                    "email": _manager.get_email(resolved),
                    "query": query,
                    "result_count": len(results),
                    "results": results,
                },
                indent=2,
            )

        # Cross-account search: fan out to all accounts
        all_results = []
        for name in _manager.account_names:
            try:
                svc = _manager.get_service(name)
                results = gmail_client.search_emails(svc, query, max_results=max_results)
                for r in results:
                    r["_account"] = name
                    r["_email"] = _manager.get_email(name)
                all_results.extend(results)
            except Exception as acct_err:
                all_results.append({
                    "_account": name,
                    "_email": _manager.get_email(name),
                    "error": str(acct_err),
                })

        return json.dumps(
            {
                "query": query,
                "accounts_searched": _manager.account_names,
                "total_results": len([r for r in all_results if "error" not in r]),
                "results": all_results,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool(name="gmail_read_email")
async def gmail_read_email(
    message_id: Annotated[str, Field(description="Gmail message ID")],
    account: Annotated[Optional[str], Field(description="Account label to use (omit for active account)")] = None,
) -> str:
    """Read a full email message including body, headers, and attachment metadata."""
    try:
        svc = _get_service(account)
        resolved = _manager.resolve(account)
        result = gmail_client.read_email(svc, message_id)
        return json.dumps(
            {
                "account": resolved,
                "email": _manager.get_email(resolved),
                "result": result,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool(name="gmail_send_email")
async def gmail_send_email(
    to: Annotated[str, Field(description="Recipient email address")],
    subject: Annotated[str, Field(description="Email subject line")],
    body: Annotated[str, Field(description="Plain-text email body")],
    cc: Annotated[Optional[str], Field(description="CC recipients (comma-separated)")] = None,
    bcc: Annotated[Optional[str], Field(description="BCC recipients (comma-separated)")] = None,
    html_body: Annotated[Optional[str], Field(description="Optional HTML body (creates multipart/alternative)")] = None,
    mime_type: Annotated[str, Field(description="MIME type hint")] = "text/plain",
    attachments: Annotated[Optional[list[str]], Field(description="List of file paths to attach")] = None,
    in_reply_to: Annotated[Optional[str], Field(description="Message-ID of the message being replied to")] = None,
    thread_id: Annotated[Optional[str], Field(description="Thread ID for replies")] = None,
    account: Annotated[Optional[str], Field(description="Account label to use (omit for active account)")] = None,
) -> str:
    """Send an email. Supports plain text, HTML, attachments, and replies."""
    try:
        svc = _get_service(account)
        resolved = _manager.resolve(account)
        result = gmail_client.send_email(
            svc,
            to=to,
            subject=subject,
            body=body,
            cc=cc,
            bcc=bcc,
            html_body=html_body,
            mime_type=mime_type,
            attachments=attachments,
            in_reply_to=in_reply_to,
            thread_id=thread_id,
        )
        return json.dumps(
            {
                "account": resolved,
                "email": _manager.get_email(resolved),
                "result": result,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool(name="gmail_draft_email")
async def gmail_draft_email(
    to: Annotated[str, Field(description="Recipient email address")],
    subject: Annotated[str, Field(description="Email subject line")],
    body: Annotated[str, Field(description="Plain-text email body")],
    cc: Annotated[Optional[str], Field(description="CC recipients (comma-separated)")] = None,
    bcc: Annotated[Optional[str], Field(description="BCC recipients (comma-separated)")] = None,
    html_body: Annotated[Optional[str], Field(description="Optional HTML body")] = None,
    mime_type: Annotated[str, Field(description="MIME type hint")] = "text/plain",
    attachments: Annotated[Optional[list[str]], Field(description="List of file paths to attach")] = None,
    in_reply_to: Annotated[Optional[str], Field(description="Message-ID of the message being replied to")] = None,
    thread_id: Annotated[Optional[str], Field(description="Thread ID for replies")] = None,
    account: Annotated[Optional[str], Field(description="Account label to use (omit for active account)")] = None,
) -> str:
    """Create a draft email (not sent). Same parameters as gmail_send_email."""
    try:
        svc = _get_service(account)
        resolved = _manager.resolve(account)
        result = gmail_client.draft_email(
            svc,
            to=to,
            subject=subject,
            body=body,
            cc=cc,
            bcc=bcc,
            html_body=html_body,
            mime_type=mime_type,
            attachments=attachments,
            in_reply_to=in_reply_to,
            thread_id=thread_id,
        )
        return json.dumps(
            {
                "account": resolved,
                "email": _manager.get_email(resolved),
                "result": result,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool(name="gmail_delete_email")
async def gmail_delete_email(
    message_id: Annotated[str, Field(description="Gmail message ID to delete (moves to trash)")],
    account: Annotated[Optional[str], Field(description="Account label to use (omit for active account)")] = None,
) -> str:
    """Move an email to trash."""
    try:
        svc = _get_service(account)
        resolved = _manager.resolve(account)
        result = gmail_client.delete_email(svc, message_id)
        return json.dumps(
            {
                "account": resolved,
                "email": _manager.get_email(resolved),
                "result": result,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool(name="gmail_batch_delete_emails")
async def gmail_batch_delete_emails(
    message_ids: Annotated[list[str], Field(description="List of Gmail message IDs to delete")],
    batch_size: Annotated[int, Field(default=50, description="Number of messages per batch")] = 50,
    account: Annotated[Optional[str], Field(description="Account label to use (omit for active account)")] = None,
) -> str:
    """Trash multiple emails in batches."""
    try:
        svc = _get_service(account)
        resolved = _manager.resolve(account)
        result = gmail_client.batch_delete_emails(svc, message_ids, batch_size=batch_size)
        return json.dumps(
            {
                "account": resolved,
                "email": _manager.get_email(resolved),
                "result": result,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool(name="gmail_modify_email")
async def gmail_modify_email(
    message_id: Annotated[str, Field(description="Gmail message ID")],
    add_label_ids: Annotated[Optional[list[str]], Field(description="Label IDs to add")] = None,
    remove_label_ids: Annotated[Optional[list[str]], Field(description="Label IDs to remove")] = None,
    account: Annotated[Optional[str], Field(description="Account label to use (omit for active account)")] = None,
) -> str:
    """Modify labels on a single email message."""
    try:
        svc = _get_service(account)
        resolved = _manager.resolve(account)
        result = gmail_client.modify_email(
            svc,
            message_id,
            add_labels=add_label_ids,
            remove_labels=remove_label_ids,
        )
        return json.dumps(
            {
                "account": resolved,
                "email": _manager.get_email(resolved),
                "result": result,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool(name="gmail_batch_modify_emails")
async def gmail_batch_modify_emails(
    message_ids: Annotated[list[str], Field(description="List of Gmail message IDs to modify")],
    add_label_ids: Annotated[Optional[list[str]], Field(description="Label IDs to add")] = None,
    remove_label_ids: Annotated[Optional[list[str]], Field(description="Label IDs to remove")] = None,
    batch_size: Annotated[int, Field(default=50, description="Number of messages per batch")] = 50,
    account: Annotated[Optional[str], Field(description="Account label to use (omit for active account)")] = None,
) -> str:
    """Modify labels on multiple email messages in batches."""
    try:
        svc = _get_service(account)
        resolved = _manager.resolve(account)
        result = gmail_client.batch_modify_emails(
            svc,
            message_ids,
            add_labels=add_label_ids,
            remove_labels=remove_label_ids,
            batch_size=batch_size,
        )
        return json.dumps(
            {
                "account": resolved,
                "email": _manager.get_email(resolved),
                "result": result,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Label Tools
# ---------------------------------------------------------------------------


@mcp.tool(name="gmail_list_labels")
async def gmail_list_labels(
    account: Annotated[Optional[str], Field(description="Account label to use (omit for active account)")] = None,
) -> str:
    """List all Gmail labels for an account."""
    try:
        svc = _get_service(account)
        resolved = _manager.resolve(account)
        labels = gmail_client.list_labels(svc)
        return json.dumps(
            {
                "account": resolved,
                "email": _manager.get_email(resolved),
                "labels": labels,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool(name="gmail_create_label")
async def gmail_create_label(
    name: Annotated[str, Field(description="Label name")],
    label_list_visibility: Annotated[str, Field(description="Visibility in label list")] = "labelShow",
    message_list_visibility: Annotated[str, Field(description="Visibility in message list")] = "show",
    account: Annotated[Optional[str], Field(description="Account label to use (omit for active account)")] = None,
) -> str:
    """Create a new Gmail label."""
    try:
        svc = _get_service(account)
        resolved = _manager.resolve(account)
        result = gmail_client.create_label(
            svc,
            name,
            label_list_visibility=label_list_visibility,
            message_list_visibility=message_list_visibility,
        )
        return json.dumps(
            {
                "account": resolved,
                "email": _manager.get_email(resolved),
                "result": result,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool(name="gmail_update_label")
async def gmail_update_label(
    label_id: Annotated[str, Field(description="Label ID to update")],
    name: Annotated[Optional[str], Field(description="New label name")] = None,
    label_list_visibility: Annotated[Optional[str], Field(description="New visibility in label list")] = None,
    message_list_visibility: Annotated[Optional[str], Field(description="New visibility in message list")] = None,
    account: Annotated[Optional[str], Field(description="Account label to use (omit for active account)")] = None,
) -> str:
    """Update an existing Gmail label."""
    try:
        svc = _get_service(account)
        resolved = _manager.resolve(account)
        result = gmail_client.update_label(
            svc,
            label_id,
            name=name,
            label_list_visibility=label_list_visibility,
            message_list_visibility=message_list_visibility,
        )
        return json.dumps(
            {
                "account": resolved,
                "email": _manager.get_email(resolved),
                "result": result,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool(name="gmail_delete_label")
async def gmail_delete_label(
    label_id: Annotated[str, Field(description="Label ID to delete")],
    account: Annotated[Optional[str], Field(description="Account label to use (omit for active account)")] = None,
) -> str:
    """Delete a Gmail label."""
    try:
        svc = _get_service(account)
        resolved = _manager.resolve(account)
        result = gmail_client.delete_label(svc, label_id)
        return json.dumps(
            {
                "account": resolved,
                "email": _manager.get_email(resolved),
                "result": result,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Filter Tools
# ---------------------------------------------------------------------------


@mcp.tool(name="gmail_list_filters")
async def gmail_list_filters(
    account: Annotated[Optional[str], Field(description="Account label to use (omit for active account)")] = None,
) -> str:
    """List all Gmail filters for an account."""
    try:
        svc = _get_service(account)
        resolved = _manager.resolve(account)
        filters = gmail_client.list_filters(svc)
        return json.dumps(
            {
                "account": resolved,
                "email": _manager.get_email(resolved),
                "filters": filters,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool(name="gmail_get_filter")
async def gmail_get_filter(
    filter_id: Annotated[str, Field(description="Filter ID to retrieve")],
    account: Annotated[Optional[str], Field(description="Account label to use (omit for active account)")] = None,
) -> str:
    """Get details of a specific Gmail filter."""
    try:
        svc = _get_service(account)
        resolved = _manager.resolve(account)
        result = gmail_client.get_filter(svc, filter_id)
        return json.dumps(
            {
                "account": resolved,
                "email": _manager.get_email(resolved),
                "result": result,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool(name="gmail_create_filter")
async def gmail_create_filter(
    criteria: Annotated[dict, Field(description="Filter criteria (e.g. {\"from\": \"user@example.com\"})")],
    action: Annotated[dict, Field(description="Filter action (e.g. {\"addLabelIds\": [\"Label_1\"]})")],
    account: Annotated[Optional[str], Field(description="Account label to use (omit for active account)")] = None,
) -> str:
    """Create a new Gmail filter with given criteria and action."""
    try:
        svc = _get_service(account)
        resolved = _manager.resolve(account)
        result = gmail_client.create_filter(svc, criteria, action)
        return json.dumps(
            {
                "account": resolved,
                "email": _manager.get_email(resolved),
                "result": result,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool(name="gmail_delete_filter")
async def gmail_delete_filter(
    filter_id: Annotated[str, Field(description="Filter ID to delete")],
    account: Annotated[Optional[str], Field(description="Account label to use (omit for active account)")] = None,
) -> str:
    """Delete a Gmail filter."""
    try:
        svc = _get_service(account)
        resolved = _manager.resolve(account)
        result = gmail_client.delete_filter(svc, filter_id)
        return json.dumps(
            {
                "account": resolved,
                "email": _manager.get_email(resolved),
                "result": result,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Attachment Tools
# ---------------------------------------------------------------------------


@mcp.tool(name="gmail_download_attachment")
async def gmail_download_attachment(
    message_id: Annotated[str, Field(description="Gmail message ID containing the attachment")],
    attachment_id: Annotated[str, Field(description="Attachment ID to download")],
    save_path: Annotated[str, Field(description="Directory to save the file to")] = ".",
    filename: Annotated[Optional[str], Field(description="Filename to use (auto-generated if omitted)")] = None,
    account: Annotated[Optional[str], Field(description="Account label to use (omit for active account)")] = None,
) -> str:
    """Download an email attachment and save it to disk."""
    try:
        svc = _get_service(account)
        resolved = _manager.resolve(account)
        result = gmail_client.download_attachment(
            svc,
            message_id,
            attachment_id,
            save_path=save_path,
            filename=filename,
        )
        return json.dumps(
            {
                "account": resolved,
                "email": _manager.get_email(resolved),
                "result": result,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    """Entry point: routes 'auth' subcommand or starts the MCP server."""
    if len(sys.argv) > 1 and sys.argv[1] == "auth":
        from .auth import run_auth

        run_auth(sys.argv[2:])
    else:
        mcp.run()
