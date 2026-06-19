# backend/api_connector/services/auth/base.py
from abc import ABC, abstractmethod

import httpx


class BaseAuthHandler(ABC):
    """
    Abstract base for authentication injection handlers.

    Contract:
    - prepare_request() MUST return an httpx.Request with auth injected.
    - It MUST be pure: no side effects, no DB calls, no logging.
    - Handlers MUST NOT store credentials as instance state
      (self.credentials = credentials is forbidden). Credentials are
      received per-call and discarded after the request is built.
    - credentials: decrypted credential dict from EncryptionService.decrypt_to_dict()
    """

    @abstractmethod
    def prepare_request(
        self, request: httpx.Request, credentials: dict
    ) -> httpx.Request:
        """Inject authentication into the outbound request. Return the modified request."""
