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
    OAuthToken,
    PaginationConfig,
    PaginationStrategy,
    SchemaField,
    TokenType,
)
from api_connector.services.encryption import encryption_service


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


class OAuthTokenFactory(DjangoModelFactory):
    class Meta:
        model = OAuthToken

    connection_profile = factory.SubFactory(ConnectionProfileFactory)
    token_type = TokenType.OAUTH_CC
    # Fernet ciphertext of a dummy access token string
    encrypted_token = factory.LazyAttribute(
        lambda _: encryption_service.encrypt("dummy_access_token")
    )
    encrypted_refresh_token = None
    expires_at = None


class ConnectionTestResultFactory(DjangoModelFactory):
    class Meta:
        model = ConnectionTestResult

    connection_profile = factory.SubFactory(ConnectionProfileFactory)
    step_results = factory.LazyAttribute(
        lambda _: [
            {
                "name": "dns_resolution",
                "passed": True,
                "message": "Resolved.",
                "detail": {},
                "duration_ms": 10,
            },
            {
                "name": "network_connectivity",
                "passed": True,
                "message": "Connected.",
                "detail": {},
                "duration_ms": 20,
            },
            {
                "name": "auth_injection",
                "passed": True,
                "message": "Auth OK.",
                "detail": {},
                "duration_ms": 5,
            },
            {
                "name": "http_response",
                "passed": True,
                "message": "200 OK.",
                "detail": {
                    "status_code": 200,
                    "response_time_ms": 100,
                    "test_url": "https://api.example.com",
                },
                "duration_ms": 100,
            },
            {
                "name": "format_detection",
                "passed": True,
                "message": "JSON.",
                "detail": {"detected_format": "json", "source": "content_type_header"},
                "duration_ms": 2,
            },
            {
                "name": "response_sample",
                "passed": True,
                "message": "Captured.",
                "detail": {
                    "body_size_bytes": 20,
                    "truncated": False,
                    "body_sample": '{"data": []}',
                },
                "duration_ms": 1,
            },
        ]
    )
    overall_passed = True
    test_path = None
    duration_ms = 138
