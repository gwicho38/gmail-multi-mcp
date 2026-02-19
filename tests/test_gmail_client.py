"""Tests for Gmail API wrapper functions."""

import base64
import pytest
from unittest.mock import MagicMock

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
    _build_message,
    _extract_body,
    _extract_attachments,
)


def _mock_service():
    """Create a mock Gmail API service with proper chaining."""
    svc = MagicMock()
    return svc


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

class TestSearch:
    def test_search_returns_messages(self):
        svc = _mock_service()
        svc.users().messages().list().execute.return_value = {
            "messages": [
                {"id": "msg1", "threadId": "t1"},
                {"id": "msg2", "threadId": "t2"},
            ],
            "resultSizeEstimate": 2,
        }
        # Mock the individual message gets
        svc.users().messages().get().execute.side_effect = [
            {
                "id": "msg1",
                "threadId": "t1",
                "snippet": "Hello world",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "alice@example.com"},
                        {"name": "To", "value": "bob@example.com"},
                        {"name": "Subject", "value": "Test Subject"},
                        {"name": "Date", "value": "Mon, 1 Jan 2024 00:00:00 +0000"},
                    ]
                },
                "labelIds": ["INBOX"],
            },
            {
                "id": "msg2",
                "threadId": "t2",
                "snippet": "Goodbye world",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "carol@example.com"},
                        {"name": "To", "value": "dave@example.com"},
                        {"name": "Subject", "value": "Another Subject"},
                        {"name": "Date", "value": "Tue, 2 Jan 2024 00:00:00 +0000"},
                    ]
                },
                "labelIds": ["INBOX", "UNREAD"],
            },
        ]

        results = search_emails(svc, "is:unread", max_results=10)
        assert len(results) == 2
        assert results[0]["id"] == "msg1"
        assert results[0]["subject"] == "Test Subject"
        assert results[0]["from"] == "alice@example.com"
        assert results[1]["id"] == "msg2"

    def test_search_handles_empty_results(self):
        svc = _mock_service()
        svc.users().messages().list().execute.return_value = {
            "resultSizeEstimate": 0,
        }
        results = search_emails(svc, "nonexistent query")
        assert results == []

    def test_search_respects_max_results(self):
        svc = _mock_service()
        svc.users().messages().list().execute.return_value = {
            "messages": [{"id": "msg1", "threadId": "t1"}],
            "resultSizeEstimate": 1,
        }
        svc.users().messages().get().execute.return_value = {
            "id": "msg1",
            "threadId": "t1",
            "snippet": "Hello",
            "payload": {"headers": []},
            "labelIds": [],
        }
        search_emails(svc, "test", max_results=5)
        # Verify maxResults was passed to the list call
        svc.users().messages().list.assert_called_with(
            userId="me", q="test", maxResults=5
        )


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

class TestRead:
    def test_read_email_returns_message_details(self):
        svc = _mock_service()
        body_data = base64.urlsafe_b64encode(b"Hello body text").decode()
        svc.users().messages().get().execute.return_value = {
            "id": "msg1",
            "threadId": "t1",
            "snippet": "Hello body...",
            "payload": {
                "mimeType": "text/plain",
                "headers": [
                    {"name": "From", "value": "alice@example.com"},
                    {"name": "To", "value": "bob@example.com"},
                    {"name": "Subject", "value": "Test Subject"},
                    {"name": "Date", "value": "Mon, 1 Jan 2024 00:00:00 +0000"},
                    {"name": "Message-ID", "value": "<abc@example.com>"},
                ],
                "body": {"size": 15, "data": body_data},
            },
            "labelIds": ["INBOX", "UNREAD"],
        }

        result = read_email(svc, "msg1")
        assert result["id"] == "msg1"
        assert result["subject"] == "Test Subject"
        assert result["from"] == "alice@example.com"
        assert result["body"] == "Hello body text"
        assert result["labels"] == ["INBOX", "UNREAD"]

    def test_read_email_handles_multipart(self):
        svc = _mock_service()
        body_data = base64.urlsafe_b64encode(b"Multipart body").decode()
        svc.users().messages().get().execute.return_value = {
            "id": "msg2",
            "threadId": "t2",
            "snippet": "Multipart...",
            "payload": {
                "mimeType": "multipart/alternative",
                "headers": [
                    {"name": "From", "value": "sender@example.com"},
                    {"name": "To", "value": "receiver@example.com"},
                    {"name": "Subject", "value": "Multipart Test"},
                    {"name": "Date", "value": "Wed, 3 Jan 2024 00:00:00 +0000"},
                ],
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "body": {"size": 14, "data": body_data},
                    },
                    {
                        "mimeType": "text/html",
                        "body": {
                            "size": 30,
                            "data": base64.urlsafe_b64encode(
                                b"<p>Multipart body</p>"
                            ).decode(),
                        },
                    },
                ],
            },
            "labelIds": ["INBOX"],
        }

        result = read_email(svc, "msg2")
        assert result["body"] == "Multipart body"

    def test_read_email_extracts_attachments_metadata(self):
        svc = _mock_service()
        svc.users().messages().get().execute.return_value = {
            "id": "msg3",
            "threadId": "t3",
            "snippet": "With attachment",
            "payload": {
                "mimeType": "multipart/mixed",
                "headers": [
                    {"name": "From", "value": "sender@example.com"},
                    {"name": "Subject", "value": "Attachment Test"},
                ],
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "body": {
                            "size": 5,
                            "data": base64.urlsafe_b64encode(b"Hello").decode(),
                        },
                    },
                    {
                        "mimeType": "application/pdf",
                        "filename": "report.pdf",
                        "body": {"size": 1024, "attachmentId": "att1"},
                    },
                ],
            },
            "labelIds": ["INBOX"],
        }

        result = read_email(svc, "msg3")
        assert len(result["attachments"]) == 1
        assert result["attachments"][0]["filename"] == "report.pdf"
        assert result["attachments"][0]["attachment_id"] == "att1"
        assert result["attachments"][0]["size"] == 1024


