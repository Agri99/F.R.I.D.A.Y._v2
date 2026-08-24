from googleapiclient.discovery import build

from tools.registry import register_tool
from security.policy import RiskClass
from security.google_auth import get_credentials


@register_tool(risk=RiskClass.GREEN)
def check_inbox(max_results: int = 5, **kwargs) -> dict:
    max_results = kwargs.get("count", kwargs.get("limit", max_results))
    """Check the most recent emails in the inbox (sender, subject, and a short snippet only).

    Args:
        max_results: How many recent emails to fetch (default 5, max 20).

    Returns:
        dict: list of recent emails
    """
    max_results = max(1, min(20, max_results))
    try:
        service = build("gmail", "v1", credentials=get_credentials())
        results = service.users().messages().list(
            userId="me", maxResults=max_results, labelIds=["INBOX"]
        ).execute()

        emails = []
        for msg in results.get("messages", []):
            full = service.users().messages().get(
                userId="me", id=msg["id"], format="metadata",
                metadataHeaders=["From", "Subject"],
            ).execute()
            headers = {h["name"]: h["value"] for h in full["payload"]["headers"]}
            emails.append({
                "from": headers.get("From", "Unknown"),
                "subject": headers.get("Subject", "(no subject)"),
                "snippet": full.get("snippet", ""),
            })
        return {"status": "ok", "emails": emails}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "message": f"Could not check inbox: {exc}"}