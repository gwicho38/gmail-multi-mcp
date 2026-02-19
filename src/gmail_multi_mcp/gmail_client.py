"""Gmail API wrapper functions.

All functions are stateless: they accept a Gmail API service object,
call the appropriate API endpoint, and return results. No credentials
or account management is handled here.
"""

import base64
import logging
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _get_header(headers: list[dict], name: str) -> str:
    """Extract a header value by name (case-insensitive) from Gmail headers."""
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _extract_body(payload: dict) -> str:
    """Extract the plain-text body from a Gmail message payload.

    Handles single-part, multipart/alternative, and nested multipart
    structures by recursively searching for the first text/plain part.
    """
    mime_type = payload.get("mimeType", "")

    # Direct text/plain body
    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        return ""

    # Multipart: recurse into parts
    parts = payload.get("parts", [])
    for part in parts:
        body = _extract_body(part)
        if body:
            return body

    return ""


def _extract_attachments(payload: dict) -> list[dict]:
    """Extract attachment metadata from a Gmail message payload.

    Returns a list of dicts with keys: filename, mime_type, size, attachment_id.
    """
    attachments = []
    parts = payload.get("parts", [])

    for part in parts:
        filename = part.get("filename", "")
        attachment_id = part.get("body", {}).get("attachmentId")

        if filename and attachment_id:
            attachments.append(
                {
                    "filename": filename,
                    "mime_type": part.get("mimeType", ""),
                    "size": part.get("body", {}).get("size", 0),
                    "attachment_id": attachment_id,
                }
            )

        # Recurse into nested multipart
        nested = _extract_attachments(part)
        attachments.extend(nested)

    return attachments


def _build_message(
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    bcc: str | None = None,
    html_body: str | None = None,
    in_reply_to: str | None = None,
    attachments: list[str] | None = None,
) -> MIMEBase:
    """Build a MIME message for sending via the Gmail API.

    Supports plain text, HTML (multipart/alternative), replies,
    and file attachments.
    """
    # Determine the base message structure
    if attachments:
        msg = MIMEMultipart("mixed")
        if html_body:
            alt = MIMEMultipart("alternative")
            alt.attach(MIMEText(body, "plain"))
            alt.attach(MIMEText(html_body, "html"))
            msg.attach(alt)
        else:
            msg.attach(MIMEText(body, "plain"))

        for file_path in attachments:
            path = Path(file_path)
            part = MIMEBase("application", "octet-stream")
            part.set_payload(path.read_bytes())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition", f'attachment; filename="{path.name}"'
            )
            msg.attach(part)
    elif html_body:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body, "plain"))
        msg.attach(MIMEText(html_body, "html"))
    else:
        msg = MIMEText(body, "plain")

    msg["To"] = to
    msg["Subject"] = subject

    if cc:
        msg["Cc"] = cc
    if bcc:
        msg["Bcc"] = bcc
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to

    return msg


def _encode_message(msg: MIMEBase) -> str:
    """Base64url-encode a MIME message for the Gmail API."""
    return base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")


# ---------------------------------------------------------------------------
# Email operations
# ---------------------------------------------------------------------------


def search_emails(
    service, query: str, max_results: int = 10
) -> list[dict]:
    """List messages matching a Gmail search query, with metadata for each.

    Args:
        service: Gmail API service object.
        query: Gmail search query string (e.g. "is:unread").
        max_results: Maximum number of messages to return.

    Returns:
        List of message summary dicts with id, threadId, from, to, subject,
        date, snippet, and labels.
    """
    resp = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )

    messages = resp.get("messages", [])
    if not messages:
        return []

    results = []
    for msg_stub in messages:
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=msg_stub["id"], format="metadata",
                 metadataHeaders=["From", "To", "Subject", "Date"])
            .execute()
        )
        headers = msg.get("payload", {}).get("headers", [])
        results.append(
            {
                "id": msg["id"],
                "threadId": msg.get("threadId", ""),
                "from": _get_header(headers, "From"),
                "to": _get_header(headers, "To"),
                "subject": _get_header(headers, "Subject"),
                "date": _get_header(headers, "Date"),
                "snippet": msg.get("snippet", ""),
                "labels": msg.get("labelIds", []),
            }
        )

    return results


def read_email(service, message_id: str) -> dict:
    """Get a full message with body extraction and attachment metadata.

    Args:
        service: Gmail API service object.
        message_id: The Gmail message ID.

    Returns:
        Dict with id, threadId, from, to, subject, date, message_id (header),
        body, snippet, labels, and attachments.
    """
    msg = (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )

    payload = msg.get("payload", {})
    headers = payload.get("headers", [])

    return {
        "id": msg["id"],
        "threadId": msg.get("threadId", ""),
        "from": _get_header(headers, "From"),
        "to": _get_header(headers, "To"),
        "subject": _get_header(headers, "Subject"),
        "date": _get_header(headers, "Date"),
        "message_id": _get_header(headers, "Message-ID"),
        "body": _extract_body(payload),
        "snippet": msg.get("snippet", ""),
        "labels": msg.get("labelIds", []),
        "attachments": _extract_attachments(payload),
    }