# ---------------------------------------------------------------------------
# Send
# ---------------------------------------------------------------------------

class TestSend:
    def test_send_email_builds_and_sends(self):
        svc = _mock_service()
        svc.users().messages().send().execute.return_value = {
            "id": "sent1",
            "threadId": "t1",
            "labelIds": ["SENT"],
        }

        result = send_email(
            svc, to="bob@example.com", subject="Hi", body="Hello Bob"
        )
        assert result["id"] == "sent1"
        svc.users().messages().send.assert_called()

    def test_send_email_with_cc_bcc(self):
        svc = _mock_service()
        svc.users().messages().send().execute.return_value = {
            "id": "sent2",
            "threadId": "t2",
            "labelIds": ["SENT"],
        }

        result = send_email(
            svc,
            to="bob@example.com",
            subject="Hi",
            body="Hello Bob",
            cc="carol@example.com",
            bcc="dave@example.com",
        )
        assert result["id"] == "sent2"

    def test_send_email_as_reply(self):
        svc = _mock_service()
        svc.users().messages().send().execute.return_value = {
            "id": "sent3",
            "threadId": "original-thread",
            "labelIds": ["SENT"],
        }

        result = send_email(
            svc,
            to="bob@example.com",
            subject="Re: Hi",
            body="Reply text",
            in_reply_to="<original@example.com>",
            thread_id="original-thread",
        )
        assert result["id"] == "sent3"
        # Verify the send call includes threadId
        call_kwargs = svc.users().messages().send.call_args
        raw_body = call_kwargs[1]["body"] if call_kwargs[1] else call_kwargs[0][0]
        assert raw_body.get("threadId") == "original-thread" or "threadId" in str(call_kwargs)

    def test_send_email_with_html(self):
        svc = _mock_service()
        svc.users().messages().send().execute.return_value = {
            "id": "sent4",
            "threadId": "t4",
            "labelIds": ["SENT"],
        }

        result = send_email(
            svc,
            to="bob@example.com",
            subject="HTML Email",
            body="Plain version",
            html_body="<p>HTML version</p>",
        )
        assert result["id"] == "sent4"


# ---------------------------------------------------------------------------
# Draft
# ---------------------------------------------------------------------------

class TestDraft:
    def test_draft_email_creates_draft(self):
        svc = _mock_service()
        svc.users().drafts().create().execute.return_value = {
            "id": "draft1",
            "message": {"id": "msg1", "threadId": "t1"},
        }

        result = draft_email(
            svc, to="bob@example.com", subject="Draft subject", body="Draft body"
        )
        assert result["id"] == "draft1"
        svc.users().drafts().create.assert_called()


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

class TestDelete:
    def test_delete_email_trashes(self):
        svc = _mock_service()
        svc.users().messages().trash().execute.return_value = {
            "id": "msg1",
            "labelIds": ["TRASH"],
        }

        result = delete_email(svc, "msg1")
        assert result["id"] == "msg1"
        svc.users().messages().trash.assert_called_with(userId="me", id="msg1")


