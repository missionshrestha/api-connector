# backend/api_connector/views/connection_profile.py
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from api_connector.models import ConnectionProfile
from api_connector.serializers.connection_profile import (
    ConnectionProfileCreateSerializer,
    ConnectionProfileReadSerializer,
    ConnectionProfileUpdateSerializer,
)


class ConnectionProfileViewSet(viewsets.ModelViewSet):
    """
    Full CRUD for ConnectionProfile.

    URL: /api/connector/profiles/
    Registered via DefaultRouter in api_connector/urls.py.

    Serializer dispatch:
      list, retrieve → ConnectionProfileReadSerializer (no secrets)
      create         → ConnectionProfileCreateSerializer (encrypts credentials)
      update, partial_update → ConnectionProfileUpdateSerializer (merges credentials)
      destroy        → uses default destroy() (no custom serializer needed)

    Security assumption [ASSUMPTION]:
      permission_classes = [AllowAny] assumes this module is deployed behind
      the host platform's authentication layer. Phase 8 security audit must
      confirm this or add an authentication class here.

    Performance:
      select_related('auth_config') prevents N+1 on the list endpoint.
      Without it, 50 profiles = 51 DB queries (1 for profiles + 50 for auth_configs).
      With it, always 1 query regardless of list size.
    """

    # [ASSUMPTION] Host-platform auth assumed. Phase 8 must validate.
    permission_classes = [AllowAny]
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    def get_queryset(self):
        queryset = ConnectionProfile.objects.select_related("auth_config").order_by(
            "-created_at"
        )
        # ?search= filters by name (case-insensitive, parameterized — injection-safe)
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search.strip())
        return queryset

    def get_serializer_class(self):
        if self.action in ["list", "retrieve"]:
            return ConnectionProfileReadSerializer
        elif self.action == "create":
            return ConnectionProfileCreateSerializer
        else:
            # update, partial_update, destroy
            return ConnectionProfileUpdateSerializer

    def create(self, request, *args, **kwargs):
        write_serializer = ConnectionProfileCreateSerializer(data=request.data)
        write_serializer.is_valid(raise_exception=True)
        instance = write_serializer.save()
        # Use ReadSerializer for the response so credentials_summary is included
        read_serializer = ConnectionProfileReadSerializer(instance)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED)
