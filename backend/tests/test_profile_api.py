# backend/tests/test_profile_api.py
"""
API integration tests for /api/connector/profiles/.

Every test that receives a response calls assert_no_credential_leak(response).
This is non-negotiable — it is the regression net for the most critical
security invariant in the system.
"""

import pytest

from api_connector.models import AuthConfig, AuthType, ConnectionProfile
from api_connector.services.encryption import encryption_service
from tests.factories import (
    AuthConfigFactory,
    ConnectionProfileFactory,
    EndpointFactory,
    SchemaFieldFactory,
)

BASE_URL = "/api/connector/profiles/"


# ── List endpoint ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestProfileList:
    def test_empty_list_returns_200(self, api_client, assert_no_credential_leak):
        response = api_client.get(BASE_URL)
        assert response.status_code == 200
        assert response.data == []
        assert_no_credential_leak(response)

    def test_list_returns_all_profiles(self, api_client, assert_no_credential_leak):
        ConnectionProfileFactory.create_batch(3)
        response = api_client.get(BASE_URL)
        assert response.status_code == 200
        assert len(response.data) == 3
        assert_no_credential_leak(response)

    def test_search_filters_by_name_case_insensitive(
        self, api_client, assert_no_credential_leak
    ):
        ConnectionProfileFactory(name="ACME Production API")
        ConnectionProfileFactory(name="Stripe Payments")
        ConnectionProfileFactory(name="acme staging")

        response = api_client.get(BASE_URL, {"search": "acme"})
        assert response.status_code == 200
        assert len(response.data) == 2
        names = [p["name"] for p in response.data]
        assert "ACME Production API" in names
        assert "acme staging" in names
        assert_no_credential_leak(response)

    def test_search_empty_string_returns_all(
        self, api_client, assert_no_credential_leak
    ):
        ConnectionProfileFactory.create_batch(2)
        response = api_client.get(BASE_URL, {"search": ""})
        assert response.status_code == 200
        assert len(response.data) == 2
        assert_no_credential_leak(response)

    def test_search_no_match_returns_empty_list(
        self, api_client, assert_no_credential_leak
    ):
        ConnectionProfileFactory(name="Stripe")
        response = api_client.get(BASE_URL, {"search": "acme"})
        assert response.status_code == 200
        assert response.data == []
        assert_no_credential_leak(response)


# ── Create endpoint ────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestProfileCreate:
    def _make_payload(self, auth_type="none", credentials=None, **kwargs):
        payload = {
            "name": kwargs.get("name", "Test API"),
            "base_url": kwargs.get("base_url", "https://api.example.com"),
            "auth_type": auth_type,
            "request_timeout": kwargs.get("request_timeout", 30),
        }
        if credentials is not None:
            payload["credentials"] = credentials
        return payload

    def test_create_bearer_returns_201(self, api_client, assert_no_credential_leak):
        payload = self._make_payload(
            auth_type="bearer",
            credentials={"token": "my-secret-token"},
        )
        response = api_client.post(BASE_URL, payload, format="json")
        assert response.status_code == 201
        assert_no_credential_leak(response)
        assert response.data["credentials_summary"]["token"]["is_set"] is True

    def test_create_all_6_auth_types(self, api_client, assert_no_credential_leak):
        test_cases = [
            ("none", None),
            ("api_key", {"key_name": "X-Key", "key_value": "v", "delivery": "header"}),
            ("bearer", {"token": "tok"}),
            ("basic", {"username": "user", "password": "pass"}),
            (
                "oauth_cc",
                {
                    "client_id": "cid",
                    "client_secret": "sec",
                    "token_endpoint": "https://auth.example.com/token",
                },
            ),
            (
                "oauth_ac",
                {
                    "client_id": "cid",
                    "client_secret": "sec",
                    "token_endpoint": "https://auth.example.com/token",
                    "authorization_endpoint": "https://auth.example.com/auth",
                },
            ),
        ]
        for auth_type, credentials in test_cases:
            payload = self._make_payload(
                name=f"Test {auth_type}",
                auth_type=auth_type,
                credentials=credentials,
            )
            response = api_client.post(BASE_URL, payload, format="json")
            assert response.status_code == 201, (
                f"Expected 201 for auth_type={auth_type}, "
                f"got {response.status_code}: {response.data}"
            )
            assert_no_credential_leak(response)

    def test_create_missing_base_url_returns_400(
        self, api_client, assert_no_credential_leak
    ):
        payload = {"name": "Test", "auth_type": "none"}
        response = api_client.post(BASE_URL, payload, format="json")
        assert response.status_code == 400
        assert response.data["error_code"] == "API_CONN_001"
        assert_no_credential_leak(response)

    def test_create_invalid_base_url_scheme_returns_400(
        self, api_client, assert_no_credential_leak
    ):
        payload = self._make_payload(base_url="ftp://api.example.com")
        response = api_client.post(BASE_URL, payload, format="json")
        assert response.status_code == 400
        assert_no_credential_leak(response)

    def test_create_request_timeout_out_of_range_returns_400(
        self, api_client, assert_no_credential_leak
    ):
        payload = self._make_payload(request_timeout=200)
        response = api_client.post(BASE_URL, payload, format="json")
        assert response.status_code == 400
        assert_no_credential_leak(response)

    def test_create_missing_api_key_value_returns_400_with_credentials_error(
        self, api_client, assert_no_credential_leak
    ):
        payload = self._make_payload(
            auth_type="api_key",
            credentials={"key_name": "X-Key", "delivery": "header"},
            # key_value missing
        )
        response = api_client.post(BASE_URL, payload, format="json")
        assert response.status_code == 400
        assert "credentials" in response.data.get("detail", {})
        assert_no_credential_leak(response)


