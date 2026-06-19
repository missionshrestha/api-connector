# backend/tests/factories.py
import factory
from factory.django import DjangoModelFactory

from api_connector.models import (
    AuthConfig,
    AuthType,
    ConnectionProfile,
    ConnectionTestResult,
    Endpoint,
    HTTPMethod,
    InferredType,
    PaginationConfig,
    PaginationStrategy,
    SchemaField,
)


class ConnectionProfileFactory(DjangoModelFactory):
    class Meta:
        model = ConnectionProfile

    name = factory.Sequence(lambda n: f"Test Profile {n}")
    base_url = "https://api.example.com"
    auth_type = AuthType.NONE
    ssl_verify = True
    request_timeout = 30


class AuthConfigFactory(DjangoModelFactory):
    class Meta:
        model = AuthConfig

    connection_profile = factory.SubFactory(ConnectionProfileFactory)
    # DUMMY blob — structural tests only. Tests that call EncryptionService.decrypt()
    # on this will fail intentionally. Use EncryptionService.encrypt_dict() to produce
    # a real blob when testing decryption paths.
    encrypted_credentials = factory.LazyAttribute(
        lambda _: {"blob": "DUMMY_ENCRYPTED_BLOB"}
    )


class EndpointFactory(DjangoModelFactory):
    class Meta:
        model = Endpoint

    connection_profile = factory.SubFactory(ConnectionProfileFactory)
    name = factory.Sequence(lambda n: f"Endpoint {n}")
    path = "/api/v1/items"
    method = HTTPMethod.GET


class PaginationConfigFactory(DjangoModelFactory):
    class Meta:
        model = PaginationConfig

    endpoint = factory.SubFactory(EndpointFactory)
    strategy = PaginationStrategy.NO_PAGINATION


class SchemaFieldFactory(DjangoModelFactory):
    class Meta:
        model = SchemaField

    endpoint = factory.SubFactory(EndpointFactory)
    key_path = factory.Sequence(lambda n: f"field_{n}")
    inferred_type = InferredType.STRING
    include = True


class ConnectionTestResultFactory(DjangoModelFactory):
    class Meta:
        model = ConnectionTestResult

    connection_profile = factory.SubFactory(ConnectionProfileFactory)
    step_results = factory.LazyAttribute(lambda _: [])
    overall_passed = False
