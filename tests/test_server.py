"""Tests for the FastMCP server with multi-account Gmail tools."""

import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from gmail_multi_mcp.accounts import AccountNotFoundError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_manager():
    """Create a mock AccountManager with two accounts."""
    mgr = MagicMock()
    mgr.account_names = ["work", "personal"]
    mgr.active_account = "work"
    mgr.list_accounts_info.return_value = [
        {"name": "work", "email": "work@example.com", "active": True},
        {"name": "personal", "email": "personal@gmail.com", "active": False},
    ]
    mgr.get_email.side_effect = lambda name: {
        "work": "work@example.com",
        "personal": "personal@gmail.com",
    }[name]
    mgr.resolve.side_effect = lambda account: account or "work"
    mgr.get_service.return_value = MagicMock()
    return mgr


# ---------------------------------------------------------------------------
# Account Tools
# ---------------------------------------------------------------------------


class TestGmailListAccounts:
    @pytest.mark.asyncio
    async def test_list_accounts_returns_all(self):
        from gmail_multi_mcp.server import gmail_list_accounts

        mgr = _make_mock_manager()
        with patch("gmail_multi_mcp.server._manager", mgr):
            result = await gmail_list_accounts()
            data = json.loads(result)
            assert data["active"] == "work"
            assert len(data["accounts"]) == 2
            assert data["accounts"][0]["name"] == "work"
            assert data["accounts"][0]["active"] is True

    @pytest.mark.asyncio
    async def test_list_accounts_when_not_initialized(self):
        from gmail_multi_mcp.server import gmail_list_accounts

        with patch("gmail_multi_mcp.server._manager", None):
            result = await gmail_list_accounts()
            data = json.loads(result)
            assert "error" in data


class TestGmailSwitchAccount:
    @pytest.mark.asyncio
    async def test_switch_account_valid(self):
        from gmail_multi_mcp.server import gmail_switch_account

        mgr = _make_mock_manager()
        with patch("gmail_multi_mcp.server._manager", mgr):
            result = await gmail_switch_account(account="personal")
            data = json.loads(result)
            assert data["switched_to"] == "personal"
            mgr.switch.assert_called_once_with("personal")

    @pytest.mark.asyncio
    async def test_switch_account_invalid(self):
        from gmail_multi_mcp.server import gmail_switch_account

        mgr = _make_mock_manager()
        mgr.switch.side_effect = AccountNotFoundError("Account 'missing' not found")
        with patch("gmail_multi_mcp.server._manager", mgr):
            result = await gmail_switch_account(account="missing")
            data = json.loads(result)
            assert "error" in data
            assert "missing" in data["error"]

    @pytest.mark.asyncio
    async def test_switch_account_not_initialized(self):
        from gmail_multi_mcp.server import gmail_switch_account

        with patch("gmail_multi_mcp.server._manager", None):
            result = await gmail_switch_account(account="work")
            data = json.loads(result)
            assert "error" in data


class TestGmailCurrentAccount:
    @pytest.mark.asyncio
    async def test_current_account(self):
        from gmail_multi_mcp.server import gmail_current_account

        mgr = _make_mock_manager()
        with patch("gmail_multi_mcp.server._manager", mgr):
            result = await gmail_current_account()
            data = json.loads(result)
            assert data["account"] == "work"
            assert data["email"] == "work@example.com"

    @pytest.mark.asyncio
    async def test_current_account_none_active(self):
        from gmail_multi_mcp.server import gmail_current_account

        mgr = _make_mock_manager()
        mgr.active_account = None
        with patch("gmail_multi_mcp.server._manager", mgr):
            result = await gmail_current_account()
            data = json.loads(result)
            assert data["account"] is None

    @pytest.mark.asyncio
    async def test_current_account_not_initialized(self):
        from gmail_multi_mcp.server import gmail_current_account

        with patch("gmail_multi_mcp.server._manager", None):
            result = await gmail_current_account()
            data = json.loads(result)
            assert "error" in data


