# backend/config/urls.py
from django.urls import include, path

urlpatterns = [
    path("api/", include("api_connector.urls")),
    # Admin intentionally excluded in Phase 0.
    # Phase 8: evaluate whether admin interface is required.
]
