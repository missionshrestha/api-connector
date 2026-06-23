# backend/api_connector/serializers/connection_test.py
from rest_framework import serializers

from api_connector.models import ConnectionTestResult


class ConnectionTestRequestSerializer(serializers.Serializer):
    """
    Validates the request body for POST /api/connector/profiles/{id}/test/.

    test_path is optional. When provided, must start with '/' to prevent
    path-confusion bugs (e.g. "api/v1" would join with base_url as "https://example.comapi/v1").
    """

    test_path = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        max_length=2048,
        default=None,
    )

    def validate_test_path(self, value: str | None) -> str | None:
        if value and not value.startswith("/"):
            raise serializers.ValidationError(
                "test_path must start with '/' or be empty. "
                "Example: '/api/v1/health' or '/ping'"
            )
        return value or None


class ConnectionTestResultSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for ConnectionTestResult responses.

    result_id aliases the model's 'id' for API contract stability.
    steps returns step_results JSONB directly — already structured correctly
    by ConnectionTestService.run().

    Security: step_results may contain body_sample from step 6 which could
    include API response data. The API consumer must not log this response.
    """

    result_id = serializers.IntegerField(source="id", read_only=True)
    steps = serializers.SerializerMethodField()

    def get_steps(self, obj: ConnectionTestResult) -> list:
        return obj.step_results

    class Meta:
        model = ConnectionTestResult
        fields = ["result_id", "overall_passed", "tested_at", "duration_ms", "steps"]
        read_only_fields = [
            "result_id",
            "overall_passed",
            "tested_at",
            "duration_ms",
            "steps",
        ]
