# backend/api_connector/views/connection_profile.py
import logging

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from api_connector.error_codes import NOT_FOUND, UNEXPECTED_ERROR
from api_connector.models import ConnectionProfile
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
        queryset = ConnectionProfile.objects.select_related("auth_config").order_by(
            "-created_at"
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