def send_email(
    service,
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    bcc: str | None = None,
    html_body: str | None = None,
    mime_type: str = "text/plain",
    attachments: list[str] | None = None,
    in_reply_to: str | None = None,
    thread_id: str | None = None,
) -> dict:
    """Build a MIME message, base64-encode it, and send via the Gmail API.

    Args:
        service: Gmail API service object.
        to: Recipient email address.
        subject: Email subject line.
        body: Plain-text body.
        cc: CC recipient(s).
        bcc: BCC recipient(s).
        html_body: Optional HTML body (creates multipart/alternative).
        mime_type: MIME type hint (default text/plain).
        attachments: List of file paths to attach.
        in_reply_to: Message-ID of the message being replied to.
        thread_id: Thread ID to add this message to (for replies).

    Returns:
        The API response dict for the sent message.
    """
    msg = _build_message(
        to=to,
        subject=subject,
        body=body,
        cc=cc,
        bcc=bcc,
        html_body=html_body,
        in_reply_to=in_reply_to,
        attachments=attachments,
    )

    raw = _encode_message(msg)
    send_body: dict = {"raw": raw}
    if thread_id:
        send_body["threadId"] = thread_id

    return (
        service.users()
        .messages()
        .send(userId="me", body=send_body)
        .execute()
    )


def draft_email(
    service,
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    bcc: str | None = None,
    html_body: str | None = None,
    mime_type: str = "text/plain",
    attachments: list[str] | None = None,
    in_reply_to: str | None = None,
    thread_id: str | None = None,
) -> dict:
    """Create a draft message (same params as send_email).

    Returns:
        The API response dict for the created draft.
    """
    msg = _build_message(
        to=to,
        subject=subject,
        body=body,
        cc=cc,
        bcc=bcc,
        html_body=html_body,
        in_reply_to=in_reply_to,
        attachments=attachments,
    )

    raw = _encode_message(msg)
    draft_body: dict = {"message": {"raw": raw}}
    if thread_id:
        draft_body["message"]["threadId"] = thread_id

    return (
        service.users()
        .drafts()
        .create(userId="me", body=draft_body)
        .execute()
    )


def delete_email(service, message_id: str) -> dict:
    """Move a message to trash.

    Args:
        service: Gmail API service object.
        message_id: The Gmail message ID.

    Returns:
        The API response dict for the trashed message.
    """
    return (
        service.users()
        .messages()
        .trash(userId="me", id=message_id)
        .execute()
    )


def batch_delete_emails(
    service, message_ids: list[str], batch_size: int = 50
) -> dict:
    """Trash multiple messages, processing in batches.

    Args:
        service: Gmail API service object.
        message_ids: List of message IDs to trash.
        batch_size: Number of messages to process per batch.

    Returns:
        Dict with 'deleted' (list of IDs) and 'errors' (list of error dicts).
    """
    deleted: list[str] = []
    errors: list[dict] = []

    for i in range(0, max(len(message_ids), 1), batch_size):
        batch = message_ids[i : i + batch_size]
        for msg_id in batch:
            try:
                service.users().messages().trash(
                    userId="me", id=msg_id
                ).execute()
                deleted.append(msg_id)
            except Exception as exc:
                logger.warning("Failed to trash message %s: %s", msg_id, exc)
                errors.append({"message_id": msg_id, "error": str(exc)})

    return {"deleted": deleted, "errors": errors}


def modify_email(
    service,
    message_id: str,
    add_labels: list[str] | None = None,
    remove_labels: list[str] | None = None,
) -> dict:
    """Modify labels on a single message.

    Args:
        service: Gmail API service object.
        message_id: The Gmail message ID.
        add_labels: Label IDs to add.
        remove_labels: Label IDs to remove.

    Returns:
        The API response dict for the modified message.
    """
    body = {
        "addLabelIds": add_labels or [],
        "removeLabelIds": remove_labels or [],
    }
    return (
        service.users()
        .messages()
        .modify(userId="me", id=message_id, body=body)
        .execute()
    )


def batch_modify_emails(
    service,
    message_ids: list[str],
    add_labels: list[str] | None = None,
    remove_labels: list[str] | None = None,
    batch_size: int = 50,
) -> dict:
    """Modify labels on multiple messages in batches.

    Args:
        service: Gmail API service object.
        message_ids: List of message IDs to modify.
        add_labels: Label IDs to add.
        remove_labels: Label IDs to remove.
        batch_size: Number of messages per batch.

    Returns:
        Dict with 'modified' (list of response dicts) and 'errors' (list of error dicts).
    """
    modified: list[dict] = []
    errors: list[dict] = []

    for i in range(0, max(len(message_ids), 1), batch_size):
        batch = message_ids[i : i + batch_size]
        for msg_id in batch:
            try:
                result = modify_email(
                    service, msg_id,
                    add_labels=add_labels,
                    remove_labels=remove_labels,
                )
                modified.append(result)
            except Exception as exc:
                logger.warning("Failed to modify message %s: %s", msg_id, exc)
                errors.append({"message_id": msg_id, "error": str(exc)})

    return {"modified": modified, "errors": errors}


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


