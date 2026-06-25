# backend/tests/test_ssrf.py
"""
SSRF protection utility unit tests.
No DB access, no real DNS calls (hostnames mocked).
"""
import socket
from unittest.mock import patch

import pytest
from django.test import override_settings

from api_connector.services.ssrf import (
    SSRFProtectionError,
    _is_ip_blocked,
    validate_url_for_ssrf,
)


class TestIsIpBlocked:
    def test_rfc1918_class_a_blocked(self):
        assert _is_ip_blocked("10.0.0.1") is True
        assert _is_ip_blocked("10.255.255.255") is True

    def test_rfc1918_class_b_blocked(self):
        assert _is_ip_blocked("172.16.0.1") is True
        assert _is_ip_blocked("172.31.255.255") is True

    def test_rfc1918_class_c_blocked(self):
        assert _is_ip_blocked("192.168.1.1") is True
        assert _is_ip_blocked("192.168.255.255") is True

    def test_loopback_blocked(self):
        assert _is_ip_blocked("127.0.0.1") is True
        assert _is_ip_blocked("127.255.255.255") is True

    def test_link_local_blocked(self):
        assert _is_ip_blocked("169.254.169.254") is True  # AWS metadata
        assert _is_ip_blocked("169.254.0.1") is True

    def test_ipv6_loopback_blocked(self):
        assert _is_ip_blocked("::1") is True

    def test_public_ip_not_blocked(self):
        assert _is_ip_blocked("93.184.216.34") is False   # example.com
        assert _is_ip_blocked("8.8.8.8") is False          # Google DNS

    def test_malformed_ip_not_blocked(self):
        assert _is_ip_blocked("not-an-ip") is False


class TestValidateUrlForSsrf:
    @override_settings(SSRF_PROTECTION_ENABLED=False)
    def test_disabled_does_not_validate(self):
        """When disabled, any URL passes — including private IPs."""
        # No exception raised even for private IP in URL
        validate_url_for_ssrf("http://192.168.1.1/secret")  # No exception

    @override_settings(SSRF_PROTECTION_ENABLED=True)
    def test_private_ip_raises_ssrf_error(self):
        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("192.168.1.1", 0))]):
            with pytest.raises(SSRFProtectionError) as exc_info:
                validate_url_for_ssrf("https://internal.service.local/api")
            assert "private or loopback" in str(exc_info.value)
            assert "internal.service.local" in str(exc_info.value)

    @override_settings(SSRF_PROTECTION_ENABLED=True)
    def test_aws_metadata_endpoint_blocked(self):
        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("169.254.169.254", 0))]):
            with pytest.raises(SSRFProtectionError):
                validate_url_for_ssrf("http://169.254.169.254/latest/meta-data")

    @override_settings(SSRF_PROTECTION_ENABLED=True)
    def test_public_api_passes(self):
        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 0))]):
            validate_url_for_ssrf("https://api.example.com/v1/items")  # No exception

    @override_settings(SSRF_PROTECTION_ENABLED=True)
    def test_loopback_blocked(self):
        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 0))]):
            with pytest.raises(SSRFProtectionError):
                validate_url_for_ssrf("http://localhost:8080/admin")

    @override_settings(SSRF_PROTECTION_ENABLED=True)
    def test_dns_timeout_allows_through(self):
        """DNS timeout — allow through, let httpx handle the actual connection failure."""
        import concurrent.futures
        with patch("concurrent.futures.Future.result", side_effect=concurrent.futures.TimeoutError()):
            validate_url_for_ssrf("https://slow-dns.example.com/api")  # No exception

    @override_settings(SSRF_PROTECTION_ENABLED=True)
    def test_dns_failure_allows_through(self):
        """DNS failure — allow through, let httpx handle it."""
        with patch("socket.getaddrinfo", side_effect=socket.gaierror("NXDOMAIN")):
            validate_url_for_ssrf("https://nonexistent.invalid/api")  # No exception

    @override_settings(SSRF_PROTECTION_ENABLED=True)
    def test_url_without_hostname_passes(self):
        """Relative URLs or malformed URLs without hostname — allow through."""
        validate_url_for_ssrf("/relative/path")  # No exception

    @override_settings(SSRF_PROTECTION_ENABLED=False)
    def test_error_message_does_not_expose_query_string(self):
        """Error message must not expose full URL (may contain API key as query param)."""
        with override_settings(SSRF_PROTECTION_ENABLED=True):
            with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("10.0.0.1", 0))]):
                with pytest.raises(SSRFProtectionError) as exc_info:
                    validate_url_for_ssrf("https://internal.host/api?api_key=SECRET123")
                # The error message must not contain the API key
                assert "SECRET123" not in str(exc_info.value)