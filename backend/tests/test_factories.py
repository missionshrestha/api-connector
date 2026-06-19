# backend/tests/test_factories.py
import pytest

from tests.factories import (
    AuthConfigFactory,
    ConnectionProfileFactory,
    ConnectionTestResultFactory,
    EndpointFactory,
    PaginationConfigFactory,
    SchemaFieldFactory,
)


@pytest.mark.django_db
def test_connection_profile_factory():
    profile = ConnectionProfileFactory()
    assert profile.id is not None
    assert profile.auth_type == "none"
    assert profile.ssl_verify is True


@pytest.mark.django_db
def test_endpoint_factory_creates_profile():
    endpoint = EndpointFactory()
    assert endpoint.id is not None
    assert endpoint.connection_profile_id is not None
    # SubFactory auto-creates the parent
    assert endpoint.connection_profile.id is not None


@pytest.mark.django_db
def test_auth_config_factory():
    config = AuthConfigFactory()
    assert config.id is not None
    assert config.encrypted_credentials == {"blob": "DUMMY_ENCRYPTED_BLOB"}
    # Cascade: accessing through related_name
    assert config.connection_profile.auth_config == config


@pytest.mark.django_db
def test_all_factories_create_without_error():
    profile = ConnectionProfileFactory()
    AuthConfigFactory(connection_profile=profile)
    endpoint = EndpointFactory(connection_profile=profile)
    PaginationConfigFactory(endpoint=endpoint)
    SchemaFieldFactory(endpoint=endpoint)
    ConnectionTestResultFactory(connection_profile=profile)
    # Reaching here means all 6 factories work
    assert True
