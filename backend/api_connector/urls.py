# backend/api_connector/urls.py
from django.urls import path

from api_connector.views.health import health_check

# app_name MUST be declared before any reverse() call references this namespace.
# All Phase 2+ reverse() calls use the 'api_connector:' prefix.
app_name = "api_connector"

urlpatterns = [
    path("health/", health_check, name="health-check"),
    # Phase 2: path('connector/profiles/', include('api_connector.profiles_urls'))
]