# ---------------------------------------------------------------------------
# Email Tools
# ---------------------------------------------------------------------------


class TestGmailSearchEmails:
    @pytest.mark.asyncio
    async def test_search_emails_cross_account(self):
        """When account is omitted, search fans out to ALL accounts."""
        from gmail_multi_mcp.server import gmail_search_emails

        mgr = _make_mock_manager()
        work_results = [{"id": "msg1", "subject": "Test"}]
        personal_results = [{"id": "msg2", "subject": "Other"}]

        def search_by_account(svc, query, max_results=10):
            # Return different results based on which service mock was passed
            if svc == work_svc:
                return work_results
            return personal_results

        work_svc = MagicMock()
        personal_svc = MagicMock()
        mgr.get_service.side_effect = lambda name: {"work": work_svc, "personal": personal_svc}[name]

        with (
            patch("gmail_multi_mcp.server._manager", mgr),
            patch("gmail_multi_mcp.server.gmail_client.search_emails", side_effect=search_by_account) as mock_search,
        ):
            result = await gmail_search_emails(query="is:unread", max_results=5)
            data = json.loads(result)
            assert data["accounts_searched"] == ["work", "personal"]
            assert data["total_results"] == 2
            assert len(data["results"]) == 2
            # Results should have _account metadata
            assert data["results"][0]["_account"] == "work"
            assert data["results"][1]["_account"] == "personal"
            assert mock_search.call_count == 2

    @pytest.mark.asyncio
    async def test_search_emails_with_account(self):
        """When account is specified, search only that account."""
        from gmail_multi_mcp.server import gmail_search_emails

        mgr = _make_mock_manager()
        mgr.resolve.side_effect = lambda a: a or "work"
        with (
            patch("gmail_multi_mcp.server._manager", mgr),
            patch("gmail_multi_mcp.server.gmail_client.search_emails", return_value=[]) as mock_search,
        ):
            result = await gmail_search_emails(query="test", account="personal")
            data = json.loads(result)
            assert data["account"] == "personal"
            mgr.get_service.assert_called_once_with("personal")

    @pytest.mark.asyncio
    async def test_search_emails_cross_account_partial_error(self):
        """Cross-account search includes errors per account without failing overall."""
        from gmail_multi_mcp.server import gmail_search_emails

        mgr = _make_mock_manager()

        def get_service_with_error(name):
            if name == "personal":
                raise RuntimeError("Auth expired")
            return MagicMock()

        mgr.get_service.side_effect = get_service_with_error

        with (
            patch("gmail_multi_mcp.server._manager", mgr),
            patch("gmail_multi_mcp.server.gmail_client.search_emails", return_value=[{"id": "msg1"}]),
        ):
            result = await gmail_search_emails(query="test")
            data = json.loads(result)
            assert data["accounts_searched"] == ["work", "personal"]
            # work succeeds, personal errors
            assert data["total_results"] == 1
            assert any("error" in r for r in data["results"])


class TestGmailReadEmail:
    @pytest.mark.asyncio
    async def test_read_email_delegates(self):
        from gmail_multi_mcp.server import gmail_read_email

        mgr = _make_mock_manager()
        mock_msg = {"id": "msg1", "subject": "Test", "body": "Hello"}
        with (
            patch("gmail_multi_mcp.server._manager", mgr),
            patch("gmail_multi_mcp.server.gmail_client.read_email", return_value=mock_msg) as mock_read,
        ):
            result = await gmail_read_email(message_id="msg1")
            data = json.loads(result)
            assert data["account"] == "work"
            assert data["result"]["id"] == "msg1"
            mock_read.assert_called_once_with(mgr.get_service.return_value, "msg1")

    @pytest.mark.asyncio
    async def test_read_email_error(self):
        from gmail_multi_mcp.server import gmail_read_email

        mgr = _make_mock_manager()
        mgr.get_service.side_effect = Exception("API error")
        with patch("gmail_multi_mcp.server._manager", mgr):
            result = await gmail_read_email(message_id="msg1")
            data = json.loads(result)
            assert "error" in data


