# backend/tests/test_connection_test_service.py
"""
ConnectionTestService unit tests.

ALL outbound calls are mocked:
  - socket.getaddrinfo → unittest.mock.patch
  - BaseHTTPClient / httpx → pytest-httpx or unittest.mock.patch
  - OAuthCCTokenService → unittest.mock.patch

Rules enforced here:
  - Zero real DNS queries
  - Zero real HTTP calls
  - Each step tested in isolation where possible
"""

import socket
from unittest.mock import MagicMock, patch

import httpx
import pytest

from api_connector.models import AuthType, ConnectionProfile
from api_connector.services.connection_test.service import ConnectionTestService
from api_connector.services.connection_test.types import (
    DNS_RESOLUTION,
    NETWORK_CONNECTIVITY,
)
from api_connector.services.encryption import encryption_service
from api_connector.services.http_exceptions import (
    HTTPNetworkError,
    HTTPStatusError,
    HTTPTimeoutError,
)
from tests.factories import AuthConfigFactory, ConnectionProfileFactory

# ── Helpers ───────────────────────────────────────────────────────────────────


def make_profile(auth_type=AuthType.BEARER, **kwargs):
    profile = ConnectionProfileFactory(auth_type=auth_type, **kwargs)
    if auth_type == AuthType.NONE:
        creds = {}
    elif auth_type == AuthType.BEARER:
        creds = {"token": "test-token", "header_name": "Authorization"}
    elif auth_type == AuthType.API_KEY:
        creds = {"key_name": "X-API-Key", "key_value": "mykey", "delivery": "header"}
    elif auth_type == AuthType.BASIC:
        creds = {"username": "user", "password": "pass"}
    elif auth_type == AuthType.OAUTH_CC:
        creds = {
            "client_id": "cid",
            "client_secret": "csecret",
            "token_endpoint": "https://auth.example.com/token",
        }
    else:
        creds = {}
    AuthConfigFactory(
        connection_profile=profile,
        encrypted_credentials=encryption_service.encrypt_dict(creds),
        credentials_summary={k: {"is_set": bool(v)} for k, v in creds.items()},
    )
    return profile


def make_fake_dns_result(ip="1.2.3.4"):
    return [(2, 1, 6, "", (ip, 0))]


def make_fake_http_response(
    status_code=200, json_body=None, content_type="application/json"
):
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.headers = {"content-type": content_type} if content_type else {}
    response.text = '{"data": [1, 2, 3]}' if json_body is None else str(json_body)
    response.content = response.text.encode()
    return response


# ── DNS Resolution Step ───────────────────────────────────────────────────────


class TestStepDnsResolution:
    svc = ConnectionTestService()

    def test_pass_resolves_ips(self):
        with patch(
            "socket.getaddrinfo",
            return_value=make_fake_dns_result("1.2.3.4")
            + make_fake_dns_result("5.6.7.8"),
        ):
            result = self.svc._step_dns_resolution("api.example.com", ssl_verify=True)
        assert result.passed is True
        assert result.name == DNS_RESOLUTION
        assert "1.2.3.4" in result.detail["resolved_ips"]
        assert "api.example.com" in result.message

    def test_fail_name_not_found(self):
        with patch(
            "socket.getaddrinfo", side_effect=socket.gaierror(8, "Name not found")
        ):
            result = self.svc._step_dns_resolution(
                "nonexistent.invalid", ssl_verify=True
            )
        assert result.passed is False
        assert result.name == DNS_RESOLUTION
        # CRITICAL: no Python exception class name in user-facing message
        assert "gaierror" not in result.message.lower()
        assert "nonexistent.invalid" in result.message

    def test_fail_timeout(self):
        import concurrent.futures

        with patch(
            "concurrent.futures.Future.result",
            side_effect=concurrent.futures.TimeoutError(),
        ):
            result = self.svc._step_dns_resolution("slow.example.com", ssl_verify=True)
        assert result.passed is False
        assert "timed out" in result.message.lower()

    def test_detail_has_suggested_action_on_fail(self):
        with patch("socket.getaddrinfo", side_effect=socket.gaierror(8, "NX")):
            result = self.svc._step_dns_resolution("bad.host", ssl_verify=True)
        assert "suggested_action" in result.detail
        assert len(result.detail["suggested_action"]) > 0


# ── Network Connectivity Step ─────────────────────────────────────────────────


