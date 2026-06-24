# backend/tests/test_schema_api.py
"""
Schema field management API integration tests.
SchemaInferenceEngine.infer() and upsert_fields() mocked in infer action tests.
"""
from unittest.mock import MagicMock, patch

import pytest

from api_connector.models import SchemaField
from api_connector.services.schema_inference.types import (
    SchemaFieldSpec,
    SchemaInferenceNoRecordsError,
)
from tests.factories import (
    AuthConfigFactory,
    ConnectionProfileFactory,
    EndpointFactory,
    SchemaFieldFactory,
)
from api_connector.services.encryption import encryption_service

BASE = "/api/connector/profiles/{ppk}/endpoints/{epk}/"
INFER_URL = BASE + "schema/infer/"
FIELDS_URL = BASE + "schema/fields/"
FIELD_URL = BASE + "schema/fields/{fpk}/"
BULK_URL = BASE + "schema/fields/bulk-update/"


def make_profile_endpoint():
    profile = ConnectionProfileFactory(auth_type="none")
    AuthConfigFactory(
        connection_profile=profile,
        encrypted_credentials=encryption_service.encrypt_dict({}),
    )
    endpoint = EndpointFactory(connection_profile=profile, path="/items")
    return profile, endpoint


# ── URL resolution ────────────────────────────────────────────────────────────

def test_schema_infer_url_resolves():
    from django.urls import reverse
    url = reverse("api_connector:endpoint-schema-infer", kwargs={"profile_pk": 1, "pk": 1})
    assert url == "/api/connector/profiles/1/endpoints/1/schema/infer/"


def test_schema_fields_url_resolves():
    from django.urls import reverse
    url = reverse("api_connector:endpoint-schema-fields", kwargs={"profile_pk": 1, "pk": 1})
    assert url == "/api/connector/profiles/1/endpoints/1/schema/fields/"


def test_schema_field_update_url_resolves():
    from django.urls import reverse
    url = reverse(
        "api_connector:endpoint-schema-field-update",
        kwargs={"profile_pk": 1, "pk": 1, "field_pk": 5},
    )
    assert url == "/api/connector/profiles/1/endpoints/1/schema/fields/5/"


def test_schema_fields_bulk_update_url_resolves():
    from django.urls import reverse
    url = reverse("api_connector:endpoint-schema-fields-bulk-update", kwargs={"profile_pk": 1, "pk": 1})
    assert url == "/api/connector/profiles/1/endpoints/1/schema/fields/bulk-update/"


# ── schema_infer action ───────────────────────────────────────────────────────

@pytest.mark.django_db
class TestSchemaInferAction:
    def _mock_engine(self, endpoint, fields):
        """Returns a patcher that mocks SchemaInferenceEngine with preset results."""
        specs = [
            SchemaFieldSpec(sf.key_path, sf.inferred_type, sf.null_percentage, sf.sample_value)
            for sf in fields
        ]
        mock_engine = MagicMock()
        mock_engine.infer.return_value = specs
        mock_engine.upsert_fields.return_value = fields
        return patch(
            "api_connector.views.endpoint.SchemaInferenceEngine",
            return_value=mock_engine,
        )

    def test_happy_path_returns_200_with_field_list(self, api_client, assert_no_credential_leak):
        profile, endpoint = make_profile_endpoint()
        sf = SchemaFieldFactory(endpoint=endpoint, key_path="id", inferred_type="integer")

        with self._mock_engine(endpoint, [sf]):
            response = api_client.post(
                INFER_URL.format(ppk=profile.pk, epk=endpoint.pk),
                data={},
                format="json",
            )

        assert response.status_code == 200
        assert isinstance(response.data, list)
        assert response.data[0]["key_path"] == "id"
        assert_no_credential_leak(response)

    def test_no_records_returns_422(self, api_client, assert_no_credential_leak):
        profile, endpoint = make_profile_endpoint()

        mock_engine = MagicMock()
        mock_engine.infer.side_effect = SchemaInferenceNoRecordsError("No records")
        with patch("api_connector.views.endpoint.SchemaInferenceEngine", return_value=mock_engine):
            response = api_client.post(
                INFER_URL.format(ppk=profile.pk, epk=endpoint.pk),
                data={},
                format="json",
            )

        assert response.status_code == 422
        assert response.data["error_code"] == "API_CONN_051"
        assert_no_credential_leak(response)

    def test_nonexistent_endpoint_returns_404(self, api_client, assert_no_credential_leak):
        profile, _ = make_profile_endpoint()
        response = api_client.post(
            INFER_URL.format(ppk=profile.pk, epk=99999),
            data={},
            format="json",
        )
        assert response.status_code == 404
        assert_no_credential_leak(response)


