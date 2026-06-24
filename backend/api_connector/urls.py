# backend/api_connector/urls.py
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from api_connector.views.connection_profile import ConnectionProfileViewSet
from api_connector.views.endpoint import EndpointViewSet
from api_connector.views.health import health_check
from api_connector.views.oauth_callback import oauth_callback

app_name = "api_connector"

# Router 1: top-level profile resources
router = DefaultRouter()
router.register(r"connector/profiles", ConnectionProfileViewSet, basename="profile")

# Router 2: endpoint resources nested under profiles
# ADR-009: nested URL keeps profile_pk in path for self-evident access control
endpoint_router = DefaultRouter()
endpoint_router.register(r"endpoints", EndpointViewSet, basename="endpoint")

urlpatterns = [
    path("health/", health_check, name="health-check"),
    path("connector/oauth/callback/", oauth_callback, name="oauth-callback"),
    path("", include(router.urls)),
    # Nested endpoints: /api/connector/profiles/<profile_pk>/endpoints/...
    path(
        "connector/profiles/<int:profile_pk>/",
        include(endpoint_router.urls),
    ),
]