class TestStepNetworkConnectivity:
    svc = ConnectionTestService()

    def test_pass_on_200(self, httpx_mock):
        httpx_mock.add_response(status_code=200, json={"status": "ok"})
        result = self.svc._step_network_connectivity(
            "https://api.example.com", ssl_verify=True, timeout=30
        )
        assert result.passed is True
        assert result.detail["status_code"] == 200

    def test_pass_on_401(self, httpx_mock):
        """Server responded with 401 — TCP/TLS still works, step passes."""
        httpx_mock.add_exception(
            HTTPStatusError("HTTP 401", status_code=401, response_body="Unauthorized")
        )
        result = self.svc._step_network_connectivity(
            "https://api.example.com", ssl_verify=True, timeout=30
        )
        assert result.passed is True
        assert result.detail["status_code"] == 401

    def test_fail_on_timeout(self, httpx_mock):
        httpx_mock.add_exception(
            HTTPTimeoutError("Read timed out", url="https://x.com")
        )
        result = self.svc._step_network_connectivity(
            "https://api.example.com", ssl_verify=True, timeout=30
        )
        assert result.passed is False
        assert "timed out" in result.message.lower()

    def test_fail_on_ssl_error(self, httpx_mock):
        httpx_mock.add_exception(
            HTTPNetworkError("SSL certificate verify failed", url="https://x.com")
        )
        result = self.svc._step_network_connectivity(
            "https://api.example.com", ssl_verify=True, timeout=30
        )
        assert result.passed is False
        assert result.detail["ssl_error"] is True
        assert (
            "certificate" in result.message.lower()
            or "tls" in result.message.lower()
            or "ssl" in result.message.lower()
        )

    def test_fail_on_connection_refused(self, httpx_mock):
        httpx_mock.add_exception(
            HTTPNetworkError("Connection refused", url="https://x.com")
        )
        result = self.svc._step_network_connectivity(
            "https://api.example.com", ssl_verify=True, timeout=30
        )
        assert result.passed is False
        assert result.detail["ssl_error"] is False

    def test_capped_timeout(self, httpx_mock):
        """Connectivity check uses min(timeout, 10) to avoid long waits."""
        httpx_mock.add_response(status_code=200)
        # Should not raise even with a 120s profile timeout
        result = self.svc._step_network_connectivity(
            "https://api.example.com", ssl_verify=True, timeout=120
        )
        assert result.passed is True


# ── Auth Injection Step ───────────────────────────────────────────────────────


@pytest.mark.django_db
class TestStepAuthInjection:
    svc = ConnectionTestService()

    def test_pass_bearer(self):
        profile = make_profile(auth_type=AuthType.BEARER)
        result, credentials = self.svc._step_auth_injection(
            profile, profile.auth_config
        )
        assert result.passed is True
        assert "_profile_id" in credentials
        assert credentials["_profile_id"] == profile.pk

    def test_pass_none_auth(self):
        profile = make_profile(auth_type=AuthType.NONE)
        result, credentials = self.svc._step_auth_injection(
            profile, profile.auth_config
        )
        assert result.passed is True
        assert "_profile_id" in credentials

    def test_fail_oauth_ac(self):
        """OAuth AC requires browser — always fails step 3, no exception raised."""
        profile = make_profile(auth_type=AuthType.OAUTH_AC)
        result, credentials = self.svc._step_auth_injection(
            profile, profile.auth_config
        )
        assert result.passed is False
        assert credentials == {}
        assert "browser" in result.message.lower()
        assert "suggested_action" in result.detail

    def test_fail_empty_credentials(self):
        profile = ConnectionProfileFactory(auth_type=AuthType.BEARER)
        auth_config = AuthConfigFactory(
            connection_profile=profile,
            encrypted_credentials=encryption_service.encrypt_dict({}),
        )
        result, _ = self.svc._step_auth_injection(profile, auth_config)
        assert result.passed is False
        assert (
            "credentials" in result.message.lower()
            or "no credentials" in result.message.lower()
        )

    def test_fail_corrupt_credentials(self):
        profile = ConnectionProfileFactory(auth_type=AuthType.BEARER)
        auth_config = AuthConfigFactory(
            connection_profile=profile,
            encrypted_credentials={"blob": "NOT_A_VALID_FERNET_TOKEN"},
        )
        result, _ = self.svc._step_auth_injection(profile, auth_config)
        assert result.passed is False
        assert (
            "corrupt" in result.message.lower() or "decrypted" in result.message.lower()
        )

    def test_pass_oauth_cc_with_token_fetch(self):
        profile = make_profile(auth_type=AuthType.OAUTH_CC)
        with patch(
            "api_connector.services.oauth_cc_token.OAuthCCTokenService.get_token",
            return_value="mocked_token",
        ):
            result, credentials = self.svc._step_auth_injection(
                profile, profile.auth_config
            )
        assert result.passed is True
        assert "_profile_id" in credentials

    def test_fail_oauth_cc_token_fetch_error(self):
        from api_connector.services.oauth_cc_token import OAuthCCTokenFetchError

        profile = make_profile(auth_type=AuthType.OAUTH_CC)
        with patch(
            "api_connector.services.oauth_cc_token.OAuthCCTokenService.get_token",
            side_effect=OAuthCCTokenFetchError("Token endpoint returned HTTP 401"),
        ):
            result, _ = self.svc._step_auth_injection(profile, profile.auth_config)
        assert result.passed is False
        assert "token" in result.message.lower()


