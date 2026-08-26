"""
src/friday/tools/gmail.py

WHAT THIS IS FOR:
Provides Gmail integration tools (search, read, send) per blueprint §21, §46.
Gated by online availability and security policies.
"""

from __future__ import annotations

import base64
from email.mime.text import MIMEText
from typing import Any

from .registry import Tool, VerificationResult
from .metadata import build_schema


def _search(query: str = "", max_results: int = 5, **kwargs) -> dict[str, Any]:
    """Search or list recent messages in Gmail inbox."""
    from friday.security.google_auth import get_credentials
    from googleapiclient.discovery import build

    max_results = max(1, min(20, int(kwargs.get("count", kwargs.get("limit", max_results)))))
    try:
        service = build("gmail", "v1", credentials=get_credentials())
        q = query.strip() if query else "label:INBOX"
        results = service.users().messages().list(userId="me", maxResults=max_results, q=q).execute()

        messages = []
        for msg in results.get("messages", []):
            full = service.users().messages().get(
                userId="me",
                id=msg["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
            headers = {h["name"]: h["value"] for h in full.get("payload", {}).get("headers", [])}
            messages.append({
                "id": msg["id"],
                "from": headers.get("From", "Unknown"),
                "subject": headers.get("Subject", "(no subject)"),
                "date": headers.get("Date", ""),
                "snippet": full.get("snippet", ""),
            })
        return {"status": "ok", "messages": messages, "count": len(messages)}
    except FileNotFoundError as exc:
        return {"status": "error", "message": f"Gmail not configured: {exc}"}
    except Exception as exc:
        return {"status": "error", "message": f"Could not search Gmail: {exc}"}


def _read(message_id: str) -> dict[str, Any]:
    """Read a specific email message body by ID."""
    from friday.security.google_auth import get_credentials
    from googleapiclient.discovery import build

    try:
        service = build("gmail", "v1", credentials=get_credentials())
        msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        
        body = msg.get("snippet", "")
        payload = msg.get("payload", {})
        if "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain" and "data" in part.get("body", {}):
                    body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                    break
        elif "data" in payload.get("body", {}):
            body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

        return {
            "status": "ok",
            "id": message_id,
            "from": headers.get("From", "Unknown"),
            "subject": headers.get("Subject", "(no subject)"),
            "date": headers.get("Date", ""),
            "body": body,
        }
    except Exception as exc:
        return {"status": "error", "message": f"Could not read email {message_id}: {exc}"}


def _send(to: str, subject: str, body: str) -> dict[str, Any]:
    """Send an email message via Gmail."""
    from friday.security.google_auth import get_credentials
    from googleapiclient.discovery import build

    try:
        service = build("gmail", "v1", credentials=get_credentials())
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return {"status": "ok", "message_id": sent.get("id"), "to": to, "subject": subject}
    except Exception as exc:
        return {"status": "error", "message": f"Could not send email: {exc}"}


def _verify_send(args: dict, result: dict) -> VerificationResult:
    if isinstance(result, dict) and result.get("status") == "ok" and result.get("message_id"):
        return VerificationResult(True, f"Email sent successfully with message ID {result.get('message_id')}")
    return VerificationResult(False, result.get("message", "Failed to send email"))


def register_all_tools(registry) -> None:
    registry.register(Tool(
        name="gmail.search",
        description="Search recent emails in inbox (From, Subject, snippet).",
        tier="GREEN",
        capability_scope="gmail.read",
        online_required=True,
        input_schema=build_schema({"query": {"type": "string"}}, []),
        handler=_search,
    ))
    registry.register(Tool(
        name="gmail.read",
        description="Read the content of a specific email by ID.",
        tier="GREEN",
        capability_scope="gmail.read",
        online_required=True,
        input_schema=build_schema({"message_id": {"type": "string"}}, ["message_id"]),
        handler=_read,
    ))
    registry.register(Tool(
        name="gmail.send",
        description="Send an email to a recipient.",
        tier="ORANGE",
        capability_scope="gmail.send",
        online_required=True,
        input_schema=build_schema({
            "to": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
        }, ["to", "subject", "body"]),
        handler=_send,
        verify=_verify_send,
    ))
