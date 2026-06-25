# backend/api_connector/views/endpoint.py
import logging

from cryptography.fernet import InvalidToken
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from api_connector.error_codes import (
    ALIAS_DUPLICATE,
    CREDENTIAL_ENCRYPTION_FAILED,
    PREVIEW_FETCH_FAILED,
    SCHEMA_INFERENCE_FAILED,
    SCHEMA_INFERENCE_NO_RECORDS,
    TEST_HTTP_FAILURE,
    TEST_NETWORK_FAILURE,
)
from api_connector.models import (
    ConnectionProfile,
    Endpoint,
    PaginationConfig,
    PaginationStrategy,
    SchemaField,
)
from api_connector.serializers.endpoint import (
    EndpointCreateSerializer,
    EndpointReadSerializer,
    EndpointUpdateSerializer,
    PreviewRequestSerializer,
)
from api_connector.serializers.pagination_config import (
    PaginationConfigReadSerializer,
    PaginationConfigUpdateSerializer,
)
from api_connector.serializers.schema_field import (
    SchemaFieldBulkUpdateSerializer,
    SchemaFieldReadSerializer,
    SchemaFieldUpdateSerializer,
)
from api_connector.services.auth.registry import auth_handler_registry
from api_connector.services.data_preview import (
    DataPreviewService,
    PreviewNoFieldsError,
)
from api_connector.services.encryption import encryption_service
from api_connector.services.http_exceptions import (
    HTTPNetworkError,
    HTTPStatusError,
    HTTPTimeoutError,
)
from api_connector.services.pagination.engine import PaginationEngineError
from api_connector.services.schema_inference import SchemaInferenceEngine

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

    # ─── Schema inference actions ──────────────────────────────────────────────

    @action(
        detail=True,
        methods=["post"],
        url_path="schema/infer",
        url_name="schema-infer",
    )
    def schema_infer(self, request, profile_pk=None, pk=None):
        """
        POST /api/connector/profiles/<profile_pk>/endpoints/<pk>/schema/infer/

        Fetches up to 300 records (3 pages) from the endpoint, runs type inference,
        and writes results to SchemaField records with stale/preservation logic.

        Security (SSRF): makes outbound HTTP. Phase 8 audit must evaluate RFC 1918 blocking.
        Synchronous — may take 5–15s. Phase 8 can convert to async task if needed.
        """
        from cryptography.fernet import InvalidToken

        from api_connector.services.auth.registry import auth_handler_registry
        from api_connector.services.encryption import encryption_service
        from api_connector.services.schema_inference.types import (
            SchemaInferenceError,
            SchemaInferenceNoRecordsError,
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
        engine = SchemaInferenceEngine()

        try:
            specs = engine.infer(endpoint, auth_handler, credentials)
        except SchemaInferenceNoRecordsError as exc:
            return Response(
                {
                    "error_code": SCHEMA_INFERENCE_NO_RECORDS,
                    "message": str(exc),
                    "detail": {},
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except SchemaInferenceError as exc:
            return Response(
                {
                    "error_code": SCHEMA_INFERENCE_FAILED,
                    "message": str(exc),
                    "detail": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        fields = engine.upsert_fields(endpoint, specs)
        logger.info(
            "schema_infer: endpoint=%s specs=%d",
            endpoint.pk,
            len(specs),
        )
        return Response(
            SchemaFieldReadSerializer(fields, many=True).data,
            status=status.HTTP_200_OK,
        )

    @action(
        detail=True,
        methods=["get"],
        url_path="schema/fields",
        url_name="schema-fields",
    )
    def schema_fields(self, request, profile_pk=None, pk=None):
        """
        GET /api/connector/profiles/<profile_pk>/endpoints/<pk>/schema/fields/

        Returns all SchemaField records for this endpoint ordered by key_path.
        Includes stale fields (they remain visible in the Explorer with greyed styling).
        Returns [] when no inference has been run — not 404.
        """
        endpoint = self.get_object()
        fields = SchemaField.objects.filter(endpoint=endpoint).order_by("key_path")
        return Response(
            SchemaFieldReadSerializer(fields, many=True).data,
            status=status.HTTP_200_OK,
        )

    @action(
        detail=True,
        methods=["patch"],
        url_path=r"schema/fields/(?P<field_pk>\d+)",
        url_name="schema-field-update",
    )
    def schema_field_update(
        self,
        request,
        profile_pk=None,
        pk=None,
        field_pk=None,
    ):
        """
        PATCH /api/connector/profiles/<profile_pk>/endpoints/<pk>/schema/fields/<field_pk>/

        Updates user-editable fields (alias, include, type_override, array_handling).
        Security boundary: field_pk filtered by endpoint — prevents cross-endpoint updates.
        """
        endpoint = self.get_object()
        schema_field = get_object_or_404(
            SchemaField,
            pk=field_pk,
            endpoint=endpoint,  # endpoint filter is security boundary
        )

        serializer = SchemaFieldUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        # Alias uniqueness check (requires endpoint context — done in view, not serializer)
        if validated.get("alias"):
            alias = validated["alias"]
            if (
                SchemaField.objects.filter(endpoint=endpoint, alias=alias)
                .exclude(pk=schema_field.pk)
                .exists()
            ):
                return Response(
                    {
                        "error_code": ALIAS_DUPLICATE,
                        "message": f"Alias '{alias}' is already used by another field in this endpoint.",
                        "detail": {"alias": alias},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Apply validated edits
        if "alias" in validated:
            schema_field.alias = validated["alias"]
        if "include" in validated:
            schema_field.include = validated["include"]
        if "type_override" in validated:
            schema_field.type_override = validated["type_override"]
        if "array_handling" in validated:
            schema_field.array_handling = validated["array_handling"]

        schema_field.save()
        return Response(
            SchemaFieldReadSerializer(schema_field).data,
            status=status.HTTP_200_OK,
        )

    @action(
        detail=True,
        methods=["post"],
        url_path="schema/fields/bulk-update",
        url_name="schema-fields-bulk-update",
    )
    def schema_fields_bulk_update(self, request, profile_pk=None, pk=None):
        """
        POST /api/connector/profiles/<profile_pk>/endpoints/<pk>/schema/fields/bulk-update/

        Batch include toggle. Always scoped to this endpoint — cannot update other endpoints' fields.
        Uses queryset.update() for atomic SQL UPDATE (not N individual saves).
        """
        endpoint = self.get_object()
        serializer = SchemaFieldBulkUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        base_qs = SchemaField.objects.filter(endpoint=endpoint)  # always scoped

        if "include_all" in validated:
            updated_count = base_qs.update(include=validated["include_all"])
        else:
            field_ids = validated["field_ids"]
            include = validated["include"]
            updated_count = base_qs.filter(pk__in=field_ids).update(include=include)

        logger.info(
            "bulk_update: endpoint=%s include_all=%s updated_count=%d",
            endpoint.pk,
            validated.get("include_all"),
            updated_count,
        )

        return Response(
            {"updated_count": updated_count},
            status=status.HTTP_200_OK,
        )

    @action(
        detail=True,
        methods=["post"],
        url_path="preview",
        url_name="preview",
    )
    def preview(self, request, profile_pk=None, pk=None):
        """
        POST /api/connector/profiles/<profile_pk>/endpoints/<pk>/preview/

        Fetches live API data, applies schema field selection + alias mapping,
        returns a typed preview result with column metadata.

        Request body: {"row_limit": int}  — 1–100, default 25
        Response: {
            "rows": [{column_name: value, ...}, ...],
            "columns": [{"name": str, "key_path": str, "effective_type": str,
                         "null_percentage": float, "sample_value": any}],
            "raw_response_body": str,   # last page JSON, truncated at 50KB
            "total_fetched": int,
            "has_more": bool,
        }

        Security (SSRF): makes outbound HTTP. Phase 8 audit must evaluate RFC 1918 blocking.
        Never logs rows, raw_response_body, or credential values (OWASP A09).
        """

        # Validate row_limit before touching DB or network
        request_serializer = PreviewRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        row_limit: int = request_serializer.validated_data["row_limit"]

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
        service = DataPreviewService()

        try:
            result = service.preview(
                endpoint=endpoint,
                auth_handler=auth_handler,
                credentials=credentials,
                row_limit=row_limit,
            )
        except PreviewNoFieldsError as exc:
            return Response(
                {
                    "error_code": SCHEMA_INFERENCE_NO_RECORDS,
                    "message": str(exc),
                    "detail": {},
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except (
            HTTPStatusError,
            HTTPTimeoutError,
            HTTPNetworkError,
            PaginationEngineError,
        ) as exc:
            return Response(
                {
                    "error_code": PREVIEW_FETCH_FAILED,
                    "message": f"API request failed during preview: {exc}",
                    "detail": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            logger.exception(
                "Unexpected error during preview for endpoint=%s", endpoint.pk
            )
            return Response(
                {
                    "error_code": "API_CONN_099",
                    "message": "An unexpected error occurred during the data preview.",
                    "detail": {},
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Assemble response — no ModelSerializer (rows have dynamic aliased keys)
        return Response(
            {
                "rows": result.rows,
                "columns": [
                    {
                        "name": c.name,
                        "key_path": c.key_path,
                        "effective_type": c.effective_type,
                        "null_percentage": c.null_percentage,
                        "sample_value": c.sample_value,
                    }
                    for c in result.columns
                ],
                "raw_response_body": result.raw_response_body,
                "total_fetched": result.total_fetched,
                "has_more": result.has_more,
            },
            status=status.HTTP_200_OK,
        )