# ── schema_fields action ──────────────────────────────────────────────────────

@pytest.mark.django_db
class TestSchemaFieldsAction:
    def test_empty_returns_200_empty_list(self, api_client, assert_no_credential_leak):
        profile, endpoint = make_profile_endpoint()
        response = api_client.get(FIELDS_URL.format(ppk=profile.pk, epk=endpoint.pk))
        assert response.status_code == 200
        assert response.data == []
        assert_no_credential_leak(response)

    def test_returns_fields_ordered_by_key_path(self, api_client, assert_no_credential_leak):
        profile, endpoint = make_profile_endpoint()
        SchemaFieldFactory(endpoint=endpoint, key_path="z_last")
        SchemaFieldFactory(endpoint=endpoint, key_path="a_first")
        response = api_client.get(FIELDS_URL.format(ppk=profile.pk, epk=endpoint.pk))
        assert response.status_code == 200
        paths = [f["key_path"] for f in response.data]
        assert paths == sorted(paths)
        assert_no_credential_leak(response)

    def test_stale_fields_included(self, api_client, assert_no_credential_leak):
        profile, endpoint = make_profile_endpoint()
        SchemaFieldFactory(endpoint=endpoint, key_path="legacy", stale=True)
        SchemaFieldFactory(endpoint=endpoint, key_path="current", stale=False)
        response = api_client.get(FIELDS_URL.format(ppk=profile.pk, epk=endpoint.pk))
        stale_flags = {f["key_path"]: f["stale"] for f in response.data}
        assert stale_flags["legacy"] is True
        assert stale_flags["current"] is False
        assert_no_credential_leak(response)


# ── schema_field_update action ─────────────────────────────────────────────────

@pytest.mark.django_db
class TestSchemaFieldUpdateAction:
    def test_update_include_false_returns_200(self, api_client, assert_no_credential_leak):
        profile, endpoint = make_profile_endpoint()
        sf = SchemaFieldFactory(endpoint=endpoint, key_path="id", include=True)
        response = api_client.patch(
            FIELD_URL.format(ppk=profile.pk, epk=endpoint.pk, fpk=sf.pk),
            {"include": False},
            format="json",
        )
        assert response.status_code == 200
        sf.refresh_from_db()
        assert sf.include is False
        assert_no_credential_leak(response)

    def test_set_valid_alias_returns_200(self, api_client, assert_no_credential_leak):
        profile, endpoint = make_profile_endpoint()
        sf = SchemaFieldFactory(endpoint=endpoint, key_path="id")
        response = api_client.patch(
            FIELD_URL.format(ppk=profile.pk, epk=endpoint.pk, fpk=sf.pk),
            {"alias": "customer_id"},
            format="json",
        )
        assert response.status_code == 200
        sf.refresh_from_db()
        assert sf.alias == "customer_id"
        assert_no_credential_leak(response)

    def test_duplicate_alias_returns_400(self, api_client, assert_no_credential_leak):
        profile, endpoint = make_profile_endpoint()
        SchemaFieldFactory(endpoint=endpoint, key_path="id", alias="shared_name")
        sf2 = SchemaFieldFactory(endpoint=endpoint, key_path="name")
        response = api_client.patch(
            FIELD_URL.format(ppk=profile.pk, epk=endpoint.pk, fpk=sf2.pk),
            {"alias": "shared_name"},
            format="json",
        )
        assert response.status_code == 400
        assert response.data["error_code"] == "API_CONN_054"
        assert_no_credential_leak(response)

    def test_cross_endpoint_update_returns_404(self, api_client, assert_no_credential_leak):
        """SECURITY: field from endpoint B cannot be updated via endpoint A's URL."""
        profile = ConnectionProfileFactory(auth_type="none")
        AuthConfigFactory(connection_profile=profile, encrypted_credentials=encryption_service.encrypt_dict({}))
        ep_a = EndpointFactory(connection_profile=profile, name="A", path="/a")
        ep_b = EndpointFactory(connection_profile=profile, name="B", path="/b")
        sf_b = SchemaFieldFactory(endpoint=ep_b, key_path="id")

        response = api_client.patch(
            FIELD_URL.format(ppk=profile.pk, epk=ep_a.pk, fpk=sf_b.pk),
            {"include": False},
            format="json",
        )
        assert response.status_code == 404
        # sf_b must be unchanged
        sf_b.refresh_from_db()
        assert sf_b.include is True
        assert_no_credential_leak(response)

    def test_clear_alias_with_null(self, api_client, assert_no_credential_leak):
        profile, endpoint = make_profile_endpoint()
        sf = SchemaFieldFactory(endpoint=endpoint, key_path="id", alias="old_name")
        response = api_client.patch(
            FIELD_URL.format(ppk=profile.pk, epk=endpoint.pk, fpk=sf.pk),
            {"alias": None},
            format="json",
        )
        assert response.status_code == 200
        sf.refresh_from_db()
        assert sf.alias is None
        assert_no_credential_leak(response)


