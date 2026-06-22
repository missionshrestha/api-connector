# backend/api_connector/urls.py
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from api_connector.views.connection_profile import ConnectionProfileViewSet
from api_connector.views.health import health_check

# URL structure: /api/connector/profiles/
# ADR-008: namespaced under 'connector' to prevent clashes with host platform routes.
# Phase 3 adds: POST /api/connector/profiles/{id}/test/
# Phase 5 adds: GET/POST /api/connector/profiles/{id}/endpoints/
app_name = "api_connector"

router = DefaultRouter()
router.register(r"connector/profiles", ConnectionProfileViewSet, basename="profile")

urlpatterns = [
    path("health/", health_check, name="health-check"),
    path("", include(router.urls)),
]
