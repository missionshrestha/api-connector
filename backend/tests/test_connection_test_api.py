# backend/tests/test_connection_test_api.py
"""
API integration tests for POST /api/connector/profiles/{id}/test/.

ConnectionTestService.run() is mocked in all tests — no real outbound calls.
"""

from unittest.mock import patch

import pytest

from tests.factories import ConnectionProfileFactory, ConnectionTestResultFactory

TEST_URL = "/api/connector/profiles/{}/test/"


@pytest.mark.django_db
class TestConnectionTestEndpoint:
    def _mock_run(self, profile):
        """Return a patcher that mocks service.run() with a factory result."""
        test_result = ConnectionTestResultFactory(connection_profile=profile)
        return patch(
            "api_connector.views.connection_profile.ConnectionTestService",
            return_value=type("S", (), {"run": lambda *a, **kw: test_result})(),
        )

    def test_returns_200_with_result_structure(
        self, api_client, assert_no_credential_leak
    ):
        profile = ConnectionProfileFactory()
        with self._mock_run(profile):
            response = api_client.post(
                TEST_URL.format(profile.pk),
                data={},
                format="json",
            )
        assert response.status_code == 200
        data = response.data
        assert "result_id" in data
        assert "overall_passed" in data
        assert "steps" in data
        assert isinstance(data["steps"], list)
        assert "duration_ms" in data
        assert_no_credential_leak(response)

    def test_with_valid_test_path(self, api_client, assert_no_credential_leak):
        profile = ConnectionProfileFactory()
        with self._mock_run(profile):
            response = api_client.post(
                TEST_URL.format(profile.pk),
                data={"test_path": "/api/v1/health"},
                format="json",
            )
        assert response.status_code == 200
        assert_no_credential_leak(response)

    def test_invalid_test_path_returns_400(self, api_client, assert_no_credential_leak):
        profile = ConnectionProfileFactory()
        response = api_client.post(
            TEST_URL.format(profile.pk),
            data={"test_path": "no-leading-slash"},
            format="json",
        )
        assert response.status_code == 400
        assert response.data["error_code"] == "API_CONN_001"
        assert_no_credential_leak(response)

    def test_empty_body_uses_base_url(self, api_client, assert_no_credential_leak):
        """Empty body (no test_path) must succeed — test_path defaults to None."""
        profile = ConnectionProfileFactory()
        with self._mock_run(profile):
            response = api_client.post(
                TEST_URL.format(profile.pk),
                data={},
                format="json",
            )
        assert response.status_code == 200
        assert_no_credential_leak(response)

    def test_nonexistent_profile_returns_404(
        self, api_client, assert_no_credential_leak
    ):
        response = api_client.post(
            TEST_URL.format(99999),
            data={},
            format="json",
        )
        assert response.status_code == 404
        assert_no_credential_leak(response)

    def test_response_has_no_credential_data(
        self, api_client, assert_no_credential_leak
    ):
        profile = ConnectionProfileFactory()
        with self._mock_run(profile):
            response = api_client.post(
                TEST_URL.format(profile.pk),
                data={},
                format="json",
            )
        # Critical: no credential values in test result response
        response_str = str(response.data)
        assert "client_secret" not in response_str
        assert "encrypted" not in response_str
        assert_no_credential_leak(response)
