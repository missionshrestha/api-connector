# backend/api_connector/services/pagination/utils.py
"""
Utility functions for the PaginationEngine.

All three functions are called on every page iteration:
  extract_records_at_path() — called in paginate() on every page response
  build_request_url() — called once at engine start
  detect_data_root() — called from the detect-data-root API action

Security: extract_records_at_path must not raise on any input (malformed API
responses, None values, unexpected types). Returns [] silently on failure.
Phase 6 inference treats [] as "no records found" — not an error.
"""


def extract_records_at_path(data: dict | list, path: str | None) -> list:
    """
    Extract a list of records from a nested response body using dot-notation path.

    Args:
        data: Parsed JSON response body (dict or list).
        path: Dot-notation path to the record array (e.g. "data.items").
              None or "" means the root of the response.

    Returns:
        List of records found at path, or [] on any failure.
        Never raises.
    """
    try:
        if path is None or path == "":
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and data:
                return [data]
            return []

        parts = path.split(".")
        current = data
        for part in parts:
            if not isinstance(current, dict):
                return []
            current = current.get(part)
            if current is None:
                return []

        if isinstance(current, list):
            return current
        return []

    except Exception:
        return []


def build_request_url(base_url: str, endpoint_path: str, path_variables: dict) -> str:
    """
    Build a full request URL from base URL, path, and {variable} substitutions.

    Unresolvable {var} placeholders are left as-is (not raised).
    This is correct behavior — a placeholder with no value signals
    misconfiguration; making a literal request is better than crashing.

    Example:
        build_request_url("https://api.example.com", "/users/{user_id}/orders",
                          {"user_id": "42"})
        → "https://api.example.com/users/42/orders"
    """
    path = endpoint_path
    for key, value in (path_variables or {}).items():
        path = path.replace(f"{{{key}}}", str(value))
    return base_url.rstrip("/") + path


def detect_data_root(response_body: dict | list) -> list[str]:
    """
    Recursively walk response_body and find dot-notation paths pointing to
    non-empty lists of dicts — candidates for data_root_path.

    Returns paths ordered by: shallowest first, larger arrays preferred
    at the same depth. Top-level arrays at root are not returned (no path).

    Depth is capped at 5 to prevent stack overflow on deeply nested APIs.

    Example:
        detect_data_root({"data": [{"id": 1}], "meta": {"total": 10}})
        → ["data"]

    Args:
        response_body: Parsed JSON response body.

    Returns:
        List of dot-notation path strings, most likely first. [] if none found.
    """
    candidates = []  # list of (depth, -len, path)

    def _walk(obj, parent_path: str, depth: int) -> None:
        if depth >= 5:
            return
        if not isinstance(obj, dict):
            return
        for key, value in obj.items():
            current_path = f"{parent_path}.{key}" if parent_path else key
            if (
                isinstance(value, list)
                and len(value) > 0
                and all(isinstance(item, dict) for item in value)
            ):
                candidates.append((depth, -len(value), current_path))
            elif isinstance(value, dict):
                _walk(value, current_path, depth + 1)

    if isinstance(response_body, dict):
        _walk(response_body, "", 0)

    # Sort: shallowest first (depth asc), then larger arrays first (-len asc)
    candidates.sort(key=lambda x: (x[0], x[1]))
    return [c[2] for c in candidates]