class TestGmailSendEmail:
    @pytest.mark.asyncio
    async def test_send_email_delegates(self):
        from gmail_multi_mcp.server import gmail_send_email

        mgr = _make_mock_manager()
        mock_resp = {"id": "sent1", "labelIds": ["SENT"]}
        with (
            patch("gmail_multi_mcp.server._manager", mgr),
            patch("gmail_multi_mcp.server.gmail_client.send_email", return_value=mock_resp) as mock_send,
        ):
            result = await gmail_send_email(
                to="bob@example.com", subject="Hi", body="Hello"
            )
            data = json.loads(result)
            assert data["account"] == "work"
            assert data["result"]["id"] == "sent1"
            mock_send.assert_called_once_with(
                mgr.get_service.return_value,
                to="bob@example.com",
                subject="Hi",
                body="Hello",
                cc=None,
                bcc=None,
                html_body=None,
                mime_type="text/plain",
                attachments=None,
                in_reply_to=None,
                thread_id=None,
            )

    @pytest.mark.asyncio
    async def test_send_email_with_all_params(self):
        from gmail_multi_mcp.server import gmail_send_email

        mgr = _make_mock_manager()
        mock_resp = {"id": "sent2"}
        with (
            patch("gmail_multi_mcp.server._manager", mgr),
            patch("gmail_multi_mcp.server.gmail_client.send_email", return_value=mock_resp) as mock_send,
        ):
            result = await gmail_send_email(
                to="bob@example.com",
                subject="Re: Hi",
                body="Reply",
                cc="carol@example.com",
                bcc="dave@example.com",
                html_body="<p>Reply</p>",
                in_reply_to="<orig@example.com>",
                thread_id="t1",
                account="personal",
            )
            data = json.loads(result)
            assert data["account"] == "personal"
            mock_send.assert_called_once()


class TestGmailDraftEmail:
    @pytest.mark.asyncio
    async def test_draft_email_delegates(self):
        from gmail_multi_mcp.server import gmail_draft_email

        mgr = _make_mock_manager()
        mock_resp = {"id": "draft1", "message": {"id": "msg1"}}
        with (
            patch("gmail_multi_mcp.server._manager", mgr),
            patch("gmail_multi_mcp.server.gmail_client.draft_email", return_value=mock_resp) as mock_draft,
        ):
            result = await gmail_draft_email(
                to="bob@example.com", subject="Draft", body="Body"
            )
            data = json.loads(result)
            assert data["account"] == "work"
            assert data["result"]["id"] == "draft1"
            mock_draft.assert_called_once()


class TestGmailDeleteEmail:
    @pytest.mark.asyncio
    async def test_delete_email_delegates(self):
        from gmail_multi_mcp.server import gmail_delete_email

        mgr = _make_mock_manager()
        mock_resp = {"id": "msg1", "labelIds": ["TRASH"]}
        with (
            patch("gmail_multi_mcp.server._manager", mgr),
            patch("gmail_multi_mcp.server.gmail_client.delete_email", return_value=mock_resp) as mock_del,
        ):
            result = await gmail_delete_email(message_id="msg1")
            data = json.loads(result)
            assert data["account"] == "work"
            assert data["result"]["id"] == "msg1"
            mock_del.assert_called_once_with(mgr.get_service.return_value, "msg1")


class TestGmailBatchDeleteEmails:
    @pytest.mark.asyncio
    async def test_batch_delete_delegates(self):
        from gmail_multi_mcp.server import gmail_batch_delete_emails

        mgr = _make_mock_manager()
        mock_resp = {"deleted": ["msg1", "msg2"], "errors": []}
        with (
            patch("gmail_multi_mcp.server._manager", mgr),
            patch("gmail_multi_mcp.server.gmail_client.batch_delete_emails", return_value=mock_resp) as mock_batch,
        ):
            result = await gmail_batch_delete_emails(message_ids=["msg1", "msg2"])
            data = json.loads(result)
            assert data["account"] == "work"
            assert data["result"]["deleted"] == ["msg1", "msg2"]
            mock_batch.assert_called_once_with(
                mgr.get_service.return_value, ["msg1", "msg2"], batch_size=50
            )