# ── HTTP Response Step ────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestStepHttpResponse:
    svc = ConnectionTestService()

    def test_pass_on_200(self, httpx_mock):
        profile = make_profile(auth_type=AuthType.NONE)
        httpx_mock.add_response(status_code=200, json={"ok": True})
        credentials = {"_profile_id": profile.pk}
        result, response = self.svc._step_http_response(
            profile.base_url, None, profile, credentials
        )
        assert result.passed is True
        assert result.detail["status_code"] == 200
        assert response is not None

    def test_fail_on_401(self, httpx_mock):
        profile = make_profile(auth_type=AuthType.NONE)
        httpx_mock.add_response(status_code=401, text="Unauthorized")
        credentials = {"_profile_id": profile.pk}
        result, response = self.svc._step_http_response(
            profile.base_url, None, profile, credentials
        )
        assert result.passed is False
        assert response is None
        assert "401" in result.message or "rejected" in result.message.lower()
        assert "suggested_action" in result.detail

    def test_fail_on_500(self, httpx_mock):
        profile = make_profile(auth_type=AuthType.NONE)
        httpx_mock.add_response(status_code=500, text="Internal Server Error")
        credentials = {"_profile_id": profile.pk}
        result, _ = self.svc._step_http_response(
            profile.base_url, None, profile, credentials
        )
        assert result.passed is False
        assert "500" in result.message or "server error" in result.message.lower()

    def test_url_construction_with_test_path(self, httpx_mock):
        profile = ConnectionProfileFactory(
            base_url="https://api.example.com", auth_type=AuthType.NONE
        )
        AuthConfigFactory(
            connection_profile=profile,
            encrypted_credentials=encryption_service.encrypt_dict({}),
        )
        httpx_mock.add_response(status_code=200, json={})
        credentials = {"_profile_id": profile.pk}
        self.svc._step_http_response(
            "https://api.example.com", "/v1/items", profile, credentials
        )
        sent = httpx_mock.get_request()
        assert "/v1/items" in str(sent.url)

    def test_fail_on_timeout(self, httpx_mock):
        profile = make_profile(auth_type=AuthType.NONE)
        httpx_mock.add_exception(httpx.ReadTimeout("timed out"))
        credentials = {"_profile_id": profile.pk}
        result, _ = self.svc._step_http_response(
            profile.base_url, None, profile, credentials
        )
        assert result.passed is False
        assert "timed out" in result.message.lower()


# ── Format Detection Step ─────────────────────────────────────────────────────


class TestStepFormatDetection:
    svc = ConnectionTestService()

    def _make_response(self, content_type=None, body="{}"):
        response = MagicMock(spec=httpx.Response)
        response.headers = {"content-type": content_type} if content_type else {}
        response.text = body
        return response

    def test_json_from_content_type(self):
        result, fmt = self.svc._step_format_detection(
            self._make_response(content_type="application/json; charset=utf-8")
        )
        assert result.passed is True
        assert fmt == "json"
        assert result.detail["source"] == "content_type_header"

    def test_json_from_body_sniff(self):
        result, fmt = self.svc._step_format_detection(
            self._make_response(content_type=None, body='{"items": []}')
        )
        assert fmt == "json"
        assert result.detail["source"] == "body_sniff"

    def test_xml_from_body_sniff(self):
        _, fmt = self.svc._step_format_detection(
            self._make_response(content_type=None, body="<?xml version='1.0'?><root/>")
        )
        assert fmt == "xml"

    def test_plain_text_fallback(self):
        _, fmt = self.svc._step_format_detection(
            self._make_response(content_type=None, body="some plain text here")
        )
        assert fmt == "plain_text"

    def test_csv_from_content_type(self):
        _, fmt = self.svc._step_format_detection(
            self._make_response(content_type="text/csv")
        )
        assert fmt == "csv"

    def test_always_passes(self):
        """Format detection never fails — even for unknown formats."""
        result, _ = self.svc._step_format_detection(
            self._make_response(
                content_type="application/octet-stream", body="\x00\x01\x02"
            )
        )
        assert result.passed is True


