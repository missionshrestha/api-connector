# backend/api_connector/models/connection_profile.py
from django.db import models

from api_connector.models.enums import AuthType


class ConnectionProfile(models.Model):
    """
    Represents a configured connection to a third-party API.

    Security notes:
    - base_url is NOT sensitive — it is the server hostname, not a credential.
      Do not encrypt or redact it.
    - default_headers is for non-secret headers (Content-Type, Accept).
      Headers containing secrets belong in AuthConfig, not here.
    - last_test_* fields store ONLY metadata (status code, timing, format).
      They must NEVER contain response body data — bodies may contain PII.
      See OWASP A02.
    """

    name = models.CharField(max_length=255)
    base_url = models.CharField(max_length=2048)
    auth_type = models.CharField(
        max_length=20,
        choices=AuthType.choices,
        default=AuthType.NONE,
    )
    # Stores [{"name": str, "value": str}]. Not encrypted. Default is empty list.
    default_headers = models.JSONField(default=list, blank=True)
    ssl_verify = models.BooleanField(default=True)
    # Validated at serializer layer to be 1–120 seconds (Phase 2).
    request_timeout = models.IntegerField(default=30)
    last_test_at = models.DateTimeField(null=True, blank=True)
    # True = passed, False = failed, None = never tested
    last_test_outcome = models.BooleanField(null=True, blank=True)
    last_test_status_code = models.IntegerField(null=True, blank=True)
    last_test_response_time = models.IntegerField(null=True, blank=True)  # milliseconds
    # String, not enum: "json", "xml", "csv", "plain_text", or None
    last_test_detected_format = models.CharField(max_length=50, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        # Phase 2 search query uses name filtering
        indexes = [models.Index(fields=["name"])]
        db_table = "api_connector_connection_profile"

    def __str__(self) -> str:
        return f"{self.name} ({self.base_url})"