class TestGmailModifyEmail:
    @pytest.mark.asyncio
    async def test_modify_email_delegates(self):
        from gmail_multi_mcp.server import gmail_modify_email

        mgr = _make_mock_manager()
        mock_resp = {"id": "msg1", "labelIds": ["INBOX", "STARRED"]}
        with (
            patch("gmail_multi_mcp.server._manager", mgr),
            patch("gmail_multi_mcp.server.gmail_client.modify_email", return_value=mock_resp) as mock_mod,
        ):
            result = await gmail_modify_email(
                message_id="msg1", add_label_ids=["STARRED"]
            )
            data = json.loads(result)
            assert data["account"] == "work"
            assert data["result"]["id"] == "msg1"
            mock_mod.assert_called_once_with(
                mgr.get_service.return_value,
                "msg1",
                add_labels=["STARRED"],
                remove_labels=None,
            )


class TestGmailBatchModifyEmails:
    @pytest.mark.asyncio
    async def test_batch_modify_delegates(self):
        from gmail_multi_mcp.server import gmail_batch_modify_emails

        mgr = _make_mock_manager()
        mock_resp = {"modified": [{"id": "msg1"}], "errors": []}
        with (
            patch("gmail_multi_mcp.server._manager", mgr),
            patch("gmail_multi_mcp.server.gmail_client.batch_modify_emails", return_value=mock_resp) as mock_batch,
        ):
            result = await gmail_batch_modify_emails(
                message_ids=["msg1"],
                add_label_ids=["STARRED"],
                remove_label_ids=["UNREAD"],
            )
            data = json.loads(result)
            assert data["account"] == "work"
            mock_batch.assert_called_once_with(
                mgr.get_service.return_value,
                ["msg1"],
                add_labels=["STARRED"],
                remove_labels=["UNREAD"],
                batch_size=50,
            )


class TestGmailListLabels:
    @pytest.mark.asyncio
    async def test_list_labels_delegates(self):
        from gmail_multi_mcp.server import gmail_list_labels

        mgr = _make_mock_manager()
        mock_labels = [{"id": "INBOX", "name": "INBOX"}]
        with (
            patch("gmail_multi_mcp.server._manager", mgr),
            patch("gmail_multi_mcp.server.gmail_client.list_labels", return_value=mock_labels) as mock_list,
        ):
            result = await gmail_list_labels()
            data = json.loads(result)
            assert data["account"] == "work"
            assert data["labels"] == mock_labels
            mock_list.assert_called_once_with(mgr.get_service.return_value)


class TestGmailCreateLabel:
    @pytest.mark.asyncio
    async def test_create_label_delegates(self):
        from gmail_multi_mcp.server import gmail_create_label

        mgr = _make_mock_manager()
        mock_label = {"id": "Label_1", "name": "Custom"}
        with (
            patch("gmail_multi_mcp.server._manager", mgr),
            patch("gmail_multi_mcp.server.gmail_client.create_label", return_value=mock_label) as mock_create,
        ):
            result = await gmail_create_label(name="Custom")
            data = json.loads(result)
            assert data["account"] == "work"
            assert data["result"]["id"] == "Label_1"
            mock_create.assert_called_once_with(
                mgr.get_service.return_value,
                "Custom",
                label_list_visibility="labelShow",
                message_list_visibility="show",
            )


class TestGmailUpdateLabel:
    @pytest.mark.asyncio
    async def test_update_label_delegates(self):
        from gmail_multi_mcp.server import gmail_update_label

        mgr = _make_mock_manager()
        mock_label = {"id": "Label_1", "name": "Renamed"}
        with (
            patch("gmail_multi_mcp.server._manager", mgr),
            patch("gmail_multi_mcp.server.gmail_client.update_label", return_value=mock_label) as mock_update,
        ):
            result = await gmail_update_label(label_id="Label_1", name="Renamed")
            data = json.loads(result)
            assert data["account"] == "work"
            assert data["result"]["name"] == "Renamed"
            mock_update.assert_called_once_with(
                mgr.get_service.return_value,
                "Label_1",
                name="Renamed",
                label_list_visibility=None,
                message_list_visibility=None,
            )


