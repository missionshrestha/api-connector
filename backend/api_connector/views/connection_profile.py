# backend/api_connector/views/connection_profile.py
import base64
import hashlib
import logging
import secrets
import urllib.parse
import uuid
from datetime import timedelta

from cryptography.fernet import InvalidToken
from django.conf import settings
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from api_connector.error_codes import NOT_FOUND, UNEXPECTED_ERROR
from api_connector.models import AuthConfig, AuthType, ConnectionProfile, OAuthACState
from api_connector.serializers.connection_profile import (
    ConnectionProfileCreateSerializer,
    ConnectionProfileReadSerializer,
    ConnectionProfileUpdateSerializer,
)
from api_connector.serializers.connection_test import (
    ConnectionTestRequestSerializer,
    ConnectionTestResultSerializer,
)
from api_connector.services.connection_test import ConnectionTestService
from api_connector.services.encryption import encryption_service

logger = logging.getLogger("api_connector.views")


class ConnectionProfileViewSet(viewsets.ModelViewSet):
    """
    Full CRUD for ConnectionProfile + connection test action.

    URL: /api/connector/profiles/
    Registered via DefaultRouter in api_connector/urls.py.

    Serializer dispatch:
      list, retrieve → ConnectionProfileReadSerializer (no secrets)
      create         → ConnectionProfileCreateSerializer (encrypts credentials)
      update, partial_update → ConnectionProfileUpdateSerializer (merges credentials)
      destroy        → uses default destroy() (no custom serializer needed)

    Security assumption [ASSUMPTION]:
      permission_classes = [AllowAny] assumes this module is deployed behind
      the host platform's authentication layer. Phase 8 security audit must
      confirm this or add an authentication class here.

    Performance:
      select_related('auth_config') prevents N+1 on the list endpoint.
      Without it, 50 profiles = 51 DB queries (1 for profiles + 50 for auth_configs).
      With it, always 1 query regardless of list size.

    Test endpoint: POST /api/connector/profiles/{id}/test/

    [ASSUMPTION] permission_classes = [AllowAny] assumes host-platform auth.
    Phase 8 security audit must confirm or add an authentication class.

    """

    permission_classes = [AllowAny]
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    def get_queryset(self):
        queryset = (
            ConnectionProfile.objects.select_related("auth_config")
            .prefetch_related("oauth_tokens")
            .order_by("-created_at")
        )
        # ?search= filters by name (case-insensitive, parameterized — injection-safe)
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search.strip())
        return queryset

    def get_serializer_class(self):
        if self.action in ["list", "retrieve"]:
            return ConnectionProfileReadSerializer
        elif self.action == "create":
            return ConnectionProfileCreateSerializer
        else:
            # update, partial_update, destroy
            return ConnectionProfileUpdateSerializer

    def create(self, request, *args, **kwargs):
        write_serializer = ConnectionProfileCreateSerializer(data=request.data)
        write_serializer.is_valid(raise_exception=True)
        instance = write_serializer.save()
        # Use ReadSerializer for the response so credentials_summary is included
        read_serializer = ConnectionProfileReadSerializer(instance)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="oauth/initiate")
    def oauth_initiate(self, request, pk=None):
        """
        GET /api/connector/profiles/{id}/oauth/initiate/

        Generates a PKCE pair and CSRF state record, constructs the provider
        authorization URL, and returns it to the frontend.

        Query parameters:
          redirect_origin (optional): the frontend origin for postMessage targeting.
            Must be in settings.CORS_ALLOWED_ORIGINS. Defaults to first CORS origin.

        Returns:
          {"authorization_url": "...", "state": "..."}

        Security (OWASP A07 — CSRF): state is UUID4, stored in OAuthACState.
        Security (RFC 7636 — PKCE): code_verifier never leaves the server;
          code_challenge is included in the authorization URL.
        """
        profile = self.get_object()

        if profile.auth_type != AuthType.OAUTH_AC:
            return Response(
                {
                    "error_code": "API_CONN_001",
                    "message": (
                        "OAuth initiation is only available for profiles "
                        "with auth_type='oauth_ac'."
                    ),
                    "detail": {"auth_type": profile.auth_type},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate and resolve redirect_origin
        requested_origin = request.query_params.get("redirect_origin", "").strip()
        allowed_origins = getattr(settings, "CORS_ALLOWED_ORIGINS", [])
        if requested_origin and requested_origin in allowed_origins:
            redirect_origin = requested_origin
        elif allowed_origins:
            redirect_origin = allowed_origins[0]
        else:
            redirect_origin = ""

        # Decrypt OAuth AC credentials
        try:
            auth_config = profile.auth_config
            credentials = encryption_service.decrypt_to_dict(
                auth_config.encrypted_credentials
            )
        except (AuthConfig.DoesNotExist, InvalidToken):
            return Response(
                {
                    "error_code": "API_CONN_012",
                    "message": (
                        "OAuth AC credentials are missing or corrupt. "
                        "Edit the profile and re-enter credentials."
                    ),
                    "detail": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        required_fields = ["client_id", "authorization_endpoint", "token_endpoint"]
        missing = [f for f in required_fields if not credentials.get(f)]
        if missing:
            return Response(
                {
                    "error_code": "API_CONN_001",
                    "message": (
                        f"Missing required OAuth AC credential fields: "
                        f"{', '.join(missing)}. Edit the profile and save."
                    ),
                    "detail": {"missing_fields": missing},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Generate PKCE pair (RFC 7636)
        code_verifier = secrets.token_urlsafe(96)  # ~128 chars; within 43-128 limit
        code_challenge = (
            base64.urlsafe_b64encode(
                hashlib.sha256(code_verifier.encode("ascii")).digest()
            )
            .rstrip(b"=")
            .decode("ascii")
        )

        # Create state record (10-minute expiry)
        state_value = str(uuid.uuid4())
        OAuthACState.objects.create(
            connection_profile=profile,
            state=state_value,
            pkce_code_verifier=code_verifier,
            pkce_code_challenge=code_challenge,
            redirect_origin=redirect_origin,
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        # Build authorization URL
        params = {
            "client_id": credentials["client_id"],
            "redirect_uri": settings.OAUTH_REDIRECT_URI,
            "response_type": "code",
            "state": state_value,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        if credentials.get("scopes"):
            params["scope"] = credentials["scopes"]

        authorization_url = (
            credentials["authorization_endpoint"].rstrip("/")
            + "?"
            + urllib.parse.urlencode(params)
        )

        logger.info(
            "OAuth AC initiate for profile=%s — state created, PKCE generated",
            profile.pk,
        )

        return Response(
            {"authorization_url": authorization_url, "state": state_value},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="test")
    def test_connection(self, request, pk=None):
        """
        POST /api/connector/profiles/{id}/test/

        Runs ConnectionTestService.run() for the profile and returns the result.

        Security note [SSRF]: This endpoint makes outbound HTTP calls to user-configured
        base_url values. Phase 8 security audit must evaluate whether SSRF protection
        (blocking RFC 1918 ranges) is required in this deployment context.
        """
        # Validate request body
        request_serializer = ConnectionTestRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        test_path = request_serializer.validated_data.get("test_path")

        # get_object() applies get_queryset() (select_related) + 404 handling
        profile = self.get_object()

        logger.info(
            "ConnectionTest requested for profile=%s test_path=%s",
            profile.pk,
            test_path or "(base URL)",
        )

        try:
            service = ConnectionTestService()
            result = service.run(profile_id=profile.pk, test_path=test_path)
        except ConnectionProfile.DoesNotExist:
            return Response(
                {
                    "error_code": NOT_FOUND,
                    "message": "Profile not found.",
                    "detail": {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception:
            logger.exception(
                "Unexpected error during connection test for profile=%s", profile.pk
            )
            return Response(
                {
                    "error_code": UNEXPECTED_ERROR,
                    "message": "An unexpected error occurred during the connection test.",
                    "detail": {},
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        result_serializer = ConnectionTestResultSerializer(instance=result)
        return Response(result_serializer.data, status=status.HTTP_200_OK)
