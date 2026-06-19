# backend/api_connector/services/auth/handlers/api_key.py
import httpx

from api_connector.services.auth.base import BaseAuthHandler


class APIKeyAuthHandler(BaseAuthHandler):
    """
    Handles AuthType.API_KEY authentication.

    Expected credentials dict keys:
      key_name (str, required): header name or query parameter name
      key_value (str, required): the API key value
      delivery (str, required): "header" or "query"
      prefix (str, optional): prepended to key_value with a space
        e.g. prefix="Token" → "Token <key_value>"

    Security: key_value must not appear in any log line.
    """

    def prepare_request(
        self, request: httpx.Request, credentials: dict
    ) -> httpx.Request:
        key_name: str = credentials["key_name"]
        key_value: str = credentials["key_value"]
        delivery: str = credentials["delivery"]
        prefix: str = credentials.get("prefix", "")

        value = f"{prefix} {key_value}" if prefix else key_value

        if delivery == "header":
            headers = dict(request.headers)
            headers[key_name] = value
            return httpx.Request(
                method=request.method,
                url=request.url,
                headers=headers,
                content=request.content,
            )
        elif delivery == "query":
            # Merge new param into existing query string
            existing_params = dict(request.url.params)
            existing_params[key_name] = key_value
            new_url = request.url.copy_with(params=existing_params)
            return httpx.Request(
                method=request.method,
                url=new_url,
                headers=request.headers,
                content=request.content,
            )
        else:
            raise ValueError(f"Unknown delivery method: {delivery}")