# ---------------------------------------------------------------------------
# Batch Delete
# ---------------------------------------------------------------------------

class TestBatchDelete:
    def test_batch_delete_trashes_multiple(self):
        svc = _mock_service()
        svc.users().messages().trash().execute.side_effect = [
            {"id": "msg1", "labelIds": ["TRASH"]},
            {"id": "msg2", "labelIds": ["TRASH"]},
            {"id": "msg3", "labelIds": ["TRASH"]},
        ]

        result = batch_delete_emails(svc, ["msg1", "msg2", "msg3"])
        assert len(result["deleted"]) == 3
        assert result["deleted"] == ["msg1", "msg2", "msg3"]

    def test_batch_delete_handles_errors(self):
        svc = _mock_service()
        svc.users().messages().trash().execute.side_effect = [
            {"id": "msg1", "labelIds": ["TRASH"]},
            Exception("Not found"),
            {"id": "msg3", "labelIds": ["TRASH"]},
        ]

        result = batch_delete_emails(svc, ["msg1", "msg2", "msg3"])
        assert len(result["deleted"]) == 2
        assert len(result["errors"]) == 1
        assert "msg2" in result["errors"][0]["message_id"]

    def test_batch_delete_empty_list(self):
        svc = _mock_service()
        result = batch_delete_emails(svc, [])
        assert result["deleted"] == []
        assert result["errors"] == []


# ---------------------------------------------------------------------------
# Modify
# ---------------------------------------------------------------------------

class TestModify:
    def test_modify_email_adds_labels(self):
        svc = _mock_service()
        svc.users().messages().modify().execute.return_value = {
            "id": "msg1",
            "labelIds": ["INBOX", "IMPORTANT"],
        }

        result = modify_email(svc, "msg1", add_labels=["IMPORTANT"])
        assert result["id"] == "msg1"
        assert "IMPORTANT" in result["labelIds"]
        svc.users().messages().modify.assert_called_with(
            userId="me",
            id="msg1",
            body={"addLabelIds": ["IMPORTANT"], "removeLabelIds": []},
        )

    def test_modify_email_removes_labels(self):
        svc = _mock_service()
        svc.users().messages().modify().execute.return_value = {
            "id": "msg1",
            "labelIds": ["INBOX"],
        }

        result = modify_email(svc, "msg1", remove_labels=["UNREAD"])
        assert result["id"] == "msg1"
        svc.users().messages().modify.assert_called_with(
            userId="me",
            id="msg1",
            body={"addLabelIds": [], "removeLabelIds": ["UNREAD"]},
        )


# ---------------------------------------------------------------------------
# Batch Modify
# ---------------------------------------------------------------------------

class TestBatchModify:
    def test_batch_modify_handles_multiple(self):
        svc = _mock_service()
        svc.users().messages().modify().execute.side_effect = [
            {"id": "msg1", "labelIds": ["INBOX", "STARRED"]},
            {"id": "msg2", "labelIds": ["INBOX", "STARRED"]},
        ]

        result = batch_modify_emails(
            svc, ["msg1", "msg2"], add_labels=["STARRED"]
        )
        assert len(result["modified"]) == 2
        assert result["modified"][0]["id"] == "msg1"

    def test_batch_modify_handles_errors(self):
        svc = _mock_service()
        svc.users().messages().modify().execute.side_effect = [
            {"id": "msg1", "labelIds": ["INBOX"]},
            Exception("Permission denied"),
        ]

        result = batch_modify_emails(
            svc, ["msg1", "msg2"], add_labels=["STARRED"]
        )
        assert len(result["modified"]) == 1
        assert len(result["errors"]) == 1

    def test_batch_modify_empty_list(self):
        svc = _mock_service()
        result = batch_modify_emails(svc, [])
        assert result["modified"] == []
        assert result["errors"] == []


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------

