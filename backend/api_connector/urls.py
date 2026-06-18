# backend/api_connector/urls.py
from django.urls import path

# app_name MUST be declared before any reverse() call references this namespace.
# All Phase 2+ reverse() calls use the 'api_connector:' prefix.
app_name = "api_connector"

urlpatterns = [
    # P0.B-04+05: health check route added here.
    # Phase 2: path('connector/profiles/', include(...))
]