# backend/api_connector/models/connection_test_result.py
from django.db import models


class ConnectionTestResult(models.Model):
    """
    Records the result of a connection test for a ConnectionProfile.

    Security notes:
    - step_results may contain a 2KB body sample (set by Phase 3 ConnectionTestService).
      Do NOT log the full step_results object. Log only overall_passed and duration_ms.
    - test_path is not sensitive but must be validated as a URL path string at the API layer.

    Design note: both tested_at and created_at use auto_now_add=True.
    They will always hold the same value. tested_at is the domain-semantic field;
    created_at is kept for consistency with all other models in this app.
    """

    connection_profile = models.ForeignKey(
        "api_connector.ConnectionProfile",
        on_delete=models.CASCADE,
        related_name="test_results",
    )
    tested_at = models.DateTimeField(auto_now_add=True)
    # [{"name": str, "passed": bool, "message": str, "detail": dict}]
    step_results = models.JSONField(default=list)
    overall_passed = models.BooleanField(default=False)
    # The path suffix tested (may be None if testing root URL)
    test_path = models.CharField(max_length=2048, null=True, blank=True)
    duration_ms = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-tested_at"]
        indexes = [
            # Phase 3: fastest lookup of latest test result for a profile
            models.Index(fields=["connection_profile", "tested_at"]),
        ]
        db_table = "api_connector_connection_test_result"

    def __str__(self) -> str:
        outcome = "PASS" if self.overall_passed else "FAIL"
        return (
            f"TestResult({outcome}) for profile "
            f"{self.connection_profile_id} at {self.tested_at}"
        )