# ── schema_fields_bulk_update action ─────────────────────────────────────────

@pytest.mark.django_db
class TestBulkUpdateAction:
    def test_include_all_true_updates_all_fields(self, api_client):
        profile, endpoint = make_profile_endpoint()
        SchemaFieldFactory(endpoint=endpoint, key_path="a", include=False)
        SchemaFieldFactory(endpoint=endpoint, key_path="b", include=False)
        response = api_client.post(
            BULK_URL.format(ppk=profile.pk, epk=endpoint.pk),
            {"include_all": True},
            format="json",
        )
        assert response.status_code == 200
        assert response.data["updated_count"] == 2
        assert SchemaField.objects.filter(endpoint=endpoint, include=True).count() == 2

    def test_include_all_false_deselects_all(self, api_client):
        profile, endpoint = make_profile_endpoint()
        SchemaFieldFactory(endpoint=endpoint, key_path="a", include=True)
        SchemaFieldFactory(endpoint=endpoint, key_path="b", include=True)
        api_client.post(
            BULK_URL.format(ppk=profile.pk, epk=endpoint.pk),
            {"include_all": False},
            format="json",
        )
        assert SchemaField.objects.filter(endpoint=endpoint, include=False).count() == 2

    def test_field_ids_updates_only_specified_fields(self, api_client):
        profile, endpoint = make_profile_endpoint()
        sf1 = SchemaFieldFactory(endpoint=endpoint, key_path="a", include=True)
        sf2 = SchemaFieldFactory(endpoint=endpoint, key_path="b", include=True)
        api_client.post(
            BULK_URL.format(ppk=profile.pk, epk=endpoint.pk),
            {"field_ids": [sf1.pk], "include": False},
            format="json",
        )
        sf1.refresh_from_db()
        sf2.refresh_from_db()
        assert sf1.include is False
        assert sf2.include is True  # unchanged

    def test_field_ids_from_other_endpoint_not_updated(self, api_client):
        """Security: field_ids filtered by endpoint — other endpoint's fields untouched."""
        profile = ConnectionProfileFactory(auth_type="none")
        AuthConfigFactory(connection_profile=profile, encrypted_credentials=encryption_service.encrypt_dict({}))
        ep_a = EndpointFactory(connection_profile=profile, name="A", path="/a")
        ep_b = EndpointFactory(connection_profile=profile, name="B", path="/b")
        sf_b = SchemaFieldFactory(endpoint=ep_b, key_path="id", include=True)

        api_client.post(
            BULK_URL.format(ppk=profile.pk, epk=ep_a.pk),
            {"field_ids": [sf_b.pk], "include": False},
            format="json",
        )
        sf_b.refresh_from_db()
        assert sf_b.include is True  # untouched

    def test_neither_mode_returns_400(self, api_client):
        profile, endpoint = make_profile_endpoint()
        response = api_client.post(
            BULK_URL.format(ppk=profile.pk, epk=endpoint.pk),
            {},
            format="json",
        )
        assert response.status_code == 400