class TestLabels:
    def test_list_labels(self):
        svc = _mock_service()
        svc.users().labels().list().execute.return_value = {
            "labels": [
                {"id": "INBOX", "name": "INBOX", "type": "system"},
                {"id": "Label_1", "name": "Work", "type": "user"},
            ]
        }

        result = list_labels(svc)
        assert len(result) == 2
        assert result[0]["id"] == "INBOX"
        assert result[1]["name"] == "Work"

    def test_list_labels_empty(self):
        svc = _mock_service()
        svc.users().labels().list().execute.return_value = {}

        result = list_labels(svc)
        assert result == []

    def test_create_label(self):
        svc = _mock_service()
        svc.users().labels().create().execute.return_value = {
            "id": "Label_2",
            "name": "Custom",
            "type": "user",
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        }

        result = create_label(svc, "Custom")
        assert result["id"] == "Label_2"
        assert result["name"] == "Custom"
        svc.users().labels().create.assert_called_with(
            userId="me",
            body={
                "name": "Custom",
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show",
            },
        )

    def test_update_label(self):
        svc = _mock_service()
        svc.users().labels().update().execute.return_value = {
            "id": "Label_2",
            "name": "Renamed",
            "type": "user",
        }

        result = update_label(svc, "Label_2", name="Renamed")
        assert result["name"] == "Renamed"
        svc.users().labels().update.assert_called()

    def test_delete_label(self):
        svc = _mock_service()
        svc.users().labels().delete().execute.return_value = None

        result = delete_label(svc, "Label_2")
        assert result["deleted"] is True
        assert result["label_id"] == "Label_2"
        svc.users().labels().delete.assert_called_with(
            userId="me", id="Label_2"
        )


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

class TestFilters:
    def test_list_filters(self):
        svc = _mock_service()
        svc.users().settings().filters().list().execute.return_value = {
            "filter": [
                {
                    "id": "f1",
                    "criteria": {"from": "alerts@example.com"},
                    "action": {"addLabelIds": ["Label_1"]},
                }
            ]
        }

        result = list_filters(svc)
        assert len(result) == 1
        assert result[0]["id"] == "f1"

    def test_list_filters_empty(self):
        svc = _mock_service()
        svc.users().settings().filters().list().execute.return_value = {}

        result = list_filters(svc)
        assert result == []

    def test_get_filter(self):
        svc = _mock_service()
        svc.users().settings().filters().get().execute.return_value = {
            "id": "f1",
            "criteria": {"from": "alerts@example.com"},
            "action": {"addLabelIds": ["Label_1"]},
        }

        result = get_filter(svc, "f1")
        assert result["id"] == "f1"
        assert result["criteria"]["from"] == "alerts@example.com"

    def test_create_filter(self):
        svc = _mock_service()
        svc.users().settings().filters().create().execute.return_value = {
            "id": "f2",
            "criteria": {"from": "news@example.com"},
            "action": {"addLabelIds": ["Label_2"]},
        }

        result = create_filter(
            svc,
            criteria={"from": "news@example.com"},
            action={"addLabelIds": ["Label_2"]},
        )
        assert result["id"] == "f2"
        svc.users().settings().filters().create.assert_called_with(
            userId="me",
            body={
                "criteria": {"from": "news@example.com"},
                "action": {"addLabelIds": ["Label_2"]},
            },
        )

    def test_delete_filter(self):
        svc = _mock_service()
        svc.users().settings().filters().delete().execute.return_value = None

        result = delete_filter(svc, "f1")
        assert result["deleted"] is True
        assert result["filter_id"] == "f1"
        svc.users().settings().filters().delete.assert_called_with(
            userId="me", id="f1"
        )


# ---------------------------------------------------------------------------
# Attachment
# ---------------------------------------------------------------------------

class TestAttachment:
    def test_download_attachment_saves_file(self, tmp_path):
        svc = _mock_service()
        file_content = b"PDF binary content here"
        encoded_data = base64.urlsafe_b64encode(file_content).decode()

        svc.users().messages().attachments().get().execute.return_value = {
            "size": len(file_content),
            "data": encoded_data,
        }

        result = download_attachment(
            svc,
            message_id="msg1",
            attachment_id="att1",
            save_path=str(tmp_path),
            filename="report.pdf",
        )
        assert result["filename"] == "report.pdf"
        assert result["size"] == len(file_content)
        saved_path = tmp_path / "report.pdf"
        assert saved_path.exists()
        assert saved_path.read_bytes() == file_content

    def test_download_attachment_default_filename(self, tmp_path):
        svc = _mock_service()
        file_content = b"some data"
        encoded_data = base64.urlsafe_b64encode(file_content).decode()

        svc.users().messages().attachments().get().execute.return_value = {
            "size": len(file_content),
            "data": encoded_data,
        }

        result = download_attachment(
            svc,
            message_id="msg1",
            attachment_id="att1",
            save_path=str(tmp_path),
        )
        # Should use a default filename when none provided
        assert result["filename"] is not None
        assert (tmp_path / result["filename"]).exists()


