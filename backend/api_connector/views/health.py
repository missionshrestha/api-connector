# backend/api_connector/views/health.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    # Response body is exactly {"status": "ok"}.
    # No version numbers, hostnames, or internal state.
    #
    # AllowAny is explicit insurance: when Phase 1 sets
    # DEFAULT_PERMISSION_CLASSES = [IsAuthenticated], views without an explicit
    # decorator inherit it. A health check that requires auth fails load balancers
    # silently — they mark the service unhealthy, not "needs login."
    #
    # Phase 1 logging: log this endpoint at DEBUG level only.
    # Load balancer polling at INFO creates log noise.
    return Response({"status": "ok"}, status=200)
