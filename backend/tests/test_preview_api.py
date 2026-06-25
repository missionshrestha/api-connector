# backend/tests/test_preview_api.py
"""
Preview API integration tests for POST .../endpoints/<pk>/preview/.

DataPreviewService.preview() mocked in all tests — zero real HTTP calls.
Cross-profile isolation is the critical security check for this endpoint.
"""

from unittest.mock import MagicMock, patch

import pytest

from api_connector.services.data_preview import (
    ColumnMeta,
    PreviewNoFieldsError,
    PreviewResult,
)
from api_connector.services.encryption import encryption_service
from tests.factories import (
    AuthConfigFactory,
    ConnectionProfileFactory,
    EndpointFactory,
)

PREVIEW_URL = "/api/connector/profiles/{ppk}/endpoints/{epk}/preview/"


def make_auth_profile(auth_type="none"):
    profile = ConnectionProfileFactory(auth_type=auth_type)
    AuthConfigFactory(
        connection_profile=profile,
        encrypted_credentials=encryption_service.encrypt_dict({}),
    )
    return profile


def make_preview_result(**overrides):
    defaults = {
        "rows": [{"customer_id": 1, "name": "Alice"}],
        "columns": [
            ColumnMeta(
                name="customer_id",
                key_path="id",
                effective_type="integer",
                null_percentage=0.0,
                sample_value=1,
            ),
            ColumnMeta(
                name="name",
                key_path="name",
                effective_type="string",
                null_percentage=0.0,
                sample_value="Alice",
            ),
        ],
        "raw_response_body": '{"data": [{"id": 1, "name": "Alice"}]}',
        "total_fetched": 1,
        "has_more": False,
    }
    defaults.update(overrides)
    return PreviewResult(**defaults)


# ─── URL resolution ───────────────────────────────────────────────────────────


def test_preview_url_resolves():
    from django.urls import reverse

    url = reverse("api_connector:endpoint-preview", kwargs={"profile_pk": 1, "pk": 1})
    assert url == "/api/connector/profiles/1/endpoints/1/preview/"


# ─── row_limit validation ─────────────────────────────────────────────────────


@pytest.mark.django_db
class TestPreviewRowLimitValidation:
    def test_row_limit_zero_returns_400(self, api_client, assert_no_credential_leak):
        profile = make_auth_profile()
        endpoint = EndpointFactory(connection_profile=profile)
        response = api_client.post(
            PREVIEW_URL.format(ppk=profile.pk, epk=endpoint.pk),
            {"row_limit": 0},
            format="json",
        )
        assert response.status_code == 400
        assert response.data["error_code"] == "API_CONN_001"
        assert_no_credential_leak(response)

    def test_row_limit_101_returns_400(self, api_client, assert_no_credential_leak):
        profile = make_auth_profile()
        endpoint = EndpointFactory(connection_profile=profile)
        response = api_client.post(
            PREVIEW_URL.format(ppk=profile.pk, epk=endpoint.pk),
            {"row_limit": 101},
            format="json",
        )
        assert response.status_code == 400
        assert_no_credential_leak(response)

    def test_row_limit_100_is_valid_boundary(
        self, api_client, assert_no_credential_leak
    ):
        profile = make_auth_profile()
        endpoint = EndpointFactory(connection_profile=profile)
        with patch("api_connector.views.endpoint.DataPreviewService") as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.preview.return_value = make_preview_result()
            mock_svc_cls.return_value = mock_svc

            response = api_client.post(
                PREVIEW_URL.format(ppk=profile.pk, epk=endpoint.pk),
                {"row_limit": 100},
                format="json",
            )
        assert response.status_code == 200
        assert_no_credential_leak(response)

    def test_empty_body_defaults_row_limit_to_25(self, api_client):
        profile = make_auth_profile()
        endpoint = EndpointFactory(connection_profile=profile)
        with patch("api_connector.views.endpoint.DataPreviewService") as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.preview.return_value = make_preview_result()
            mock_svc_cls.return_value = mock_svc

            api_client.post(
                PREVIEW_URL.format(ppk=profile.pk, epk=endpoint.pk),
                {},
                format="json",
            )
            # Verify service was called with row_limit=25
            call_kwargs = mock_svc.preview.call_args
            assert call_kwargs.kwargs["row_limit"] == 25 or call_kwargs.args[3] == 25


# ─── Service error paths ──────────────────────────────────────────────────────


