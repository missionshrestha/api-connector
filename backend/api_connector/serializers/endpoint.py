# backend/api_connector/serializers/endpoint.py
r"""
Endpoint read, create, and update serializers.

Security (OWASP A03):
  data_root_path and record_count_path are dot-notation strings used to traverse
  API response JSON in Phases 6/7. Validated against ^[\w]+(\.[\w]+)*$ to prevent
  path-traversal-style confusion attacks.

ADR-009: detected_path_variables computed at read time from the stored path string.
  Source of truth is the path field — no separate PathVariable model needed.
"""

import re

from rest_framework import serializers

from api_connector.models import Endpoint, HTTPMethod, PaginationConfig

DOT_NOTATION_PATTERN = r"^[\w]+(\.[\w]+)*$"
PATH_VARIABLE_PATTERN = r"\{(\w+)\}"


class EndpointReadSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for list and retrieve responses.

    Computed fields:
      detected_path_variables: extracted from stored path at read time.
      has_pagination_config: boolean from one-to-one relation; avoids N+1
        when ViewSet queryset uses select_related('pagination_config').
    """

    detected_path_variables = serializers.SerializerMethodField()
    has_pagination_config = serializers.SerializerMethodField()

    def get_detected_path_variables(self, obj) -> list[str]:
        return re.findall(PATH_VARIABLE_PATTERN, obj.path)

    def get_has_pagination_config(self, obj) -> bool:
        try:
            return obj.pagination_config is not None
        except PaginationConfig.DoesNotExist:
            return False

    class Meta:
        model = Endpoint
        fields = [
            "id",
            "connection_profile",
            "name",
            "path",
            "method",
            "query_params",
            "path_variables",
            "request_body",
            "endpoint_headers",
            "response_format",
            "data_root_path",
            "record_count_path",
            "detected_path_variables",
            "has_pagination_config",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


def _validate_dot_notation(value: str | None, field_name: str) -> str | None:
    """Shared validator for data_root_path and record_count_path."""
    if value and not re.match(DOT_NOTATION_PATTERN, value):
        raise serializers.ValidationError(
            f"{field_name} must use dot-notation (e.g. 'data.items'). "
            f"No double dots, leading/trailing dots, or special characters."
        )
    return value


class EndpointCreateSerializer(serializers.ModelSerializer):
    """
    Write serializer for POST /api/connector/profiles/<profile_pk>/endpoints/.

    Validates:
      - path starts with '/'
      - method in [GET, POST]
      - request_body is null when method=GET
      - path_variables keys match {var} placeholders in path (no extra keys)
      - query_params each have non-empty key
      - endpoint_headers each have non-empty name
      - data_root_path and record_count_path match dot-notation pattern
    """

    class Meta:
        model = Endpoint
        fields = [
            "name",
            "path",
            "method",
            "query_params",
            "path_variables",
            "request_body",
            "endpoint_headers",
            "response_format",
            "data_root_path",
            "record_count_path",
        ]

    def validate_name(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("name cannot be blank.")
        return value

    def validate_path(self, value: str) -> str:
        if not value.startswith("/"):
            raise serializers.ValidationError(
                "path must start with '/'. Example: '/api/v1/items'"
            )
        return value

    def validate_query_params(self, value: list) -> list:
        for item in value:
            if not isinstance(item, dict):
                raise serializers.ValidationError(
                    "Each query_param must be an object with 'key' and 'value' strings."
                )
            if not item.get("key", "").strip():
                raise serializers.ValidationError("query_param 'key' cannot be empty.")
        return value

    def validate_endpoint_headers(self, value: list) -> list:
        for item in value:
            if not isinstance(item, dict):
                raise serializers.ValidationError(
                    "Each endpoint_header must be an object with 'name' and 'value' strings."
                )
            if not item.get("name", "").strip():
                raise serializers.ValidationError(
                    "endpoint_header 'name' cannot be empty."
                )
        return value

    def validate_data_root_path(self, value: str | None) -> str | None:
        return _validate_dot_notation(value, "data_root_path")

    def validate_record_count_path(self, value: str | None) -> str | None:
        return _validate_dot_notation(value, "record_count_path")

    def validate(self, data: dict) -> dict:
        method = data.get("method", HTTPMethod.GET)
        request_body = data.get("request_body")
        path = data.get("path", "")
        path_variables = data.get("path_variables", {})

        # request_body must be null for GET
        if method == HTTPMethod.GET and request_body is not None:
            raise serializers.ValidationError(
                {"request_body": "request_body must be null for GET endpoints."}
            )

        # path_variables keys must match {var} placeholders in path — no extra keys
        detected_vars = set(re.findall(PATH_VARIABLE_PATTERN, path))
        provided_keys = set(path_variables.keys())
        extra_keys = provided_keys - detected_vars
        if extra_keys:
            raise serializers.ValidationError(
                {
                    "path_variables": (
                        f"Keys {extra_keys} do not correspond to {{variable}} "
                        f"placeholders found in path '{path}'. "
                        f"Detected placeholders: {detected_vars or 'none'}"
                    )
                }
            )

        return data


class EndpointUpdateSerializer(serializers.ModelSerializer):
    """
    Write serializer for PATCH /api/connector/profiles/<profile_pk>/endpoints/<pk>/.

    All fields optional (supports partial PATCH).
    Same validations as EndpointCreateSerializer — applied only when fields are present.
    """

    class Meta:
        model = Endpoint
        fields = [
            "name",
            "path",
            "method",
            "query_params",
            "path_variables",
            "request_body",
            "endpoint_headers",
            "response_format",
            "data_root_path",
            "record_count_path",
        ]
        extra_kwargs = {
            field: {"required": False}
            for field in [
                "name",
                "path",
                "method",
                "query_params",
                "path_variables",
                "request_body",
                "endpoint_headers",
                "response_format",
                "data_root_path",
                "record_count_path",
            ]
        }

    def validate_name(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("name cannot be blank.")
        return value

    def validate_path(self, value: str) -> str:
        if not value.startswith("/"):
            raise serializers.ValidationError(
                "path must start with '/'. Example: '/api/v1/items'"
            )
        return value

    def validate_query_params(self, value: list) -> list:
        for item in value:
            if not isinstance(item, dict):
                raise serializers.ValidationError(
                    "Each query_param must be an object with 'key' and 'value' strings."
                )
            if not item.get("key", "").strip():
                raise serializers.ValidationError("query_param 'key' cannot be empty.")
        return value

    def validate_endpoint_headers(self, value: list) -> list:
        for item in value:
            if not isinstance(item, dict):
                raise serializers.ValidationError(
                    "Each endpoint_header must be an object with 'name' and 'value' strings."
                )
            if not item.get("name", "").strip():
                raise serializers.ValidationError(
                    "endpoint_header 'name' cannot be empty."
                )
        return value

    def validate_data_root_path(self, value: str | None) -> str | None:
        return _validate_dot_notation(value, "data_root_path")

    def validate_record_count_path(self, value: str | None) -> str | None:
        return _validate_dot_notation(value, "record_count_path")

    def validate(self, data: dict) -> dict:
        # Only cross-field validate if both relevant fields are present
        method = data.get("method") or (
            self.instance.method if self.instance else HTTPMethod.GET
        )
        path = data.get("path") or (self.instance.path if self.instance else "")
        path_variables = data.get("path_variables", {})

        if (
            method == HTTPMethod.GET
            and "request_body" in data
            and data["request_body"] is not None
        ):
            raise serializers.ValidationError(
                {"request_body": "request_body must be null for GET endpoints."}
            )

        if "path_variables" in data and "path" in data:
            import re as _re

            detected_vars = set(_re.findall(PATH_VARIABLE_PATTERN, path))
            provided_keys = set(path_variables.keys())
            extra_keys = provided_keys - detected_vars
            if extra_keys:
                raise serializers.ValidationError(
                    {
                        "path_variables": f"Keys {extra_keys} not found in path placeholders {detected_vars}."
                    }
                )

        return data


class PreviewRequestSerializer(serializers.Serializer):
    """
    Validates the request body for POST .../endpoints/<pk>/preview/.

    row_limit: integer 1–100, defaulting to 25.
    Validation happens before any DB or HTTP access — prevents large unintended fetches.
    """

    row_limit = serializers.IntegerField(
        min_value=1,
        max_value=100,
        default=25,
        required=False,
    )