# ── Response Sample Step ──────────────────────────────────────────────────────


class TestStepResponseSample:
    svc = ConnectionTestService()

    def _make_response(self, body):
        response = MagicMock(spec=httpx.Response)
        response.text = body
        response.content = body.encode()
        return response

    def test_short_body_not_truncated(self):
        result = self.svc._step_response_sample(self._make_response('{"x": 1}'))
        assert result.passed is True
        assert result.detail["truncated"] is False
        assert result.detail["body_sample"] == '{"x": 1}'

    def test_long_body_truncated_to_2048_chars(self):
        long_body = "a" * 3000
        result = self.svc._step_response_sample(self._make_response(long_body))
        assert result.detail["truncated"] is True
        assert len(result.detail["body_sample"]) == 2048

    def test_body_size_bytes_is_raw_content_length(self):
        body = "hello"
        result = self.svc._step_response_sample(self._make_response(body))
        assert result.detail["body_size_bytes"] == len(body.encode())

    def test_always_passes(self):
        result = self.svc._step_response_sample(self._make_response(""))
        assert result.passed is True


# ── Full run() Orchestration ──────────────────────────────────────────────────


@pytest.mark.django_db
class TestConnectionTestServiceRun:
    def _mock_dns_success(self):
        return patch("socket.getaddrinfo", return_value=make_fake_dns_result("1.2.3.4"))

    def test_happy_path_all_6_steps_pass(self, httpx_mock):
        profile = make_profile(auth_type=AuthType.BEARER)
        # Step 1: DNS
        with self._mock_dns_success():
            # Step 2: network (200)
            httpx_mock.add_response(status_code=200, json={"ok": True})
            # Step 4: authenticated HTTP (200 with JSON)
            httpx_mock.add_response(
                status_code=200,
                json={"data": [1, 2, 3]},
                headers={"content-type": "application/json"},
            )
            svc = ConnectionTestService()
            result = svc.run(profile_id=profile.pk)

        assert result.overall_passed is True
        assert len(result.step_results) == 6
        assert all(s["passed"] for s in result.step_results)

        # Profile last_test_* fields updated
        profile.refresh_from_db()
        assert profile.last_test_outcome is True
        assert profile.last_test_at is not None
        assert profile.last_test_detected_format == "json"

    def test_early_exit_at_step_1_dns_failure(self):
        profile = make_profile(auth_type=AuthType.BEARER)
        with patch("socket.getaddrinfo", side_effect=socket.gaierror(8, "NX")):
            svc = ConnectionTestService()
            result = svc.run(profile_id=profile.pk)

        assert result.overall_passed is False
        assert len(result.step_results) == 1
        assert result.step_results[0]["name"] == DNS_RESOLUTION

        profile.refresh_from_db()
        assert profile.last_test_outcome is False
        assert profile.last_test_status_code is None

    def test_early_exit_at_step_2_network_failure(self, httpx_mock):
        profile = make_profile(auth_type=AuthType.BEARER)
        with self._mock_dns_success():
            httpx_mock.add_exception(HTTPTimeoutError("timeout", url="https://x.com"))
            svc = ConnectionTestService()
            result = svc.run(profile_id=profile.pk)

        assert result.overall_passed is False
        assert len(result.step_results) == 2
        assert result.step_results[1]["name"] == NETWORK_CONNECTIVITY
        assert result.step_results[1]["passed"] is False

    def test_profile_not_found_raises_does_not_exist(self):
        with pytest.raises(ConnectionProfile.DoesNotExist):
            ConnectionTestService().run(profile_id=99999)

    def test_last_test_status_code_from_step4(self, httpx_mock):
        profile = make_profile(auth_type=AuthType.NONE)
        with self._mock_dns_success():
            # Network connectivity check passes
            httpx_mock.add_response(status_code=200, json={})
            # Authenticated HTTP request gets 200
            httpx_mock.add_response(
                status_code=200,
                json={"ok": True},
                headers={"content-type": "application/json"},
            )
            ConnectionTestService().run(profile_id=profile.pk)

        profile.refresh_from_db()
        assert profile.last_test_status_code == 200
