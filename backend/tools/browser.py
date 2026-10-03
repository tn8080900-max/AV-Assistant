from urllib.parse import urlsplit
import webbrowser


def open_website(url: str) -> str:
    candidate = url.strip()
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only complete http:// or https:// website addresses can be opened.")
    if parsed.username or parsed.password:
        raise ValueError("Web addresses containing login details are not allowed.")
    if not webbrowser.open(candidate, new=2):
        raise RuntimeError("Windows could not open the default browser.")
    return f"Opened {parsed.hostname} in the default browser."