class TestGmailDeleteLabel:
    @pytest.mark.asyncio
    async def test_delete_label_delegates(self):
        from gmail_multi_mcp.server import gmail_delete_label

        mgr = _make_mock_manager()
        mock_resp = {"deleted": True, "label_id": "Label_1"}
        with (
            patch("gmail_multi_mcp.server._manager", mgr),
            patch("gmail_multi_mcp.server.gmail_client.delete_label", return_value=mock_resp) as mock_del,
        ):
            result = await gmail_delete_label(label_id="Label_1")
            data = json.loads(result)
            assert data["account"] == "work"
            assert data["result"]["deleted"] is True
            mock_del.assert_called_once_with(mgr.get_service.return_value, "Label_1")


class TestGmailListFilters:
    @pytest.mark.asyncio
    async def test_list_filters_delegates(self):
        from gmail_multi_mcp.server import gmail_list_filters

        mgr = _make_mock_manager()
        mock_filters = [{"id": "f1", "criteria": {}, "action": {}}]
        with (
            patch("gmail_multi_mcp.server._manager", mgr),
            patch("gmail_multi_mcp.server.gmail_client.list_filters", return_value=mock_filters) as mock_list,
        ):
            result = await gmail_list_filters()
            data = json.loads(result)
            assert data["account"] == "work"
            assert data["filters"] == mock_filters
            mock_list.assert_called_once_with(mgr.get_service.return_value)


class TestGmailGetFilter:
    @pytest.mark.asyncio
    async def test_get_filter_delegates(self):
        from gmail_multi_mcp.server import gmail_get_filter

        mgr = _make_mock_manager()
        mock_filter = {"id": "f1", "criteria": {"from": "a@b.com"}, "action": {}}
        with (
            patch("gmail_multi_mcp.server._manager", mgr),
            patch("gmail_multi_mcp.server.gmail_client.get_filter", return_value=mock_filter) as mock_get,
        ):
            result = await gmail_get_filter(filter_id="f1")
            data = json.loads(result)
            assert data["account"] == "work"
            assert data["result"]["id"] == "f1"
            mock_get.assert_called_once_with(mgr.get_service.return_value, "f1")


class TestGmailCreateFilter:
    @pytest.mark.asyncio
    async def test_create_filter_delegates(self):
        from gmail_multi_mcp.server import gmail_create_filter

        mgr = _make_mock_manager()
        criteria = {"from": "news@example.com"}
        action = {"addLabelIds": ["Label_1"]}
        mock_filter = {"id": "f2", "criteria": criteria, "action": action}
        with (
            patch("gmail_multi_mcp.server._manager", mgr),
            patch("gmail_multi_mcp.server.gmail_client.create_filter", return_value=mock_filter) as mock_create,
        ):
            result = await gmail_create_filter(criteria=criteria, action=action)
            data = json.loads(result)
            assert data["account"] == "work"
            assert data["result"]["id"] == "f2"
            mock_create.assert_called_once_with(
                mgr.get_service.return_value, criteria, action
            )


class TestGmailDeleteFilter:
    @pytest.mark.asyncio
    async def test_delete_filter_delegates(self):
        from gmail_multi_mcp.server import gmail_delete_filter

        mgr = _make_mock_manager()
        mock_resp = {"deleted": True, "filter_id": "f1"}
        with (
            patch("gmail_multi_mcp.server._manager", mgr),
            patch("gmail_multi_mcp.server.gmail_client.delete_filter", return_value=mock_resp) as mock_del,
        ):
            result = await gmail_delete_filter(filter_id="f1")
            data = json.loads(result)
            assert data["account"] == "work"
            assert data["result"]["deleted"] is True
            mock_del.assert_called_once_with(mgr.get_service.return_value, "f1")


