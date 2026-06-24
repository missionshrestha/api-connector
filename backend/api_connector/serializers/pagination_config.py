# backend/api_connector/serializers/pagination_config.py
r"""
Pagination configuration serializers.

Six strategy-param serializers validate the per-strategy params dict.
PaginationConfigUpdateSerializer dispatches to the correct one in validate().

Security: strategy_params values are configuration, not secrets — safe to log.
dot-notation paths (total_pages_path, cursor_response_path, next_url_response_path)
validated against ^[\w]+(\.[\w]+)*$ to prevent confusion attacks (OWASP A03).
"""

import re

from rest_framework import serializers

from api_connector.models import Endpoint, PaginationConfig, PaginationStrategy

DOT_NOTATION_PATTERN = r"^[\w]+(\.[\w]+)*$"


def _validate_dot_notation_path(value: str | None, field_name: str) -> str | None:
    if value and not re.match(DOT_NOTATION_PATTERN, value):
        raise serializers.ValidationError(
            f"{field_name} must be dot-notation (e.g. 'meta.cursor'). "
            f"No double dots, leading/trailing dots, or special characters."
        )
    return value


# ── Per-strategy param validators (write-only, not ModelSerializers) ──────────


class NoPaginationParamsSerializer(serializers.Serializer):
    """No params required."""

    def validate(self, data):
        return {}


class OffsetLimitParamsSerializer(serializers.Serializer):
    offset_param = serializers.CharField(max_length=100)
    limit_param = serializers.CharField(max_length=100)
    page_size = serializers.IntegerField(min_value=1, max_value=10000)


class PageSizeParamsSerializer(serializers.Serializer):
    page_param = serializers.CharField(max_length=100)
    page_size_param = serializers.CharField(max_length=100)
    page_size = serializers.IntegerField(min_value=1)
    total_pages_path = serializers.CharField(
        max_length=500, required=False, allow_null=True, allow_blank=True
    )

    def validate_total_pages_path(self, value):
        return _validate_dot_notation_path(value, "total_pages_path")


class CursorParamsSerializer(serializers.Serializer):
    cursor_request_param = serializers.CharField(max_length=100)
    cursor_response_path = serializers.CharField(max_length=500)

    def validate_cursor_response_path(self, value):
        return _validate_dot_notation_path(value, "cursor_response_path")


class NextURLParamsSerializer(serializers.Serializer):
    next_url_response_path = serializers.CharField(max_length=500)

    def validate_next_url_response_path(self, value):
        return _validate_dot_notation_path(value, "next_url_response_path")


class LinkHeaderParamsSerializer(serializers.Serializer):
    """No params required — reads the RFC 5988 Link header automatically."""

    def validate(self, data):
        return {}


# ── Strategy param serializer map ─────────────────────────────────────────────

STRATEGY_PARAMS_SERIALIZER_MAP: dict[str, type[serializers.Serializer]] = {
    PaginationStrategy.NO_PAGINATION: NoPaginationParamsSerializer,
    PaginationStrategy.OFFSET_LIMIT: OffsetLimitParamsSerializer,
    PaginationStrategy.PAGE_SIZE: PageSizeParamsSerializer,
    PaginationStrategy.CURSOR: CursorParamsSerializer,
    PaginationStrategy.NEXT_URL: NextURLParamsSerializer,
    PaginationStrategy.LINK_HEADER: LinkHeaderParamsSerializer,
}


# ── Read serializer ───────────────────────────────────────────────────────────


class PaginationConfigReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaginationConfig
        fields = [
            "id",
            "endpoint",
            "strategy",
            "strategy_params",
            "max_pages",
            "max_records",
            "inter_page_delay_ms",
            "max_retries",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


# ── Update serializer ─────────────────────────────────────────────────────────


class PaginationConfigUpdateSerializer(serializers.Serializer):
    """
    Write serializer for PATCH .../pagination/.

    Validates strategy_params against the per-strategy validator in validate().
    save(endpoint) calls update_or_create — second PATCH updates, does not duplicate.
    """

    strategy = serializers.ChoiceField(choices=PaginationStrategy.choices)
    strategy_params = serializers.JSONField(default=dict)
    max_pages = serializers.IntegerField(min_value=1, default=100)
    max_records = serializers.IntegerField(min_value=1, default=10000)
    inter_page_delay_ms = serializers.IntegerField(
        min_value=0, max_value=30000, default=0
    )
    max_retries = serializers.IntegerField(min_value=0, max_value=10, default=3)

    def validate(self, data):
        strategy = data.get("strategy")
        strategy_params = data.get("strategy_params", {})

        serializer_class = STRATEGY_PARAMS_SERIALIZER_MAP.get(strategy)
        if serializer_class is None:
            raise serializers.ValidationError(
                {"strategy": f"Unknown strategy: {strategy!r}"}
            )

        params_serializer = serializer_class(data=strategy_params)
        if not params_serializer.is_valid():
            raise serializers.ValidationError(
                {"strategy_params": params_serializer.errors}
            )

        data["strategy_params"] = params_serializer.validated_data
        return data

    def save(self, endpoint: Endpoint) -> PaginationConfig:
        """Upsert pagination config — one record per endpoint (unique_together via OneToOneField)."""
        validated = self.validated_data
        config, _ = PaginationConfig.objects.update_or_create(
            endpoint=endpoint,
            defaults={
                "strategy": validated["strategy"],
                "strategy_params": validated["strategy_params"],
                "max_pages": validated["max_pages"],
                "max_records": validated["max_records"],
                "inter_page_delay_ms": validated["inter_page_delay_ms"],
                "max_retries": validated["max_retries"],
            },
        )
        return config
