# backend/api_connector/models/schema_field.py
from django.db import models

from api_connector.models.enums import ArrayHandling, InferredType


class SchemaField(models.Model):
    """
    Represents a discovered field in an Endpoint's response schema.

    Security notes:
    - sample_value may contain PII if the API returns personal data.
      Do not log sample_value contents. Phase 8 security audit covers this.
    - alias is user-controlled; validate length (max 64) and character set
      (alphanumeric, underscore, hyphen) at the serializer layer.

    [ASSUMPTION] The `stale` field is added in Phase 1 (rather than Phase 6) to
    avoid a post-initial migration. The Phase 1 spec omits it; the Expected Final
    State includes it. This deviation is documented in the Phase Completion Summary.
    """

    endpoint = models.ForeignKey(
        "api_connector.Endpoint",
        on_delete=models.CASCADE,
        related_name="schema_fields",
    )
    # Dot-notation path, e.g. "customer.address.city". Unique per endpoint.
    key_path = models.CharField(max_length=500)
    # User-defined output name. Unique per endpoint (enforced at serializer layer).
    alias = models.CharField(max_length=64, null=True, blank=True)
    inferred_type = models.CharField(
        max_length=30,
        choices=InferredType.choices,
        default=InferredType.STRING,
    )
    # null means "use inferred_type"
    type_override = models.CharField(
        max_length=30,
        choices=InferredType.choices,
        null=True,
        blank=True,
    )
    include = models.BooleanField(default=True)
    # Only relevant when inferred_type=ARRAY_OF_OBJECTS
    array_handling = models.CharField(
        max_length=10,
        choices=ArrayHandling.choices,
        null=True,
        blank=True,
    )
    # 0.0–1.0; fraction of records where this path was absent or None
    null_percentage = models.FloatField(default=0.0)
    # One non-null sample value; any JSON type
    sample_value = models.JSONField(null=True, blank=True)
    # True when path was present in a previous inference run but absent in latest
    stale = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key_path"]
        unique_together = [["endpoint", "key_path"]]
        indexes = [
            # Phase 7: SchemaField.objects.filter(endpoint=e, include=True)
            models.Index(fields=["endpoint", "include"]),
        ]
        db_table = "api_connector_schema_field"

    def __str__(self) -> str:
        return f"{self.key_path} ({self.inferred_type})"