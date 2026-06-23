# backend/api_connector/urls.py
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from api_connector.views.connection_profile import ConnectionProfileViewSet
from api_connector.views.health import health_check
from api_connector.views.oauth_callback import oauth_callback

# URL structure: /api/connector/profiles/
# ADR-008: namespaced under 'connector' to prevent clashes with host platform routes.

app_name = "api_connector"

router = DefaultRouter()
router.register(r"connector/profiles", ConnectionProfileViewSet, basename="profile")


urlpatterns = [
    path("health/", health_check, name="health-check"),
    path("connector/oauth/callback/", oauth_callback, name="oauth-callback"),
    path("", include(router.urls)),
]