def list_labels(service) -> list[dict]:
    """List all labels for the authenticated user.

    Returns:
        List of label dicts.
    """
    resp = service.users().labels().list(userId="me").execute()
    return resp.get("labels", [])


def create_label(
    service,
    name: str,
    label_list_visibility: str = "labelShow",
    message_list_visibility: str = "show",
) -> dict:
    """Create a new label.

    Args:
        service: Gmail API service object.
        name: Label name.
        label_list_visibility: Visibility in label list.
        message_list_visibility: Visibility in message list.

    Returns:
        The created label dict.
    """
    body = {
        "name": name,
        "labelListVisibility": label_list_visibility,
        "messageListVisibility": message_list_visibility,
    }
    return (
        service.users()
        .labels()
        .create(userId="me", body=body)
        .execute()
    )


def update_label(
    service,
    label_id: str,
    name: str | None = None,
    label_list_visibility: str | None = None,
    message_list_visibility: str | None = None,
) -> dict:
    """Update an existing label.

    Args:
        service: Gmail API service object.
        label_id: The label ID to update.
        name: New label name (optional).
        label_list_visibility: New visibility in label list (optional).
        message_list_visibility: New visibility in message list (optional).

    Returns:
        The updated label dict.
    """
    body: dict = {}
    if name is not None:
        body["name"] = name
    if label_list_visibility is not None:
        body["labelListVisibility"] = label_list_visibility
    if message_list_visibility is not None:
        body["messageListVisibility"] = message_list_visibility

    return (
        service.users()
        .labels()
        .update(userId="me", id=label_id, body=body)
        .execute()
    )


def delete_label(service, label_id: str) -> dict:
    """Delete a label.

    Args:
        service: Gmail API service object.
        label_id: The label ID to delete.

    Returns:
        Dict with 'deleted' (True) and 'label_id'.
    """
    service.users().labels().delete(userId="me", id=label_id).execute()
    return {"deleted": True, "label_id": label_id}


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


def list_filters(service) -> list[dict]:
    """List all filters for the authenticated user.

    Returns:
        List of filter dicts.
    """
    resp = (
        service.users()
        .settings()
        .filters()
        .list(userId="me")
        .execute()
    )
    return resp.get("filter", [])


def get_filter(service, filter_id: str) -> dict:
    """Get a specific filter by ID.

    Args:
        service: Gmail API service object.
        filter_id: The filter ID.

    Returns:
        The filter dict.
    """
    return (
        service.users()
        .settings()
        .filters()
        .get(userId="me", id=filter_id)
        .execute()
    )


def create_filter(service, criteria: dict, action: dict) -> dict:
    """Create a new filter.

    Args:
        service: Gmail API service object.
        criteria: Filter criteria dict (e.g. {"from": "user@example.com"}).
        action: Filter action dict (e.g. {"addLabelIds": ["Label_1"]}).

    Returns:
        The created filter dict.
    """
    body = {"criteria": criteria, "action": action}
    return (
        service.users()
        .settings()
        .filters()
        .create(userId="me", body=body)
        .execute()
    )


def delete_filter(service, filter_id: str) -> dict:
    """Delete a filter.

    Args:
        service: Gmail API service object.
        filter_id: The filter ID to delete.

    Returns:
        Dict with 'deleted' (True) and 'filter_id'.
    """
    (
        service.users()
        .settings()
        .filters()
        .delete(userId="me", id=filter_id)
        .execute()
    )
    return {"deleted": True, "filter_id": filter_id}


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------


def download_attachment(
    service,
    message_id: str,
    attachment_id: str,
    save_path: str = ".",
    filename: str | None = None,
) -> dict:
    """Download an attachment and save it to disk.

    Args:
        service: Gmail API service object.
        message_id: The Gmail message ID containing the attachment.
        attachment_id: The attachment ID.
        save_path: Directory to save the file to.
        filename: Filename to use. Defaults to 'attachment_<attachment_id>'.

    Returns:
        Dict with 'filename', 'path', and 'size'.
    """
    resp = (
        service.users()
        .messages()
        .attachments()
        .get(userId="me", messageId=message_id, id=attachment_id)
        .execute()
    )

    data = base64.urlsafe_b64decode(resp["data"])
    if filename is None:
        filename = f"attachment_{attachment_id}"

    save_dir = Path(save_path)
    save_dir.mkdir(parents=True, exist_ok=True)
    file_path = save_dir / filename
    file_path.write_bytes(data)

    return {
        "filename": filename,
        "path": str(file_path),
        "size": len(data),
    }
