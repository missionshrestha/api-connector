# backend/api_connector/models/enums.py
from django.db import models


class AuthType(models.TextChoices):
    NONE = "none", "None"
    API_KEY = "api_key", "API Key"
    BEARER = "bearer", "Bearer Token"
    BASIC = "basic", "Basic Auth"
    OAUTH_CC = "oauth_cc", "OAuth Client Credentials"
    OAUTH_AC = "oauth_ac", "OAuth Authorization Code"


class PaginationStrategy(models.TextChoices):
    NO_PAGINATION = "no_pagination", "No Pagination"
    OFFSET_LIMIT = "offset_limit", "Offset/Limit"
    PAGE_SIZE = "page_size", "Page/Size"
    CURSOR = "cursor", "Cursor"
    NEXT_URL = "next_url", "Next URL"
    LINK_HEADER = "link_header", "Link Header"


class InferredType(models.TextChoices):
    NULL = "null", "Null"
    BOOLEAN = "boolean", "Boolean"
    INTEGER = "integer", "Integer"
    FLOAT = "float", "Float"
    DATE = "date", "Date"
    DATETIME = "datetime", "Datetime"
    STRING = "string", "String"
    MIXED = "mixed", "Mixed"
    ARRAY_OF_OBJECTS = "array_of_objects", "Array of Objects"
    ARRAY_OF_PRIMITIVES = "array_of_primitives", "Array of Primitives"


class ArrayHandling(models.TextChoices):
    EXPAND = "expand", "Expand"
    RETAIN = "retain", "Retain"


class HTTPMethod(models.TextChoices):
    GET = "GET", "GET"
    POST = "POST", "POST"