class TestGmailDownloadAttachment:
    @pytest.mark.asyncio
    async def test_download_attachment_delegates(self):
        from gmail_multi_mcp.server import gmail_download_attachment

        mgr = _make_mock_manager()
        mock_resp = {"filename": "report.pdf", "path": "/tmp/report.pdf", "size": 1024}
        with (
            patch("gmail_multi_mcp.server._manager", mgr),
            patch("gmail_multi_mcp.server.gmail_client.download_attachment", return_value=mock_resp) as mock_dl,
        ):
            result = await gmail_download_attachment(
                message_id="msg1", attachment_id="att1", save_path="/tmp", filename="report.pdf"
            )
            data = json.loads(result)
            assert data["account"] == "work"
            assert data["result"]["filename"] == "report.pdf"
            mock_dl.assert_called_once_with(
                mgr.get_service.return_value,
                "msg1",
                "att1",
                save_path="/tmp",
                filename="report.pdf",
            )


# ---------------------------------------------------------------------------
# Error Handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_all_email_tools_return_json_error_on_exception(self):
        """Every email tool should catch exceptions and return JSON with 'error' key."""
        from gmail_multi_mcp import server

        mgr = _make_mock_manager()
        mgr.get_service.side_effect = RuntimeError("Service failed")

        tool_calls = [
            (server.gmail_search_emails, {"query": "test", "account": "work"}),
            (server.gmail_read_email, {"message_id": "msg1"}),
            (server.gmail_send_email, {"to": "a@b.com", "subject": "s", "body": "b"}),
            (server.gmail_draft_email, {"to": "a@b.com", "subject": "s", "body": "b"}),
            (server.gmail_delete_email, {"message_id": "msg1"}),
            (server.gmail_batch_delete_emails, {"message_ids": ["msg1"]}),
            (server.gmail_modify_email, {"message_id": "msg1"}),
            (server.gmail_batch_modify_emails, {"message_ids": ["msg1"]}),
            (server.gmail_list_labels, {}),
            (server.gmail_create_label, {"name": "Test"}),
            (server.gmail_update_label, {"label_id": "L1"}),
            (server.gmail_delete_label, {"label_id": "L1"}),
            (server.gmail_list_filters, {}),
            (server.gmail_get_filter, {"filter_id": "f1"}),
            (server.gmail_create_filter, {"criteria": {}, "action": {}}),
            (server.gmail_delete_filter, {"filter_id": "f1"}),
            (server.gmail_download_attachment, {"message_id": "msg1", "attachment_id": "att1"}),
        ]

        with patch("gmail_multi_mcp.server._manager", mgr):
            for tool_fn, kwargs in tool_calls:
                result = await tool_fn(**kwargs)
                data = json.loads(result)
                assert "error" in data, f"{tool_fn.__name__} did not return error JSON"


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------


class TestMain:
    def test_main_calls_mcp_run(self):
        from gmail_multi_mcp.server import main

        with patch("gmail_multi_mcp.server.mcp") as mock_mcp:
            with patch("gmail_multi_mcp.server.sys") as mock_sys:
                mock_sys.argv = ["gmail-multi-mcp"]
                main()
                mock_mcp.run.assert_called_once()

    def test_main_routes_auth_subcommand(self):
        from gmail_multi_mcp.server import main

        with patch("gmail_multi_mcp.server.sys") as mock_sys:
            mock_sys.argv = ["gmail-multi-mcp", "auth", "add", "work"]
            with patch("gmail_multi_mcp.server.mcp") as mock_mcp:
                # auth module doesn't exist yet, so we mock the import
                with patch.dict("sys.modules", {"gmail_multi_mcp.auth": MagicMock()}) as mock_modules:
                    import sys
                    mock_auth_module = sys.modules["gmail_multi_mcp.auth"]
                    main()
                    mock_auth_module.run_auth.assert_called_once_with(["add", "work"])
                    mock_mcp.run.assert_not_called()
