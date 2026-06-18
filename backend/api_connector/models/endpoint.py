# backend/api_connector/models/endpoint.py
from django.db import models

from api_connector.models.enums import HTTPMethod


class Endpoint(models.Model):
    """
    Represents a specific API endpoint within a ConnectionProfile.

    Security notes:
    - path_variables are static configuration values, NOT secrets. Do not encrypt.
    - request_body may contain API parameters. Users must not place credentials
      in request_body — document this clearly in Phase 8 user-facing docs.
    - data_root_path is used in Phase 6 to traverse response JSON. Validate
      dot-notation format at the serializer layer (Phase 5) to prevent
      path-traversal-style confusion attacks (OWASP A03).
    """

    connection_profile = models.ForeignKey(
        "api_connector.ConnectionProfile",
        on_delete=models.CASCADE,
        related_name="endpoints",
    )
    name = models.CharField(max_length=255)
    # May contain {variable} placeholders, e.g. /users/{user_id}/orders
    path = models.CharField(max_length=2048)
    method = models.CharField(
        max_length=4,
        choices=HTTPMethod.choices,
        default=HTTPMethod.GET,
    )
    # [{"key": str, "value": str}]
    query_params = models.JSONField(default=list, blank=True)
    # {"variable_name": "static_value"} — keys auto-detected from {var} in path (Phase 5)
    path_variables = models.JSONField(default=dict, blank=True)
    # Nullable; only valid when method=POST
    request_body = models.JSONField(null=True, blank=True)
    # [{"name": str, "value": str}]
    endpoint_headers = models.JSONField(default=list, blank=True)
    # Dot-notation path to the array of records, e.g. "data.items"
    data_root_path = models.CharField(max_length=500, null=True, blank=True)
    # Dot-notation path to total record count field
    record_count_path = models.CharField(max_length=500, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        unique_together = [["connection_profile", "name"]]
        db_table = "api_connector_endpoint"

    def __str__(self) -> str:
        return f"{self.method} {self.path} ({self.name})"
