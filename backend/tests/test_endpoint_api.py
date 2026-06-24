# backend/tests/test_endpoint_api.py
"""
Endpoint API integration tests through the full HTTP stack.

Cross-profile isolation test is the most critical security test here.
"""

import pytest

from api_connector.models import Endpoint
from tests.factories import (
    ConnectionProfileFactory,
    EndpointFactory,
    PaginationConfigFactory,
    SchemaFieldFactory,
)

BASE_URL = "/api/connector/profiles/{profile_pk}/endpoints/"


@pytest.mark.django_db
class TestEndpointList:
    def test_empty_list_returns_200(self, api_client, assert_no_credential_leak):
        profile = ConnectionProfileFactory()
        response = api_client.get(BASE_URL.format(profile_pk=profile.pk))
        assert response.status_code == 200
        assert response.data == []
        assert_no_credential_leak(response)

    def test_list_scoped_to_profile(self, api_client, assert_no_credential_leak):
        profile1 = ConnectionProfileFactory()
        profile2 = ConnectionProfileFactory()
        EndpointFactory(connection_profile=profile1, name="EP1")
        EndpointFactory(connection_profile=profile2, name="EP2")

        response = api_client.get(BASE_URL.format(profile_pk=profile1.pk))
        assert response.status_code == 200
        assert len(response.data) == 1
        assert response.data[0]["name"] == "EP1"
        assert_no_credential_leak(response)

    def test_unknown_profile_returns_404(self, api_client, assert_no_credential_leak):
        response = api_client.get(BASE_URL.format(profile_pk=99999))
        assert response.status_code == 404
        assert_no_credential_leak(response)


@pytest.mark.django_db
class TestEndpointCreate:
    def test_create_get_endpoint_returns_201(
        self, api_client, assert_no_credential_leak
    ):
        profile = ConnectionProfileFactory()
        payload = {"name": "List Users", "path": "/api/v1/users", "method": "GET"}
        response = api_client.post(
            BASE_URL.format(profile_pk=profile.pk), payload, format="json"
        )
        assert response.status_code == 201
        assert response.data["detected_path_variables"] == []
        assert response.data["has_pagination_config"] is False
        assert_no_credential_leak(response)

    def test_create_endpoint_with_path_variable(
        self, api_client, assert_no_credential_leak
    ):
        profile = ConnectionProfileFactory()
        payload = {
            "name": "Get User",
            "path": "/users/{user_id}",
            "method": "GET",
            "path_variables": {"user_id": "42"},
        }
        response = api_client.post(
            BASE_URL.format(profile_pk=profile.pk), payload, format="json"
        )
        assert response.status_code == 201
        assert response.data["detected_path_variables"] == ["user_id"]
        assert_no_credential_leak(response)

    def test_get_with_request_body_returns_400(
        self, api_client, assert_no_credential_leak
    ):
        profile = ConnectionProfileFactory()
        response = api_client.post(
            BASE_URL.format(profile_pk=profile.pk),
            {"name": "Bad", "path": "/api", "method": "GET", "request_body": {"x": 1}},
            format="json",
        )
        assert response.status_code == 400
        assert response.data["error_code"] == "API_CONN_001"
        assert_no_credential_leak(response)

    def test_create_sets_correct_connection_profile(self, api_client):
        profile = ConnectionProfileFactory()
        api_client.post(
            BASE_URL.format(profile_pk=profile.pk),
            {"name": "EP", "path": "/api", "method": "GET"},
            format="json",
        )
        ep = Endpoint.objects.get(connection_profile=profile)
        assert ep.connection_profile_id == profile.pk


@pytest.mark.django_db
class TestEndpointCrossProfileIsolation:
    def test_cannot_access_other_profiles_endpoint(
        self, api_client, assert_no_credential_leak
    ):
        """SECURITY: cross-profile isolation via get_queryset() profile_pk filter."""
        profile1 = ConnectionProfileFactory()
        profile2 = ConnectionProfileFactory()
        ep2 = EndpointFactory(connection_profile=profile2)

        # Attempt to access profile2's endpoint via profile1's URL
        response = api_client.get(
            f"/api/connector/profiles/{profile1.pk}/endpoints/{ep2.pk}/"
        )
        assert response.status_code == 404
        assert_no_credential_leak(response)


@pytest.mark.django_db
class TestEndpointUpdate:
    def test_patch_name_only_returns_200(self, api_client, assert_no_credential_leak):
        profile = ConnectionProfileFactory()
        ep = EndpointFactory(connection_profile=profile, name="Old Name", path="/api")
        response = api_client.patch(
            f"/api/connector/profiles/{profile.pk}/endpoints/{ep.pk}/",
            {"name": "New Name"},
            format="json",
        )
        assert response.status_code == 200
        assert response.data["name"] == "New Name"
        assert response.data["path"] == "/api"  # unchanged
        assert_no_credential_leak(response)


@pytest.mark.django_db
class TestEndpointDelete:
    def test_delete_returns_204_and_cascades(self, api_client):
        profile = ConnectionProfileFactory()
        ep = EndpointFactory(connection_profile=profile)
        PaginationConfigFactory(endpoint=ep)
        SchemaFieldFactory(endpoint=ep)

        response = api_client.delete(
            f"/api/connector/profiles/{profile.pk}/endpoints/{ep.pk}/"
        )
        assert response.status_code == 204
        assert Endpoint.objects.filter(pk=ep.pk).count() == 0
