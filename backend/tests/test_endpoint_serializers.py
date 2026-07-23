# backend/tests/test_endpoint_serializers.py
"""
Endpoint serializer unit tests. No DB access where possible.
"""

import pytest

from api_connector.serializers.endpoint import (
    EndpointCreateSerializer,
    EndpointReadSerializer,
    EndpointUpdateSerializer,
)
from tests.factories import ConnectionProfileFactory, EndpointFactory

# ── EndpointCreateSerializer validation ──────────────────────────────────────


class TestEndpointCreateSerializerValidation:
    def test_valid_get_endpoint(self):
        s = EndpointCreateSerializer(
            data={
                "name": "List Items",
                "path": "/api/v1/items",
                "method": "GET",
            }
        )
        assert s.is_valid(), s.errors

    def test_valid_post_endpoint_with_body(self):
        s = EndpointCreateSerializer(
            data={
                "name": "Create Item",
                "path": "/api/v1/items",
                "method": "POST",
                "request_body": {"filter": "value"},
            }
        )
        assert s.is_valid(), s.errors

    def test_get_with_nonnull_request_body_rejected(self):
        s = EndpointCreateSerializer(
            data={
                "name": "Bad",
                "path": "/api",
                "method": "GET",
                "request_body": {"x": 1},
            }
        )
        assert not s.is_valid()
        assert "request_body" in str(s.errors)

    def test_path_without_leading_slash_rejected(self):
        s = EndpointCreateSerializer(
            data={
                "name": "Bad",
                "path": "api/v1",
                "method": "GET",
            }
        )
        assert not s.is_valid()
        assert "path" in s.errors

    def test_extra_path_variable_key_rejected(self):
        s = EndpointCreateSerializer(
            data={
                "name": "Test",
                "path": "/users/{user_id}",
                "method": "GET",
                "path_variables": {"user_id": "1", "extra_key": "bad"},
            }
        )
        assert not s.is_valid()
        assert "path_variables" in str(s.errors)

    def test_empty_query_param_key_rejected(self):
        s = EndpointCreateSerializer(
            data={
                "name": "Test",
                "path": "/api",
                "method": "GET",
                "query_params": [{"key": "", "value": "v"}],
            }
        )
        assert not s.is_valid()
        assert "query_params" in s.errors

    def test_empty_header_name_rejected(self):
        s = EndpointCreateSerializer(
            data={
                "name": "Test",
                "path": "/api",
                "method": "GET",
                "endpoint_headers": [{"name": "", "value": "v"}],
            }
        )
        assert not s.is_valid()
        assert "endpoint_headers" in s.errors

    def test_invalid_data_root_path_rejected(self):
        s = EndpointCreateSerializer(
            data={
                "name": "Test",
                "path": "/api",
                "method": "GET",
                "data_root_path": "data..items",  # double dot
            }
        )
        assert not s.is_valid()
        assert "data_root_path" in s.errors

    def test_path_traversal_data_root_path_rejected(self):
        """OWASP A03: path-traversal-style string must be rejected."""
        s = EndpointCreateSerializer(
            data={
                "name": "Test",
                "path": "/api",
                "method": "GET",
                "data_root_path": "../../etc/passwd",
            }
        )
        assert not s.is_valid()
        assert "data_root_path" in s.errors

    def test_explicit_response_format_xml_valid(self):
        s = EndpointCreateSerializer(
            data={
                "name": "Test",
                "path": "/api",
                "method": "GET",
                "response_format": "xml",
            }
        )
        assert s.is_valid(), s.errors

    def test_invalid_response_format_rejected(self):
        s = EndpointCreateSerializer(
            data={
                "name": "Test",
                "path": "/api",
                "method": "GET",
                "response_format": "yaml",
            }
        )
        assert not s.is_valid()
        assert "response_format" in s.errors

    def test_omitted_response_format_valid(self):
        """Defaulting decision is P2.C-04's job — the serializer itself just
        allows omission."""
        s = EndpointCreateSerializer(
            data={"name": "Test", "path": "/api", "method": "GET"}
        )
        assert s.is_valid(), s.errors
        assert "response_format" not in s.validated_data


@pytest.mark.django_db
class TestEndpointResponseFormatRoundTrip:
    def test_explicit_xml_persists_and_round_trips(self):
        profile = ConnectionProfileFactory()
        create_s = EndpointCreateSerializer(
            data={
                "name": "XML Endpoint",
                "path": "/api",
                "method": "GET",
                "response_format": "xml",
            }
        )
        assert create_s.is_valid(), create_s.errors
        endpoint = create_s.save(connection_profile=profile)
        assert endpoint.response_format == "xml"

        read_s = EndpointReadSerializer(instance=endpoint)
        assert read_s.data["response_format"] == "xml"

    def test_patch_updates_response_format(self):
        profile = ConnectionProfileFactory()
        endpoint = EndpointFactory(connection_profile=profile, response_format="json")
        update_s = EndpointUpdateSerializer(
            instance=endpoint, data={"response_format": "xml"}, partial=True
        )
        assert update_s.is_valid(), update_s.errors
        updated = update_s.save()
        assert updated.response_format == "xml"


# ── EndpointReadSerializer computed fields ────────────────────────────────────


@pytest.mark.django_db
class TestEndpointReadSerializerComputedFields:
    def test_detected_path_variables_zero_vars(self):
        profile = ConnectionProfileFactory()
        ep = EndpointFactory(connection_profile=profile, path="/api/v1/items")
        s = EndpointReadSerializer(instance=ep)
        assert s.data["detected_path_variables"] == []

    def test_detected_path_variables_one_var(self):
        profile = ConnectionProfileFactory()
        ep = EndpointFactory(connection_profile=profile, path="/users/{user_id}/orders")
        s = EndpointReadSerializer(instance=ep)
        assert s.data["detected_path_variables"] == ["user_id"]

    def test_detected_path_variables_two_vars(self):
        profile = ConnectionProfileFactory()
        ep = EndpointFactory(
            connection_profile=profile, path="/users/{user_id}/orders/{order_id}"
        )
        s = EndpointReadSerializer(instance=ep)
        assert set(s.data["detected_path_variables"]) == {"user_id", "order_id"}

    def test_has_pagination_config_false_when_no_config(self):
        profile = ConnectionProfileFactory()
        ep = EndpointFactory(connection_profile=profile)
        s = EndpointReadSerializer(instance=ep)
        assert s.data["has_pagination_config"] is False

    def test_has_pagination_config_true_when_config_exists(self):
        from tests.factories import PaginationConfigFactory

        profile = ConnectionProfileFactory()
        ep = EndpointFactory(connection_profile=profile)
        PaginationConfigFactory(endpoint=ep)
        # Re-fetch with select_related so pagination_config is loaded
        from api_connector.models import Endpoint

        ep_fresh = Endpoint.objects.select_related("pagination_config").get(pk=ep.pk)
        s = EndpointReadSerializer(instance=ep_fresh)
        assert s.data["has_pagination_config"] is True


# ── EndpointUpdateSerializer ──────────────────────────────────────────────────


class TestEndpointUpdateSerializer:
    def test_empty_data_is_valid(self):
        """Empty PATCH — all fields optional."""
        s = EndpointUpdateSerializer(data={})
        assert s.is_valid(), s.errors

    def test_partial_name_update_valid(self):
        s = EndpointUpdateSerializer(data={"name": "New Name"})
        assert s.is_valid(), s.errors
