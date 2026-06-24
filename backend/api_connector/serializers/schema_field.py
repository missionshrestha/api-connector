# backend/api_connector/serializers/schema_field.py
"""
Schema field serializers.

SchemaFieldReadSerializer — used for all GET responses.
SchemaFieldUpdateSerializer — validates per-field user edits (alias, include, etc.).
SchemaFieldBulkUpdateSerializer — validates batch include toggles.

Security: sample_value appears in read output (may contain PII from API response).
  Never log SchemaFieldReadSerializer output directly.
  The alias pattern ^[a-zA-Z0-9_-]+$ prevents control characters and shell-injection
  content in column headers that will be used in Phase 7 CSV export.
"""
import re

from rest_framework import serializers

from api_connector.models import ArrayHandling, InferredType, SchemaField

_ALIAS_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


class SchemaFieldReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = SchemaField
        fields = [
            "id",
            "endpoint",
            "key_path",
            "alias",
            "inferred_type",
            "type_override",
            "include",
            "array_handling",
            "null_percentage",
            "sample_value",
            "stale",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class SchemaFieldUpdateSerializer(serializers.Serializer):
    """
    Write-only validator for per-field user edits.
    Alias uniqueness check happens in the view (requires endpoint context).
    """

    alias = serializers.CharField(
        max_length=64, required=False, allow_null=True, allow_blank=True
    )
    include = serializers.BooleanField(required=False)
    type_override = serializers.ChoiceField(
        choices=[("", None)] + list(InferredType.choices),
        required=False,
        allow_null=True,
        allow_blank=True,
    )
    array_handling = serializers.ChoiceField(
        choices=ArrayHandling.choices,
        required=False,
        allow_null=True,
    )

    def validate_alias(self, value: str | None) -> str | None:
        if not value:
            return None
        stripped = value.strip()
        if not stripped:
            return None
        if not _ALIAS_PATTERN.match(stripped):
            raise serializers.ValidationError(
                "Alias must contain only letters, numbers, underscores, and hyphens."
            )
        if len(stripped) > 64:
            raise serializers.ValidationError("Alias must be 64 characters or fewer.")
        return stripped

    def validate_type_override(self, value):
        """Empty string means 'clear override' → normalize to None."""
        if value == "" or value is None:
            return None
        return value


class SchemaFieldBulkUpdateSerializer(serializers.Serializer):
    """
    Validates bulk include toggle operations.

    Two modes:
      Mode A — toggle ALL fields: {"include_all": true/false}
      Mode B — toggle specific fields: {"field_ids": [1,2,3], "include": true/false}
    """

    include_all = serializers.BooleanField(required=False)
    field_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False
    )
    include = serializers.BooleanField(required=False)

    def validate(self, data: dict) -> dict:
        has_include_all = "include_all" in data
        has_field_ids = "field_ids" in data
        has_include = "include" in data

        if not has_include_all and not (has_field_ids and has_include):
            raise serializers.ValidationError(
                "Provide 'include_all' (bool) OR both 'field_ids' (list) and "
                "'include' (bool)."
            )
        return data