# backend/api_connector/services/ssrf.py
"""
SSRF protection utility.

ADR-011: Optional RFC 1918 / loopback / link-local IP blocking.
Enabled via settings.SSRF_PROTECTION_ENABLED (default False).

Security (OWASP A10:2021 — SSRF):
  When enabled, resolves the hostname of every outbound URL and checks
  all resulting IP addresses against blocked ranges before any connection.
  Raises SSRFProtectionError with a user-safe message on blocked addresses.

Blocked ranges (RFC 1918, loopback, link-local, IPv6 loopback/ULA):
  10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 — RFC 1918 private
  127.0.0.0/8 — IPv4 loopback
  169.254.0.0/16 — Link-local (AWS instance metadata, etc.)
  ::1/128 — IPv6 loopback
  fc00::/7 — IPv6 ULA (Unique Local Address)

Note on DNS TOCTOU:
  This check resolves the hostname at validation time. The actual connection
  also resolves the hostname. A DNS rebinding attack could return a public IP
  at validation time and a private IP at connection time. This is an accepted
  limitation for MVP scope — document in security-audit.md.
"""

import concurrent.futures
import ipaddress
import logging
import socket
import urllib.parse

from django.conf import settings

logger = logging.getLogger("api_connector.ssrf")

# ── Blocked IP ranges ──────────────────────────────────────────────────────────
BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),  # RFC 1918 class A private
    ipaddress.ip_network("172.16.0.0/12"),  # RFC 1918 class B private
    ipaddress.ip_network("192.168.0.0/16"),  # RFC 1918 class C private
    ipaddress.ip_network("127.0.0.0/8"),  # IPv4 loopback
    ipaddress.ip_network(
        "169.254.0.0/16"
    ),  # Link-local (AWS metadata at 169.254.169.254)
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),  # IPv6 ULA
]


class SSRFProtectionError(Exception):
    """
    Raised when a URL resolves to a blocked (RFC 1918 / loopback) IP address.
    Message is safe to display to users — contains only the blocked IP prefix, not full URL.
    """


def _is_ip_blocked(ip_str: str) -> bool:
    """Return True if the IP address falls within any blocked network."""
    try:
        addr = ipaddress.ip_address(ip_str)
        return any(addr in net for net in BLOCKED_NETWORKS)
    except ValueError:
        # Malformed IP — treat as not blocked (let httpx handle the error)
        return False


def validate_url_for_ssrf(url: str, timeout_seconds: float = 5.0) -> None:
    """
    Resolve the URL's hostname and verify none of the resulting IPs are in blocked ranges.

    Does nothing if settings.SSRF_PROTECTION_ENABLED is False (default).

    Args:
        url: The full URL to validate (e.g. "https://api.example.com/v1/items").
        timeout_seconds: Maximum time for DNS resolution before giving up.

    Raises:
        SSRFProtectionError: if any resolved IP is in a blocked range.
    """
    if not getattr(settings, "SSRF_PROTECTION_ENABLED", False):
        return  # Protection disabled — short-circuit immediately

    parsed = urllib.parse.urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        return  # No hostname to validate (relative URL, etc.)

    # Use ThreadPoolExecutor to apply a hard timeout on the blocking DNS call
    def resolve() -> list[str]:
        results = socket.getaddrinfo(hostname, None)
        return [r[4][0] for r in results]

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(resolve)
            resolved_ips = future.result(timeout=timeout_seconds)
    except concurrent.futures.TimeoutError:
        # DNS timeout — allow through (don't block on inability to resolve)
        logger.warning(
            "SSRF validation: DNS timeout for hostname '%s' — allowing through",
            hostname,
        )
        return
    except socket.gaierror:
        # DNS failure — allow through (httpx will handle the error)
        return

    for ip_str in resolved_ips:
        if _is_ip_blocked(ip_str):
            # Log hostname prefix only — never full URL (may contain API key in query string)
            logger.warning(
                "SSRF protection: blocked request to hostname '%s' — resolved to private/loopback IP",
                hostname,
            )
            raise SSRFProtectionError(
                f"The URL '{parsed.scheme}://{hostname}' resolves to a private or loopback "
                f"IP address, which is not permitted. "
                f"Configure this integration to use a publicly accessible API endpoint."
            )
