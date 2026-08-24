import webbrowser
from urllib.parse import quote_plus

from tools.registry import register_tool
from security.policy import RiskClass


def _is_safe_url(url: str) -> bool:
    return url.strip().lower().startswith(("http://", "https://"))


@register_tool(risk=RiskClass.YELLOW)
def open_url(url: str) -> dict:
    """Open a web page in the default browser.

    Args:
        url: The full URL to open, must start with http:// or https://

    Returns:
        dict: status of the open action
    """
    url = url.strip()
    if not _is_safe_url(url):
        return {"status": "error", "message": "Only http:// or https:// URLs are allowed."}
    webbrowser.open(url)
    return {"status": "ok", "url": url}


@register_tool(risk=RiskClass.YELLOW)
def web_search(query: str) -> dict:
    """Search the web for a query, opening the results in the default browser.

    Args:
        query: What to search for.

    Returns:
        dict: status and the search URL opened
    """
    query = (query or "").strip()
    if not query:
        return {"status": "error", "message": "No search query provided."}
    search_url = f"https://www.google.com/search?q={quote_plus(query)}"
    webbrowser.open(search_url)
    return {"status": "ok", "url": search_url}