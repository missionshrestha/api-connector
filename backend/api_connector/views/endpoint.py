# backend/api_connector/views/endpoint.py
import logging

from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from api_connector.models import (
    ConnectionProfile,
    Endpoint,
    PaginationConfig,
    PaginationStrategy,
)
from api_connector.serializers.endpoint import (
    EndpointCreateSerializer,
    EndpointReadSerializer,
    EndpointUpdateSerializer,
)
from api_connector.serializers.pagination_config import (
    PaginationConfigReadSerializer,
    PaginationConfigUpdateSerializer,
)

logger = logging.getLogger("api_connector.views.endpoint")

# Default config returned when no PaginationConfig exists for an endpoint
_DEFAULT_PAGINATION_RESPONSE = {
    "strategy": PaginationStrategy.NO_PAGINATION,
    "strategy_params": {},
    "max_pages": 100,
    "max_records": 10000,
    "inter_page_delay_ms": 0,
    "max_retries": 3,
}


class EndpointViewSet(viewsets.ModelViewSet):
    """
    Endpoint CRUD + pagination config + data root detection.

    URL: /api/connector/profiles/<profile_pk>/endpoints/
    Pagination: GET/PATCH .../endpoints/<pk>/pagination/
    Data root: POST .../endpoints/<pk>/detect-data-root/

    [ASSUMPTION] AllowAny — host-platform auth assumed. Phase 8 must validate.
    """

    permission_classes = [AllowAny]
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    def get_queryset(self):
        profile_pk = self.kwargs["profile_pk"]
        get_object_or_404(ConnectionProfile, pk=profile_pk)
        return (
            Endpoint.objects.select_related("pagination_config")
            .filter(connection_profile_id=profile_pk)
            .order_by("name")
        )

    def get_serializer_class(self):
        if self.action in ["list", "retrieve"]:
            return EndpointReadSerializer
        elif self.action == "create":
            return EndpointCreateSerializer
        else:
            return EndpointUpdateSerializer

    def create(self, request, *args, **kwargs):
        profile_pk = self.kwargs["profile_pk"]
        write_serializer = EndpointCreateSerializer(data=request.data)
        write_serializer.is_valid(raise_exception=True)
        endpoint = write_serializer.save(connection_profile_id=profile_pk)
        read_serializer = EndpointReadSerializer(endpoint)
        logger.info(
            "Endpoint created: profile=%s endpoint=%s name='%s'",
            profile_pk,
            endpoint.pk,
            endpoint.name,
        )
        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        endpoint = self.get_object()
        logger.info(
            "Endpoint deleted: profile=%s endpoint=%s",
            self.kwargs["profile_pk"],
            endpoint.pk,
        )
        return super().destroy(request, *args, **kwargs)

    @action(
        detail=True,
        methods=["get", "patch"],
        url_path="pagination",
        url_name="pagination",
    )
    def pagination(self, request, profile_pk=None, pk=None):
        """
        GET  .../endpoints/<pk>/pagination/ — return config or defaults
        PATCH .../endpoints/<pk>/pagination/ — validate and upsert config
        """
        endpoint = self.get_object()

        if request.method == "GET":
            config = PaginationConfig.objects.filter(endpoint=endpoint).first()
            if config is None:
                return Response(
                    {**_DEFAULT_PAGINATION_RESPONSE, "endpoint": endpoint.pk},
                    status=status.HTTP_200_OK,
                )
            serializer = PaginationConfigReadSerializer(config)
            return Response(serializer.data)

        elif request.method == "PATCH":
            serializer = PaginationConfigUpdateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            config = serializer.save(endpoint=endpoint)
            logger.info(
                "PaginationConfig upserted: endpoint=%s strategy=%s",
                endpoint.pk,
                config.strategy,
            )
            read_serializer = PaginationConfigReadSerializer(config)
            return Response(read_serializer.data)

    @action(
        detail=True,
        methods=["post"],
        url_path="detect-data-root",
        url_name="detect-data-root",
    )
    def detect_data_root_action(self, request, profile_pk=None, pk=None):
        """
        POST .../endpoints/<pk>/detect-data-root/

        Makes ONE GET request to the endpoint's URL with auth injected.
        Parses the JSON response and returns candidate data root paths.

        Security (SSRF): makes outbound HTTP to user-configured URL.
        Phase 8 audit must evaluate RFC 1918 blocking requirement.
        """
        from cryptography.fernet import InvalidToken

        from api_connector.error_codes import (
            CREDENTIAL_ENCRYPTION_FAILED,
            DATA_ROOT_PATH_INVALID,
            TEST_HTTP_FAILURE,
            TEST_NETWORK_FAILURE,
        )
        from api_connector.services.auth.registry import auth_handler_registry
        from api_connector.services.encryption import encryption_service
        from api_connector.services.http_client import BaseHTTPClient
        from api_connector.services.http_exceptions import (
            HTTPNetworkError,
            HTTPStatusError,
            HTTPTimeoutError,
        )
        from api_connector.services.pagination.utils import (
            build_request_url,
            detect_data_root,
        )

        endpoint = self.get_object()
        profile = endpoint.connection_profile

        # Decrypt credentials
        try:
            credentials = encryption_service.decrypt_to_dict(
                profile.auth_config.encrypted_credentials
            )
            credentials["_profile_id"] = profile.pk
        except (InvalidToken, Exception):
            return Response(
                {
                    "error_code": CREDENTIAL_ENCRYPTION_FAILED,
                    "message": "Could not decrypt profile credentials.",
                    "detail": {},
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        auth_handler = auth_handler_registry.get(profile.auth_type)
        url = build_request_url(
            profile.base_url, endpoint.path, endpoint.path_variables
        )

        client = BaseHTTPClient(timeout=profile.request_timeout)
        try:
            response = client.get(
                url,
                auth_handler=auth_handler,
                credentials=credentials,
                ssl_verify=profile.ssl_verify,
            )
        except HTTPStatusError as exc:
            return Response(
                {
                    "error_code": TEST_HTTP_FAILURE,
                    "message": f"API returned HTTP {exc.status_code}.",
                    "detail": {"status_code": exc.status_code},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except (HTTPTimeoutError, HTTPNetworkError) as exc:
            return Response(
                {
                    "error_code": TEST_NETWORK_FAILURE,
                    "message": str(exc),
                    "detail": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            body = response.json()
        except Exception:
            return Response(
                {
                    "error_code": DATA_ROOT_PATH_INVALID,
                    "message": (
                        "API returned a non-JSON response — "
                        "data root path detection requires a JSON response."
                    ),
                    "detail": {},
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        candidates = detect_data_root(body)
        logger.info(
            "detect-data-root: endpoint=%s candidates=%s",
            endpoint.pk,
            candidates[:3],
        )
        return Response(
            {
                "top_candidate": candidates[0] if candidates else None,
                "all_candidates": candidates,
            }
        )
