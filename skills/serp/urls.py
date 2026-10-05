"""URL safety checks shared by SERP parsing and page visiting."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

MAX_URL_LENGTH = 2000
_LOCAL_SUFFIXES = (".localhost", ".local", ".internal")


def unsafe_reason(url: object) -> str | None:
    """Explain why ``url`` must not be visited, or return ``None`` if it is safe.

    Safe means: a well-formed, absolute ``http``/``https`` URL without embedded
    credentials whose host is not obviously local or private. Hostnames are not
    resolved, so a public name that points at a private address is not caught.
    """
    if not isinstance(url, str) or not url:
        return "not a URL"
    if len(url) > MAX_URL_LENGTH:
        return "URL too long"
    if any(ch.isspace() or ord(ch) < 32 for ch in url):
        return "URL contains whitespace or control characters"

    try:
        parts = urlsplit(url)
        host = parts.hostname
        parts.port  # Raises ValueError on a malformed port.
    except ValueError:
        return "malformed URL"

    if parts.scheme not in ("http", "https"):
        return f"unsupported scheme '{parts.scheme}'" if parts.scheme else "not an absolute URL"
    if not host:
        return "URL has no host"
    if parts.username is not None or parts.password is not None:
        return "URL contains credentials"

    host = host.rstrip(".")
    if host == "localhost" or host.endswith(_LOCAL_SUFFIXES):
        return "local host"
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # Browsers read hosts such as "2130706433" or "0x7f.1" as IPv4 addresses.
        last_label = host.rsplit(".", 1)[-1]
        if "." not in host or last_label.isdigit() or last_label.startswith("0x"):
            return "host is not a public domain name"
        return None
    return None if address.is_global else "non-public IP address"