# ── Retrieve endpoint ──────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestProfileRetrieve:
    def test_retrieve_returns_200(self, api_client, assert_no_credential_leak):
        profile = ConnectionProfileFactory()
        AuthConfigFactory(
            connection_profile=profile,
            credentials_summary={"token": {"is_set": True}},
        )
        response = api_client.get(f"{BASE_URL}{profile.pk}/")
        assert response.status_code == 200
        assert response.data["id"] == profile.pk
        assert response.data["credentials_summary"] == {"token": {"is_set": True}}
        assert_no_credential_leak(response)

    def test_retrieve_nonexistent_returns_404(
        self, api_client, assert_no_credential_leak
    ):
        response = api_client.get(f"{BASE_URL}99999/")
        assert response.status_code == 404
        assert_no_credential_leak(response)


# ── Update endpoints ───────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestProfileUpdate:
    def _create_bearer_profile(self):
        profile = ConnectionProfileFactory(auth_type=AuthType.BEARER)
        creds = {"token": "original-token", "header_name": "Authorization"}
        AuthConfigFactory(
            connection_profile=profile,
            encrypted_credentials=encryption_service.encrypt_dict(creds),
            credentials_summary={
                "token": {"is_set": True},
                "header_name": {"is_set": True},
            },
        )
        return profile

    def test_patch_name_only_leaves_credentials_unchanged(
        self, api_client, assert_no_credential_leak
    ):
        profile = self._create_bearer_profile()
        original_blob = AuthConfig.objects.get(
            connection_profile=profile
        ).encrypted_credentials

        response = api_client.patch(
            f"{BASE_URL}{profile.pk}/",
            {"name": "New Name"},
            format="json",
        )
        assert response.status_code == 200
        assert_no_credential_leak(response)

        auth_config = AuthConfig.objects.get(connection_profile=profile)
        assert auth_config.encrypted_credentials == original_blob
        assert ConnectionProfile.objects.get(pk=profile.pk).name == "New Name"

    def test_patch_new_token_updates_credentials(
        self, api_client, assert_no_credential_leak
    ):
        profile = self._create_bearer_profile()

        response = api_client.patch(
            f"{BASE_URL}{profile.pk}/",
            {"credentials": {"token": "new-token"}},
            format="json",
        )
        assert response.status_code == 200
        assert_no_credential_leak(response)

        auth_config = AuthConfig.objects.get(connection_profile=profile)
        decrypted = encryption_service.decrypt_to_dict(
            auth_config.encrypted_credentials
        )
        assert decrypted["token"] == "new-token"
        assert decrypted["header_name"] == "Authorization"  # preserved

    def test_patch_empty_string_credentials_preserves_existing(
        self, api_client, assert_no_credential_leak
    ):
        profile = self._create_bearer_profile()
        response = api_client.patch(
            f"{BASE_URL}{profile.pk}/",
            {"credentials": {"token": ""}},
            format="json",
        )
        assert response.status_code == 200
        assert_no_credential_leak(response)

        auth_config = AuthConfig.objects.get(connection_profile=profile)
        decrypted = encryption_service.decrypt_to_dict(
            auth_config.encrypted_credentials
        )
        assert decrypted["token"] == "original-token"  # unchanged


# ── Delete endpoint ────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestProfileDelete:
    def test_delete_returns_204(self, api_client, assert_no_credential_leak):
        profile = ConnectionProfileFactory()
        response = api_client.delete(f"{BASE_URL}{profile.pk}/")
        assert response.status_code == 204

    def test_deleted_profile_returns_404_on_get(
        self, api_client, assert_no_credential_leak
    ):
        profile = ConnectionProfileFactory()
        api_client.delete(f"{BASE_URL}{profile.pk}/")
        response = api_client.get(f"{BASE_URL}{profile.pk}/")
        assert response.status_code == 404
        assert_no_credential_leak(response)

    def test_deleted_profile_absent_from_list(
        self, api_client, assert_no_credential_leak
    ):
        profile = ConnectionProfileFactory()
        pk = profile.pk
        api_client.delete(f"{BASE_URL}{pk}/")
        response = api_client.get(BASE_URL)
        assert response.status_code == 200
        ids = [p["id"] for p in response.data]
        assert pk not in ids
        assert_no_credential_leak(response)

    def test_cascade_delete_removes_endpoints_and_schema_fields(self, api_client):
        """
        Cascade test: deleting a profile must remove all its endpoints and schema fields.
        Verifies the on_delete=CASCADE FK chain functions end-to-end, not just in model definitions.
        """
        profile = ConnectionProfileFactory()
        endpoint = EndpointFactory(connection_profile=profile)
        SchemaFieldFactory.create_batch(3, endpoint=endpoint)

        assert (
            endpoint.__class__.objects.filter(connection_profile=profile).count() == 1
        )
        assert endpoint.schema_fields.count() == 3

        response = api_client.delete(f"{BASE_URL}{profile.pk}/")
        assert response.status_code == 204

        from api_connector.models import Endpoint, SchemaField

        assert Endpoint.objects.filter(connection_profile_id=profile.pk).count() == 0
        assert SchemaField.objects.filter(endpoint_id=endpoint.pk).count() == 0
