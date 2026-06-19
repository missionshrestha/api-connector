# backend/api_connector/services/auth/registry.py
from api_connector.models.enums import AuthType
from api_connector.services.auth.base import BaseAuthHandler
from api_connector.services.auth.handlers.api_key import APIKeyAuthHandler
from api_connector.services.auth.handlers.basic import BasicAuthHandler
from api_connector.services.auth.handlers.bearer import BearerAuthHandler
from api_connector.services.auth.handlers.none_handler import NoneAuthHandler
from api_connector.services.auth.handlers.oauth_ac import OAuthACAuthHandler
from api_connector.services.auth.handlers.oauth_cc import OAuthCCAuthHandler


class AuthHandlerRegistry:
    """
    Maps AuthType enum values to concrete BaseAuthHandler subclasses.

    Returns a new handler instance per call — handlers are stateless and
    must not carry request-specific state between calls.

    Security: auth_type coming from API requests must be validated against
    AuthType.choices at the serializer layer before calling registry.get().
    Never pass raw user input strings directly to get().
    """

    _registry: dict[str, type[BaseAuthHandler]] = {
        AuthType.NONE: NoneAuthHandler,
        AuthType.API_KEY: APIKeyAuthHandler,
        AuthType.BEARER: BearerAuthHandler,
        AuthType.BASIC: BasicAuthHandler,
        AuthType.OAUTH_CC: OAuthCCAuthHandler,
        AuthType.OAUTH_AC: OAuthACAuthHandler,
    }

    def get(self, auth_type: str) -> BaseAuthHandler:
        """Look up and instantiate a handler for the given AuthType value.

        Raises ValueError if auth_type is not registered.
        """
        handler_class = self._registry.get(auth_type)
        if handler_class is None:
            raise ValueError(
                f"No handler registered for auth_type: {auth_type!r}. "
                f"Valid types: {list(self._registry.keys())}"
            )
        return handler_class()


# Module-level singleton
auth_handler_registry = AuthHandlerRegistry()
