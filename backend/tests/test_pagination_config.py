# backend/tests/test_pagination_config.py
"""
PaginationConfig serializer and API tests.
Critical: upsert test verifies second PATCH updates, doesn't create duplicate.
"""

import pytest

from api_connector.models import PaginationConfig
from api_connector.serializers.pagination_config import (
    OffsetLimitParamsSerializer,
    PaginationConfigUpdateSerializer,
)
from tests.factories import (
    ConnectionProfileFactory,
    EndpointFactory,
)

BASE = "/api/connector/profiles/{profile_pk}/endpoints/{ep_pk}/pagination/"


# ── Serializer unit tests ─────────────────────────────────────────────────────


class TestOffsetLimitParamsSerializer:
    def test_valid(self):
        s = OffsetLimitParamsSerializer(
            data={"offset_param": "offset", "limit_param": "limit", "page_size": 20}
        )
        assert s.is_valid(), s.errors

    def test_missing_page_size_invalid(self):
        s = OffsetLimitParamsSerializer(
            data={"offset_param": "offset", "limit_param": "limit"}
        )
        assert not s.is_valid()
        assert "page_size" in s.errors

    def test_page_size_zero_invalid(self):
        s = OffsetLimitParamsSerializer(
            data={"offset_param": "o", "limit_param": "l", "page_size": 0}
        )
        assert not s.is_valid()


class TestPaginationConfigUpdateSerializerDispatch:
    def test_strategy_mismatch_params_rejected(self):
        """offset_limit strategy with cursor params → rejected."""
        s = PaginationConfigUpdateSerializer(
            data={
                "strategy": "offset_limit",
                "strategy_params": {"cursor_request_param": "after"},  # wrong keys
            }
        )
        assert not s.is_valid()
        assert "strategy_params" in s.errors

    def test_no_pagination_empty_params_valid(self):
        s = PaginationConfigUpdateSerializer(
            data={"strategy": "no_pagination", "strategy_params": {}}
        )
        assert s.is_valid(), s.errors

    def test_safety_field_out_of_range_rejected(self):
        s = PaginationConfigUpdateSerializer(
            data={
                "strategy": "no_pagination",
                "strategy_params": {},
                "max_pages": 0,  # min_value=1
            }
        )
        assert not s.is_valid()
        assert "max_pages" in s.errors


# ── API integration tests ─────────────────────────────────────────────────────


@pytest.mark.django_db
class TestPaginationConfigAPI:
    def _url(self, profile_pk, ep_pk):
        return BASE.format(profile_pk=profile_pk, ep_pk=ep_pk)

    def test_get_returns_defaults_when_no_config(self, api_client):
        profile = ConnectionProfileFactory()
        ep = EndpointFactory(connection_profile=profile)
        response = api_client.get(self._url(profile.pk, ep.pk))
        assert response.status_code == 200
        assert response.data["strategy"] == "no_pagination"
        assert "max_pages" in response.data

    def test_patch_creates_config(self, api_client):
        profile = ConnectionProfileFactory()
        ep = EndpointFactory(connection_profile=profile)
        response = api_client.patch(
            self._url(profile.pk, ep.pk),
            {
                "strategy": "offset_limit",
                "strategy_params": {
                    "offset_param": "offset",
                    "limit_param": "limit",
                    "page_size": 20,
                },
            },
            format="json",
        )
        assert response.status_code == 200
        assert PaginationConfig.objects.filter(endpoint=ep).count() == 1

    def test_second_patch_updates_same_row(self, api_client):
        """Upsert: second PATCH must update, NOT create a second row."""
        profile = ConnectionProfileFactory()
        ep = EndpointFactory(connection_profile=profile)
        data = {
            "strategy": "offset_limit",
            "strategy_params": {
                "offset_param": "offset",
                "limit_param": "limit",
                "page_size": 20,
            },
        }
        api_client.patch(self._url(profile.pk, ep.pk), data, format="json")
        data["strategy_params"]["page_size"] = 50
        api_client.patch(self._url(profile.pk, ep.pk), data, format="json")

        assert PaginationConfig.objects.filter(endpoint=ep).count() == 1
        assert (
            PaginationConfig.objects.get(endpoint=ep).strategy_params["page_size"] == 50
        )

    def test_get_returns_stored_config_after_patch(self, api_client):
        profile = ConnectionProfileFactory()
        ep = EndpointFactory(connection_profile=profile)
        api_client.patch(
            self._url(profile.pk, ep.pk),
            {
                "strategy": "cursor",
                "strategy_params": {
                    "cursor_request_param": "after",
                    "cursor_response_path": "meta.next_cursor",
                },
                "max_pages": 50,
            },
            format="json",
        )
        response = api_client.get(self._url(profile.pk, ep.pk))
        assert response.status_code == 200
        assert response.data["strategy"] == "cursor"
        assert response.data["max_pages"] == 50

    def test_invalid_strategy_params_returns_400(self, api_client):
        profile = ConnectionProfileFactory()
        ep = EndpointFactory(connection_profile=profile)
        response = api_client.patch(
            self._url(profile.pk, ep.pk),
            {"strategy": "offset_limit", "strategy_params": {}},  # missing required
            format="json",
        )
        assert response.status_code == 400
