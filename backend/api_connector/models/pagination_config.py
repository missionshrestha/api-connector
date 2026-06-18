# backend/api_connector/models/pagination_config.py
from django.db import models

from api_connector.models.enums import PaginationStrategy


class PaginationConfig(models.Model):
    """
    Stores pagination configuration for an Endpoint.

    Safety controls:
    - max_pages and max_records are unconditional hard stops for the
      Phase 5 PaginationEngine. They must not be treated as soft suggestions.
    - Users can lower these values per endpoint for APIs with large result sets.
    """

    endpoint = models.OneToOneField(
        "api_connector.Endpoint",
        on_delete=models.CASCADE,
        related_name="pagination_config",
    )
    strategy = models.CharField(
        max_length=20,
        choices=PaginationStrategy.choices,
        default=PaginationStrategy.NO_PAGINATION,
    )
    # Strategy-specific params, validated at serializer layer (Phase 5)
    strategy_params = models.JSONField(default=dict, blank=True)
    max_pages = models.IntegerField(default=100)
    max_records = models.IntegerField(default=10000)
    inter_page_delay_ms = models.IntegerField(default=0)  # 0 = no delay
    max_retries = models.IntegerField(default=3)  # for 429 and 5xx retry logic
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "api_connector_pagination_config"

    def __str__(self) -> str:
        return f"PaginationConfig({self.strategy}) for endpoint {self.endpoint_id}"