# ---------------------------------------------------------------------------
# Helper: _build_message
# ---------------------------------------------------------------------------

class TestBuildMessage:
    def test_build_plain_message(self):
        msg = _build_message(
            to="bob@example.com", subject="Test", body="Hello"
        )
        assert msg["To"] == "bob@example.com"
        assert msg["Subject"] == "Test"

    def test_build_message_with_cc_bcc(self):
        msg = _build_message(
            to="bob@example.com",
            subject="Test",
            body="Hello",
            cc="carol@example.com",
            bcc="dave@example.com",
        )
        assert msg["Cc"] == "carol@example.com"
        assert msg["Bcc"] == "dave@example.com"

    def test_build_html_message(self):
        msg = _build_message(
            to="bob@example.com",
            subject="HTML",
            body="Plain",
            html_body="<p>HTML</p>",
        )
        # Should be multipart/alternative with both parts
        assert msg.get_content_type() == "multipart/alternative"

    def test_build_reply_message(self):
        msg = _build_message(
            to="bob@example.com",
            subject="Re: Original",
            body="Reply text",
            in_reply_to="<original@example.com>",
        )
        assert msg["In-Reply-To"] == "<original@example.com>"
        assert msg["References"] == "<original@example.com>"


# ---------------------------------------------------------------------------
# Helper: _extract_body
# ---------------------------------------------------------------------------

class TestExtractBody:
    def test_extract_plain_text_body(self):
        body_data = base64.urlsafe_b64encode(b"Plain text").decode()
        payload = {
            "mimeType": "text/plain",
            "body": {"size": 10, "data": body_data},
        }
        assert _extract_body(payload) == "Plain text"

    def test_extract_body_from_multipart(self):
        body_data = base64.urlsafe_b64encode(b"From multipart").decode()
        payload = {
            "mimeType": "multipart/alternative",
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"size": 14, "data": body_data},
                },
                {
                    "mimeType": "text/html",
                    "body": {
                        "size": 20,
                        "data": base64.urlsafe_b64encode(
                            b"<p>From multipart</p>"
                        ).decode(),
                    },
                },
            ],
        }
        assert _extract_body(payload) == "From multipart"

    def test_extract_body_nested_multipart(self):
        body_data = base64.urlsafe_b64encode(b"Nested body").decode()
        payload = {
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "mimeType": "multipart/alternative",
                    "parts": [
                        {
                            "mimeType": "text/plain",
                            "body": {"size": 11, "data": body_data},
                        },
                    ],
                },
                {
                    "mimeType": "application/pdf",
                    "filename": "file.pdf",
                    "body": {"size": 500, "attachmentId": "att1"},
                },
            ],
        }
        assert _extract_body(payload) == "Nested body"

    def test_extract_body_empty_payload(self):
        payload = {
            "mimeType": "text/plain",
            "body": {"size": 0},
        }
        assert _extract_body(payload) == ""


# ---------------------------------------------------------------------------
# Helper: _extract_attachments
# ---------------------------------------------------------------------------

class TestExtractAttachments:
    def test_extract_attachments_from_multipart(self):
        payload = {
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"size": 5, "data": "aGVsbG8="},
                },
                {
                    "mimeType": "application/pdf",
                    "filename": "report.pdf",
                    "body": {"size": 1024, "attachmentId": "att1"},
                },
                {
                    "mimeType": "image/png",
                    "filename": "screenshot.png",
                    "body": {"size": 2048, "attachmentId": "att2"},
                },
            ],
        }
        attachments = _extract_attachments(payload)
        assert len(attachments) == 2
        assert attachments[0]["filename"] == "report.pdf"
        assert attachments[0]["attachment_id"] == "att1"
        assert attachments[1]["filename"] == "screenshot.png"

    def test_extract_attachments_none_present(self):
        payload = {
            "mimeType": "text/plain",
            "body": {"size": 5, "data": "aGVsbG8="},
        }
        attachments = _extract_attachments(payload)
        assert attachments == []

    def test_extract_attachments_nested(self):
        payload = {
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "mimeType": "multipart/alternative",
                    "parts": [
                        {
                            "mimeType": "text/plain",
                            "body": {"size": 5, "data": "aGVsbG8="},
                        },
                    ],
                },
                {
                    "mimeType": "application/zip",
                    "filename": "archive.zip",
                    "body": {"size": 4096, "attachmentId": "att3"},
                },
            ],
        }
        attachments = _extract_attachments(payload)
        assert len(attachments) == 1
        assert attachments[0]["filename"] == "archive.zip"