@pytest.mark.django_db
class TestPreviewErrorPaths:
    def test_no_included_fields_returns_422(
        self, api_client, assert_no_credential_leak
    ):
        profile = make_auth_profile()
        endpoint = EndpointFactory(connection_profile=profile)

        with patch("api_connector.views.endpoint.DataPreviewService") as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.preview.side_effect = PreviewNoFieldsError("No fields")
            mock_svc_cls.return_value = mock_svc

            response = api_client.post(
                PREVIEW_URL.format(ppk=profile.pk, epk=endpoint.pk),
                {"row_limit": 25},
                format="json",
            )

        assert response.status_code == 422
        assert response.data["error_code"] == "API_CONN_051"
        assert_no_credential_leak(response)

    def test_http_401_from_api_returns_400(self, api_client, assert_no_credential_leak):
        from api_connector.services.http_exceptions import HTTPStatusError

        profile = make_auth_profile()
        endpoint = EndpointFactory(connection_profile=profile)

        with patch("api_connector.views.endpoint.DataPreviewService") as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.preview.side_effect = HTTPStatusError(
                "HTTP 401", status_code=401, response_body="Unauthorized"
            )
            mock_svc_cls.return_value = mock_svc

            response = api_client.post(
                PREVIEW_URL.format(ppk=profile.pk, epk=endpoint.pk),
                {"row_limit": 10},
                format="json",
            )

        assert response.status_code == 400
        assert response.data["error_code"] == "API_CONN_053"
        assert_no_credential_leak(response)

    def test_network_timeout_returns_400(self, api_client, assert_no_credential_leak):
        from api_connector.services.http_exceptions import HTTPTimeoutError

        profile = make_auth_profile()
        endpoint = EndpointFactory(connection_profile=profile)

        with patch("api_connector.views.endpoint.DataPreviewService") as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.preview.side_effect = HTTPTimeoutError(
                "Timeout", url="https://x.com"
            )
            mock_svc_cls.return_value = mock_svc

            response = api_client.post(
                PREVIEW_URL.format(ppk=profile.pk, epk=endpoint.pk),
                {"row_limit": 10},
                format="json",
            )

        assert response.status_code == 400
        assert_no_credential_leak(response)

    def test_nonexistent_endpoint_returns_404(
        self, api_client, assert_no_credential_leak
    ):
        profile = make_auth_profile()
        response = api_client.post(
            PREVIEW_URL.format(ppk=profile.pk, epk=99999),
            {"row_limit": 25},
            format="json",
        )
        assert response.status_code == 404
        assert_no_credential_leak(response)


# ─── Happy path ───────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestPreviewHappyPath:
    def test_valid_preview_returns_200_with_result_structure(
        self, api_client, assert_no_credential_leak
    ):
        profile = make_auth_profile()
        endpoint = EndpointFactory(connection_profile=profile)

        with patch("api_connector.views.endpoint.DataPreviewService") as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.preview.return_value = make_preview_result()
            mock_svc_cls.return_value = mock_svc

            response = api_client.post(
                PREVIEW_URL.format(ppk=profile.pk, epk=endpoint.pk),
                {"row_limit": 25},
                format="json",
            )

        assert response.status_code == 200
        data = response.data
        assert "rows" in data
        assert "columns" in data
        assert "raw_response_body" in data
        assert "total_fetched" in data
        assert "has_more" in data
        assert isinstance(data["rows"], list)
        assert isinstance(data["columns"], list)
        assert isinstance(data["has_more"], bool)
        assert_no_credential_leak(response)

    def test_response_does_not_contain_encrypted_credentials(
        self, api_client, assert_no_credential_leak
    ):
        profile = make_auth_profile()
        endpoint = EndpointFactory(connection_profile=profile)

        with patch("api_connector.views.endpoint.DataPreviewService") as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.preview.return_value = make_preview_result()
            mock_svc_cls.return_value = mock_svc

            response = api_client.post(
                PREVIEW_URL.format(ppk=profile.pk, epk=endpoint.pk),
                {"row_limit": 25},
                format="json",
            )

        response_str = str(response.data)
        assert "blob" not in response_str
        assert "encrypted_credentials" not in response_str
        assert_no_credential_leak(response)

    def test_has_more_in_response(self, api_client, assert_no_credential_leak):
        profile = make_auth_profile()
        endpoint = EndpointFactory(connection_profile=profile)

        with patch("api_connector.views.endpoint.DataPreviewService") as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.preview.return_value = make_preview_result(
                has_more=True, total_fetched=25
            )
            mock_svc_cls.return_value = mock_svc

            response = api_client.post(
                PREVIEW_URL.format(ppk=profile.pk, epk=endpoint.pk),
                {"row_limit": 25},
                format="json",
            )

        assert response.data["has_more"] is True
        assert_no_credential_leak(response)


# ─── Cross-profile isolation (security) ──────────────────────────────────────


@pytest.mark.django_db
class TestPreviewCrossProfileIsolation:
    def test_endpoint_from_other_profile_returns_404(
        self, api_client, assert_no_credential_leak
    ):
        """SECURITY: endpoint from profile B cannot be previewed via profile A URL."""
        profile_a = make_auth_profile()
        profile_b = make_auth_profile()
        endpoint_b = EndpointFactory(connection_profile=profile_b, path="/secret")

        response = api_client.post(
            PREVIEW_URL.format(ppk=profile_a.pk, epk=endpoint_b.pk),
            {"row_limit": 10},
            format="json",
        )
        assert response.status_code == 404
        assert_no_credential_leak(response)
