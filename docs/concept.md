# API Connector — Feature Concept Document

> **Purpose:** This document describes the concept of an API Connector feature at a generic, technology-agnostic level. It is a starting point for discussion, scoping, and design. Specific implementation choices — data models, services, UI components, technology stack, deployment approach — are left to each project based on its own context, constraints, and requirements.

---

## Table of Contents

1. [What Is an API Connector?](#1-what-is-an-api-connector)
2. [Why API Connectors Matter](#2-why-api-connectors-matter)
3. [Core Mental Model](#3-core-mental-model)
4. [Connection Profiles](#4-connection-profiles)
5. [Authentication](#5-authentication)
6. [Endpoint Configuration](#6-endpoint-configuration)
7. [Pagination](#7-pagination)
8. [Schema Discovery &amp; Management](#8-schema-discovery--management)
9. [Connection Testing &amp; Diagnostics](#9-connection-testing--diagnostics)
10. [Data Preview](#10-data-preview)
11. [Credential &amp; Secret Management](#11-credential--secret-management)
12. [Security Considerations](#12-security-considerations)
13. [Error Handling](#13-error-handling)
14. [Resilience &amp; Reliability](#14-resilience--reliability)
15. [Observability &amp; Audit](#15-observability--audit)
16. [Multi-Tenancy &amp; Access Control](#16-multi-tenancy--access-control)
17. [Integration into a Larger Platform](#17-integration-into-a-larger-platform)
18. [Extensibility &amp; Future Directions](#18-extensibility--future-directions)
19. [What to Include vs. Exclude](#19-what-to-include-vs-exclude)

---

## 1. What Is an API Connector?

An API Connector is a configurable integration layer that enables a platform to connect to external REST APIs and treat them as structured data sources — in the same way it treats databases, files, or cloud storage.

Rather than writing custom integration code for every external service, an API Connector provides a general-purpose, reusable mechanism: the user configures how to reach an API, how to authenticate with it, how to traverse its pages, and how to interpret its response structure. The connector handles the rest.

The fundamental promise of an API Connector is: **any REST API becomes a first-class data source without writing code.**

---

## 2. Why API Connectors Matter

### The Diversity of Data Sources

Modern data pipelines draw from many kinds of sources. Relational databases, NoSQL stores, and file uploads cover a large portion of internal, organization-owned data. But a significant and growing category of data lives behind REST APIs: weather services, financial data feeds, government data portals, geolocation services, SaaS platforms, research APIs, and public datasets. These sources are live, authenticated, paginated, and API-first.

### Two Primary Use Cases

**Standalone ingestion:** API data ingested directly as a data source — astronomy data, economic indicators, public health metrics — forms its own analytical dataset within a pipeline.

**Data enrichment:** API data supplements and augments records already in a pipeline. A customer record can be enriched with geolocation data. A product record can be enriched with real-time pricing indices. This enrichment is only possible when API sources are treated as first-class citizens alongside databases.

### Why Not Just Write Custom Integrations?

Custom per-API integrations are not scalable. Every new API source requires:

- Bespoke authentication handling
- Custom pagination logic
- Hand-crafted schema definitions
- Ad hoc error handling
- Repeated maintenance as APIs evolve

A generic API Connector amortizes this complexity across all sources. The engineering investment is made once; every new API is a configuration exercise, not a development task.

---

## 3. Core Mental Model

The API Connector introduces two main abstractions: the **Connection Profile** and the **Endpoint**. Understanding the relationship between them is the foundation of the entire feature.

```
Connection Profile
│  (How to reach and authenticate with an API)
│
├── Endpoint A         (e.g., /users)
│   ├── Pagination Config
│   └── Schema Fields
│
├── Endpoint B         (e.g., /orders)
│   ├── Pagination Config
│   └── Schema Fields
│
└── Endpoint C         (e.g., /products)
    ├── Pagination Config
    └── Schema Fields
```

**A Connection Profile** captures the shared identity of an external API: its base URL, authentication method, and credentials. It answers: *who is this API and how do we authenticate with it?*

**An Endpoint** represents a specific data resource within that API — equivalent to a table in a relational database. It answers: *what data do we fetch, how, and in what shape?*

This separation is intentional. Authentication is shared across an entire API; data resources are independent. Endpoints inherit their connection context from the profile and extend it with their own fetch behavior and schema.

---

## 4. Connection Profiles

A Connection Profile is the top-level configuration unit. It holds everything needed to establish a connection with an external API.

### What a Profile Captures

- **Identity:** A human-readable name and the base URL of the API.
- **Authentication:** The chosen auth method and the corresponding credentials.
- **Transport settings:** SSL/TLS verification preference, request timeout, default HTTP headers (e.g., `Accept: application/json`).
- **Connection health:** Metadata from the most recent connection test — whether it passed, what the outcome was, and when it was last tested.

### Profile Lifecycle

A profile is created once and shared across all its endpoints. Updating credentials on the profile propagates to all dependent endpoints automatically. Deleting a profile removes all its endpoints and their associated data.

### Profile as a Reusable Identity

Multiple users or pipeline configurations can reference the same profile. Credentials are stored once, centrally, in encrypted form, and are never exposed through the application layer.

---

## 5. Authentication

Authentication is one of the two most variable dimensions of REST API integration. The correct method depends entirely on the API being connected to.

### The Authentication Methods

#### No Authentication

For fully public APIs that require no credentials. A request is made with no additional headers or parameters. Use cases include open government datasets, public weather APIs, and unauthenticated reference data sources.

#### API Key

A static, pre-issued key that the client sends with every request. API key delivery varies:

- **Header injection:** The key is sent as a custom header (e.g., `X-API-Key: abc123`, or `Authorization: ApiKey abc123`).
- **Query parameter injection:** The key is appended to the URL (e.g., `?api_key=abc123`).

The API key name, delivery method, and optional prefix (the string that goes before the key value, such as `Bearer` or `Token`) are configurable per profile. This covers the majority of public API providers.

#### HTTP Basic Authentication

A username and password encoded together using Base64 and sent in the `Authorization` header. Many legacy and internal APIs use this method. The actual credential value is never transmitted in plaintext — it is Base64-encoded before sending.

#### Bearer Token

A pre-obtained token passed in the `Authorization: Bearer <token>` header. The connector does not know or care how the token was obtained; it is provided by the user and injected as-is. Common for APIs that issue long-lived access tokens outside of OAuth flows.

#### OAuth 2.0 — Client Credentials

A machine-to-machine token exchange. The connector holds a client ID and client secret, exchanges them at a token endpoint, and receives a time-limited access token. The connector automatically manages the token lifecycle: fetching a new token before expiry, caching the token across requests to avoid re-fetching unnecessarily, and refreshing when it expires.

This method is used when connecting to organizational APIs where no human user consent is required — for example, internal service-to-service communication or B2B data feeds.

#### OAuth 2.0 — Authorization Code (with PKCE)

A user-facing consent flow where a human user grants the connector access to their data on a third-party platform. The flow involves:

1. Generating a PKCE code challenge and state token (CSRF protection).
2. Redirecting the user to the provider's authorization screen.
3. Receiving the authorization code at a callback URL.
4. Exchanging the code for an access token and refresh token.
5. Silently refreshing the access token using the refresh token.

This method is used when connecting to user-owned data — for example, a user's CRM records, their personal financial data, or their social media analytics.

### Credential Storage Principle

Regardless of the method, credentials must **never** be stored in plaintext. They must be encrypted at rest and must never appear in API responses, application logs, or error messages. Only metadata about credentials — whether they are set, not what they contain — should be surfaced to the frontend.

### Token Lifecycle Management

For OAuth methods, the connector is responsible for the full token lifecycle: initial acquisition, caching, expiry detection, refresh, and handling re-authorization when a refresh token has itself expired. This lifecycle should be transparent to the end user during normal operation; re-authorization prompts should only surface when tokens cannot be silently refreshed.

---

## 6. Endpoint Configuration

An Endpoint represents one specific data resource within an API. Where a Connection Profile answers "which API and how to authenticate," an Endpoint answers "which data and how to fetch it."

### What an Endpoint Captures

**Path and method:**

- The path relative to the profile's base URL (e.g., `/v2/users`, `/data/records`).
- The HTTP method — typically GET, but POST is also used for data retrieval when query parameters would exceed URL length limits or when the API requires filtering parameters in the request body.

**Path variables:**

- APIs often parameterize paths with variable segments (e.g., `/organizations/{org_id}/members`). These placeholder values are user-defined and resolved at request time.

**Query parameters:**

- Static key-value pairs appended to every request (e.g., `?format=json&status=active`).

**Request body (for POST):**

- A JSON payload sent with POST requests. Like query parameters, this is typically static or templated — it specifies filters, field selections, or configuration accepted by the API.

**Response traversal — the data root path:**

- Most APIs do not return an array at the top level of their response. They nest it inside a wrapper object:
  ```json
  { "data": { "items": [...], "total": 500 } }
  ```
- The data root path tells the connector where inside the response the actual records live (e.g., `data.items`). Without this, the connector cannot distinguish records from metadata.

**Record count path:**

- Some APIs include a total count in the response (e.g., `data.total`). This allows the connector to display progress information and make smarter pagination decisions.

### Endpoint as a Table Analogy

In the context of a data pipeline, an Endpoint is semantically equivalent to a database table. Where a database connector has `connection → database → schema → table`, an API connector has `profile → endpoint`. To downstream pipeline stages, an endpoint is simply another source of records — regardless of what auth method, pagination strategy, or response structure sits behind it.

---

## 7. Pagination

Pagination is the second most variable dimension of REST API integration. Every API paginates differently, and partial pagination support is equivalent to silent data truncation.

### Why Pagination Must Be Comprehensive

An API connector that only supports one pagination method will silently return incomplete data for any API using a different convention. There is no error — the first page simply looks like the entire dataset. This is one of the most dangerous silent correctness failures in data integration.

### The Pagination Strategies

#### No Pagination

The API returns the complete dataset in a single response. No iteration is required. Appropriate for small reference datasets, lookup tables, or APIs that guarantee complete responses.

#### Limit-Offset

The classical SQL-derived pagination model, expressed as query parameters. The client specifies how many records to return (`limit`) and where to start in the dataset (`offset`). Each successful page increments the offset by the limit. Pagination terminates when the returned record count falls below the requested limit.

Example: `GET /records?limit=100&offset=0`, `GET /records?limit=100&offset=100`, ...

#### Page-Size

Conceptually identical to Limit-Offset but expressed as a page number rather than an offset. The client specifies the page number and page size. Pagination terminates on the same condition — fewer records returned than the page size.

Example: `GET /records?page=1&size=100`, `GET /records?page=2&size=100`, ...

#### Cursor

The API issues an opaque cursor token representing the "position" in the dataset. The client passes this cursor as a parameter on the next request. The cursor value is extracted from the response body via a configurable path (e.g., `pagination.next_cursor`). Pagination terminates when the cursor is absent or null.

Cursor pagination is the most reliable strategy for large or frequently updated datasets because it is stable — it does not drift as records are inserted or deleted during traversal. However, it does not allow random access or progress estimation.

#### Next URL

The API embeds the full URL of the next page directly in the response body (e.g., `{"next": "https://api.example.com/records?page=2&token=xyz"}`). The connector follows this URL on each iteration and terminates when the next field is absent, null, or an empty string.

#### Link Header

The next page URL is embedded in the HTTP response header following RFC 5988 format: `Link: <https://api.example.com/records?page=2>; rel="next"`. The connector parses this header on each response and follows the `rel="next"` link until it is no longer present.

### Safety Limits

Regardless of strategy, the connector must enforce hard limits to prevent runaway pagination:

- **Maximum page count:** An upper bound on the number of pages fetched per run, regardless of what the API signals.
- **Maximum record count:** An upper bound on the total number of records accumulated.

These limits are not guidelines — they are mandatory safeguards against misconfiguration, misbehaving APIs, or infinite loop conditions.

### Inter-Page Behavior

Between pages, the connector may need to:

- Respect rate limit headers (`Retry-After`, `X-RateLimit-Reset`) and pause accordingly.
- Apply a configurable delay to avoid aggressive request bursts.
- Retry on transient failures (5xx responses, connection drops) with backoff.

---

## 8. Schema Discovery & Management

Because every API returns a different response structure, schema discovery is a prerequisite for treating API data as structured, typed records. Manual schema definition for arbitrary APIs is impractical at scale.

### The Problem

A relational database has an explicit, pre-defined schema accessible via metadata queries. An API does not. Its response structure must be inferred from actual response data. Nested JSON, arrays, nullable fields, mixed-type fields, and inconsistencies between records all complicate this inference.

### Schema Inference

The inference process involves:

1. **Fetching a representative sample** — one or more pages of data from the endpoint, using the configured pagination strategy.
2. **Walking all records** — for each record in the sample, recursively traversing all fields and accumulating value samples per field path.
3. **Calculating null rates** — tracking how often each field is absent or null across the record set, producing a null percentage (0.0 = always present; 1.0 = always null).
4. **Type determination** — from accumulated samples, assigning the most accurate type to each field.

### Nested Structure Handling

JSON responses are often nested multiple levels deep. Schema inference must flatten nested objects into addressable paths using a consistent notation (commonly dot-notation: `customer.address.city`, `order.items[0].price`).

Arrays/Objects require special handling:

- **Array of objects:** Can be expanded into multiple rows (one row per array element) or retained as a JSON blob column.
- **Array of primitives:** Can be retained as an array column or concatenated into a single string.
- **Array of arrays:** ...
- **Object of arrays:** ...
- **Object of objects:** ...

The choice depends on downstream pipeline requirements and should be configurable per field.

### Type Categories

A practical inference engine must distinguish, at minimum, between:

| Type                    | Notes                                                       |
| ----------------------- | ----------------------------------------------------------- |
| `string`              | Any textual value                                           |
| `integer`             | Whole numbers                                               |
| `float`               | Decimal numbers                                             |
| `boolean`             | True/false values — must be distinguished from integer 0/1 |
| `date`                | Date-only values                                            |
| `datetime`            | Date and time values                                        |
| `null`                | Always-null fields                                          |
| `mixed`               | Field contains incompatible types across records            |
| `array_of_objects`    | Array whose elements are JSON objects                       |
| `array_of_primitives` | Array whose elements are scalars                            |
| `object_of_objects`   |                                                             |
| `object_of_arrays`    |                                                             |
| `arrays_of_arrays`    |                                                             |

Mixed-type fields deserve special attention: they signal either API inconsistency or a field that serves multiple semantic roles. The user should be informed and allowed to decide how to handle them.

### Schema Management

After inference, schema fields should be user-reviewable and adjustable:

- **Include / Exclude:** Users select which fields to carry into the pipeline. Fields not included are dropped before data reaches downstream stages.
- **Aliasing:** Users can assign a display name to any field path, decoupling the pipeline's column names from the API's internal naming conventions.
- **Type override:** When inference is incorrect or ambiguous (common with dates stored as strings), users can override the inferred type.
- **Null percentage visibility:** Showing null rates helps users assess data quality and decide whether a field is reliable enough to include.

### Schema Staleness

Schemas should be re-inferrable at any time. When an API changes its response structure, previously inferred fields may no longer exist (stale) or new fields may appear. A re-inference run should clearly mark which existing fields are stale and which are newly discovered, without silently overwriting user-configured aliases or overrides.

---

## 9. Connection Testing & Diagnostics

Before a connection profile is used in a live pipeline, users need confidence that it is correctly configured. A connection test that returns only "success" or "failure" is insufficient — it provides no actionable information when something goes wrong.

### Why Step-by-Step Diagnostics

Configuration failures in API integrations cluster around a few specific layers: the host may not be resolvable, the network path may be blocked, the credentials may be wrong, the server may respond with a redirect or unexpected format. A sequential diagnostic that tests each layer independently tells the user exactly where the failure is, not just that one exists.

### Diagnostic Layers

A well-structured connection test should verify, in sequence:

1. **DNS resolution:** Can the hostname in the base URL be resolved to an IP address? A failure here indicates a typo in the URL or a DNS configuration problem — not a credential issue.
2. **Network reachability:** Can a TCP connection be established to the resolved host and port? A failure here indicates a firewall rule, network routing issue, or the server is down.
3. **Authentication injection:** Are the credentials formatted correctly before the request is sent? This step validates the credential structure before committing to a network round trip.
4. **HTTP response:** Does the server return a valid HTTP response with an acceptable status code? A 401 indicates wrong credentials. A 403 indicates permissions. A 404 may indicate a wrong base URL. A 5xx indicates a server-side problem.
5. **Format detection:** Is the response valid JSON? An API that returns HTML on errors, XML by default, or binary for certain content types will cause downstream failures if not caught here.
6. **Response sample capture:** A small excerpt of the actual response, confirming that the data root path is reachable and records are present.

Each step should report its outcome, an informative message, and the time taken. The test should stop at the first failure and clearly indicate which step failed.

### Test Result Persistence

Test results should be stored historically, not just shown once. Historical test results allow users and operators to see whether a connection has been stable over time, and provide context when debugging pipeline failures.

---

## 10. Data Preview

Data preview bridges the gap between configuration and trust. A user who has configured an endpoint but has not seen actual data from it cannot confidently deploy the endpoint to a live pipeline.

### What Data Preview Provides

A live, bounded fetch of real data from the configured endpoint, displayed in a tabular format. The user sees exactly what records the pipeline will receive, formatted with the configured schema fields applied.

### Preview Behavior

- **Field filtering:** Only the included schema fields are shown. Fields the user has excluded are not fetched or displayed.
- **Row limiting:** The preview fetches a bounded number of records — enough to be representative, not enough to become a full pipeline run. The limit is configurable.
- **Paginated display:** If the preview fetches more records than fit on one screen, the preview display itself should be paginated for usability.
- **Data root path validation:** If the configured data root path is incorrect, the preview will show zero records or an error, immediately revealing the misconfiguration.

### Preview as Validation

Data preview is not just a convenience feature. It is the primary mechanism by which users validate their endpoint configuration before it affects a real pipeline. A working preview strongly indicates that authentication, pagination, data root path, and schema are all correctly configured.

---

## 11. Credential & Secret Management

Credentials are the most sensitive piece of data the API Connector handles. Their management deserves dedicated attention at every layer.

### Encryption at Rest

All credentials — API keys, passwords, OAuth tokens, bearer tokens, client secrets — must be encrypted before persistence. The encryption must be:

- **Authenticated:** The encrypted value must include an integrity check so tampering is detectable (e.g., AES-256-CBC with HMAC-SHA256, or an AEAD cipher).
- **Envelope-based or blob-based:** All credentials for a profile can be stored as a single encrypted blob, or as individually encrypted values. The blob approach is simpler and more flexible for evolving credential structures; individual encryption requires more schema design but allows selective access.
- **Key-managed:** The encryption key must come from a secrets manager or environment variable — never hardcoded, never stored in the database.

### Credential Surface Area

Credentials must be absent from:

- API responses to the frontend (return only presence metadata, never values)
- Application logs (strip credential fields before logging)
- Error messages and exception tracebacks
- URL query strings when logging requests

### Credential Lifecycle

**Initial setup:** Credentials are provided by the user, validated (via a connection test), and encrypted before storage.

**Update:** When credentials change (key rotated by the API provider, token expired), the user provides new values. The old encrypted blob is replaced atomically.

**Key rotation:** When the platform's own encryption key needs to be rotated, all stored credential blobs must be re-encrypted from the old key to the new key. This operation should be atomic and reversible — if re-encryption fails midway, the system should be able to roll back rather than leave partially re-encrypted state.

**Deletion:** When a connection profile is deleted, all associated credential material should be purged from storage.

### OAuth Token Storage

OAuth access tokens and refresh tokens are credentials and must be encrypted at rest with the same rigor as user-provided secrets. They are never long-lived enough to be considered low-sensitivity.

When a refresh token expires and cannot produce a new access token, the connector must surface a re-authorization prompt rather than silently failing.

---

## 12. Security Considerations

### SSRF (Server-Side Request Forgery) Protection

An API Connector that allows arbitrary user-supplied URLs and makes outbound HTTP requests is, by design, vulnerable to SSRF if not explicitly protected. An attacker can supply a URL pointing to an internal network service (e.g., `http://169.254.169.254/` for cloud metadata, or `http://192.168.1.1/` for internal infrastructure) and use the connector as a proxy to enumerate or access internal resources.

Protection requires:

- Resolving the target hostname to an IP address before making the request.
- Blocking requests to RFC 1918 private ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16), loopback (127.0.0.0/8), and link-local (169.254.0.0/16) addresses.
- Re-validating after any redirects that may resolve to a different address.

SSRF protection is not optional in any shared, multi-user, or cloud-hosted deployment.

### Response Validation

Responses from external APIs are untrusted. The connector must:

- Validate that responses are valid JSON before processing.
- Reject binary content (executables, compiled files, non-text formats).
- Enforce hard limits on response size and record count to prevent memory exhaustion from unexpectedly large responses.
- Never write raw response bytes to disk without validation.

### SSL/TLS Verification

SSL certificate verification must be enabled by default. Disabling it should require an explicit user opt-in per profile and should be treated as a security exception, not a convenience setting. Disabling verification in production without documented justification is a security risk.

### Logging Safety

Credentials must never appear in logs. This means:

- Stripping query string parameters from logged URLs (API keys delivered as query parameters must be masked).
- Never logging request bodies that contain credentials.
- Never logging response bodies (they may contain sensitive data from the external API).
- Ensuring structured logging does not inadvertently serialize credential fields.

### Injection Prevention

If URL path variables or query parameters are constructed from user input, they must be validated and encoded to prevent injection into the request structure. URLs with unusual schemes (e.g., `file://`, `ftp://`, `gopher://`) should be rejected.

---

## 13. Error Handling

### Structured Error Responses

When something goes wrong, the response to the caller should carry enough information to diagnose the issue without exposing internals. A useful error structure includes:

- A stable, machine-readable error code for programmatic handling.
- A human-readable message for display.
- Contextual detail that is specific to the failure instance.

Importantly, the human-readable message must never include raw exception text, stack traces, database query details, or credential values.

### Error Categories

Errors in an API Connector cluster around predictable domains:

| Category       | Examples                                                                   |
| -------------- | -------------------------------------------------------------------------- |
| Configuration  | Invalid base URL, missing required credential field, unsupported auth type |
| Network        | DNS failure, connection refused, timeout, SSL error                        |
| Authentication | 401 Unauthorized, 403 Forbidden, token expired                             |
| Pagination     | Malformed cursor, missing data root path, exceeded limits                  |
| Schema         | Empty response, non-JSON response, incompatible type evolution             |
| Data Preview   | Root path not found, zero records returned                                 |
| Internal       | Encryption failure, database error, unexpected system state                |

Each category should have its own error code range so that operators and users can triage failures without reading full error details.

### Fail-Safe Defaults

The connector should fail safely rather than partially silently:

- If schema inference returns zero fields, surface an error rather than storing an empty schema.
- If pagination produces zero records when previous runs produced records, flag it rather than silently overwriting.
- If a required configuration value is missing, fail at configuration time, not at pipeline run time.

---

## 14. Resilience & Reliability

### Transient Failure Handling

External APIs experience transient failures: brief network interruptions, momentary server overloads, and rate limit enforcement. The connector should not treat these as permanent failures.

**Retry strategy:** On transient failure (5xx responses, connection errors, timeout), the connector should retry with exponential backoff — each retry waits longer than the previous one. The backoff should include jitter (a small random component) to prevent many connectors retrying simultaneously after a shared outage, which would amplify the load on the recovering API.

**Idempotency:** For operations that modify state or fetch paginated data, retries must be safe to apply multiple times. Fetching the same page twice should not cause data duplication downstream.

**Retry limits:** Retries are bounded. After a configurable number of attempts without success, the connector gives up and reports a failure rather than retrying indefinitely.

### Rate Limiting Awareness

APIs enforce rate limits. When a rate limit is reached, the API typically returns a `429 Too Many Requests` response with headers indicating when requests can resume (`Retry-After`, `X-RateLimit-Reset`). The connector should:

- Detect rate limit responses (429) and treat them as "retry after delay" rather than permanent failures.
- Read and respect the `Retry-After` header value when present.
- Apply a configurable inter-page delay to avoid triggering rate limits in the first place.

### Circuit Breaker

For APIs that are consistently failing over a period of time, retrying each request independently wastes resources and delays failure surfacing. A circuit breaker pattern can detect sustained failure and temporarily halt requests to the failing API, giving it time to recover, before trying again.

In a simpler implementation, this can be as minimal as tracking consecutive failures and pausing after a threshold is crossed.

### Timeouts

Every outbound request must have a configurable timeout. A request without a timeout can hang indefinitely, blocking the connection, the thread, and downstream pipeline stages. Timeouts should be configurable per profile to accommodate APIs with legitimately slow response times (e.g., APIs that perform heavy server-side computation before responding).

---

## 15. Observability & Audit

### Connection Test History

Every connection test run should be recorded with its outcome, timestamps, step results, and relevant metadata (status code, response time, detected format). This history is operationally valuable: it allows operators to see when a connection started failing, correlate failures with API provider incidents, and verify that fixes are working.

### Sync / Execution History

For production pipeline runs, each data fetch operation should be logged with:

- Start and end time.
- Number of pages fetched, records fetched.
- Whether the run completed successfully or encountered an error.
- Which pagination limit was hit, if any.
- Error details for failed runs.

This history enables data freshness monitoring, anomaly detection (did the record count drop unexpectedly?), and debugging of pipeline-level data quality issues.

### Structured Logging

Application-level logs should use structured formats (JSON) with consistent fields: timestamp, request ID, connector ID, endpoint ID, operation type, outcome, duration. This makes logs machine-searchable and enables aggregation and alerting in monitoring platforms.

### Audit Logging

For security and compliance purposes, high-sensitivity operations should be audited:

- Credential creation, update, and deletion.
- Encryption key rotation.
- OAuth token acquisition and refresh.
- Access to credential decryption (who, when, for what purpose).

Audit logs are immutable append-only records. They answer the question: *who did what, to what, when?*

### Alerting & Monitoring

In production deployments, the connector's health should be surfaced through operational metrics:

- Connection test pass/fail rates per profile.
- Pipeline run success/failure rates.
- Average fetch duration and page count per endpoint.
- Rate limit encounter frequency.
- Encryption key age (to prompt rotation before expiry).

---

## 16. Multi-Tenancy & Access Control

### Tenant Isolation

In a multi-user or multi-tenant platform, connection profiles and their credentials must be strictly isolated. One tenant's profiles must be invisible and inaccessible to any other tenant, at both the application and database layers.

Isolation applies to:

- Profile and endpoint CRUD operations.
- Connection test execution.
- Schema inference and data preview.
- Credential storage and decryption.

### Access Control

Within a single organization or tenant, finer-grained access control may be needed:

- **Who can create profiles?** Creating a profile implies the ability to store credentials and make outbound network connections.
- **Who can view profiles?** Viewing a profile should show metadata but never credentials.
- **Who can run connection tests?** Running a test makes an outbound network call using stored credentials.
- **Who can trigger schema inference or data preview?** These operations fetch real data from external APIs.

The appropriate level of granularity depends on the host platform's access control model. At minimum, credential-sensitive operations should be restricted to authorized users.

### Credential Ownership

Credentials stored in a connection profile should be associated with an owner and subject to that owner's access rights. When an owner leaves or changes roles, the platform should have a process for transferring or revoking ownership of profiles and their credentials.

---

## 17. Integration into a Larger Platform

### The Connector as a Data Source Node

In the context of a pipeline or query builder, each endpoint is a data source node — equivalent to a database table. When a user selects an endpoint as a pipeline source, the system:

1. Resolves the connection profile to retrieve (and decrypt) credentials.
2. Configures the pagination engine for the endpoint's strategy.
3. Executes the fetch, receiving records page by page.
4. Passes records into the transformation and loading stages of the pipeline.

To the rest of the pipeline, the records are structureless rows with typed columns. The connector is responsible for producing records in that shape; everything downstream is agnostic to the fact that the source was an API.

### Schema Registration

After schema inference, the endpoint's schema fields should be registered with the platform's schema registry (if one exists) in the same format as database table schemas. This ensures that query builder, field selectors, and type validation all behave identically for API endpoints and database tables.

### Execution Environment Considerations

The pagination engine — the component that makes sequential HTTP requests and accumulates records — may need to be deployed differently depending on the execution environment:

- In synchronous/threaded environments, a blocking sequential request loop is appropriate.
- In distributed processing environments (e.g., Spark), execution may need to be adapted to run at the driver or within a partitioned UDF, depending on how the API supports parallel access.
- In async environments, the fetch loop can be made non-blocking for better resource utilization.

The core concept — configurable pagination, record accumulation, schema mapping — is the same regardless of execution environment. The execution model is an implementation choice.

### Connector as a Destination (Write Operations)

The concept of an API Connector as described in this document focuses on read operations — fetching data from external APIs into a pipeline. The inverse — writing pipeline output to an external API — is a separate concept with different concerns:

- Idempotency (how to safely retry failed writes without duplicating records).
- Partial failure handling (what happens if 7 of 10 pages write successfully but the 8th fails).
- Rate limit handling on write (more complex than on read, as writes may have tighter limits).
- Error responses that identify which records failed.

Write support is a meaningful extension of the connector concept but doubles the scope and introduces a distinct failure surface. It should be treated as a separate feature decision.

---

## 18. Extensibility & Future Directions

### Adding New Authentication Methods

The authentication system should be designed so that new methods can be added without changing existing functionality. Each method is an isolated implementation behind a shared interface: given a profile, inject credentials into a request. New providers (HMAC signing, Mutual TLS, API key with custom signing, Kerberos) should slot in without modifying existing handlers.

### Adding New Pagination Strategies

Similarly, new pagination strategies should be addable without modifying existing strategy code. The engine delegates to a strategy object; a new strategy is a new object that implements the shared iteration contract.

### Webhooks and Push-Based Integration

All strategies described so far are pull-based: the connector initiates requests on a schedule or on demand. Some APIs are push-based: they emit events to a registered endpoint when data changes. Webhook support is the natural complement to pull-based connectors and is a common next step:

- The platform exposes a webhook receive endpoint.
- The external API sends events to this endpoint as they occur.
- The platform processes incoming events in real time.

Webhooks and pull-based connectors are architecturally different (one is inbound, one is outbound) but semantically complementary. Combining both allows the platform to handle both scheduled batch ingestion and real-time event processing.

### Async Execution

A synchronous, sequential fetch model is appropriate for small-to-medium APIs and simple deployment environments. As data volumes grow or as the platform adds more concurrent users and pipeline runs, asynchronous execution becomes advantageous:

- Multiple pages can be fetched concurrently (where the API supports it).
- Rate limit delays do not block other work.
- Connection pool resources are not held during I/O waits.

Async execution is an optimization of the same concept, not a different concept.

### GraphQL and Non-REST APIs

This document focuses on REST APIs. GraphQL APIs, gRPC APIs, and SOAP services present different models. The Connection Profile + Endpoint abstraction generalizes: a GraphQL endpoint is still a profile + endpoint, but the request body is a query string, the response structure is strongly typed by the schema, and there is no pagination in the REST sense. These are distinct connector types sharing the same conceptual foundation.

---

## 19. What to Include vs. Exclude

Any implementation of this feature concept will face decisions about what to include and what to defer. These decisions should be driven by the business value delivered relative to implementation complexity, and by the real-world prevalence of each use case in the target user population.

### Guiding Principle

A connector that supports 80% of API patterns correctly is more valuable than one that supports 100% of patterns partially. Silent partial support — claiming to support a method but handling edge cases incorrectly — is worse than explicit non-support.

### Common Inclusion/Exclusion Patterns

| Capability                                 | Typically Included Early          | Notes                                                                                   |
| ------------------------------------------ | --------------------------------- | --------------------------------------------------------------------------------------- |
| No Auth, API Key, Basic Auth, Bearer Token | Yes                               | Covers the vast majority of public APIs. Low complexity, high coverage.                 |
| GET-based pagination (all 6 strategies)    | Yes                               | Partial pagination support causes silent data loss. All strategies must be complete.    |
| Schema inference (basic types)             | Yes                               | Manual schema definition at scale is impractical.                                       |
| Connection testing with diagnostics        | Yes                               | Eliminates hours of debugging misconfigured profiles.                                   |
| Data preview                               | Yes                               | Users need to validate configurations before deploying to pipelines.                    |
| Credential encryption                      | Yes                               | Non-negotiable security baseline.                                                       |
| SSRF protection                            | Yes (in cloud/shared deployments) | Non-negotiable in any shared network environment.                                       |
| POST-based data retrieval                  | Context-dependent                 | Required if the target API population uses POST for reads; otherwise deferrable.        |
| OAuth CC and OAuth AC                      | Context-dependent                 | High complexity; appropriate when organizational/private API access is a core use case. |
| Write operations (API as destination)      | Typically deferred                | Separate concern with separate failure surface; best addressed as a distinct feature.   |
| Webhooks / push-based ingestion            | Typically deferred                | Architecturally distinct from pull; significant scope addition.                         |
| Async execution                            | Typically deferred                | Optimization for scale; synchronous is correct for most MVP use cases.                  |

### Deliberate Exclusions Are Not Gaps

Explicitly not supporting something is different from failing to consider it. A well-reasoned exclusion with documented rationale is a feature decision, not a missing feature. It communicates what the connector does and does not do, sets correct user expectations, and ensures that what is included is well-implemented rather than partially done.

---

## Appendix A: Glossary

| Term                | Definition                                                                                                                                                                 |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Connection Profile  | The top-level configuration unit representing one external API: its base URL, authentication method, and credentials.                                                      |
| Endpoint            | A specific data resource within a Connection Profile — equivalent to a table. Includes path, method, parameters, and pagination.                                          |
| Data Root Path      | A dot-notation path into the API response JSON that points to the array of records (e.g.,`data.items`).                                                                  |
| Pagination Strategy | The method by which an API exposes multiple pages of data. One of: no pagination, limit-offset, page-size, cursor, next URL, link header.                                  |
| Schema Inference    | The automatic process of discovering field names and types from live API response data.                                                                                    |
| Schema Field        | One discovered or user-configured field in an endpoint's schema, with type, alias, null percentage, and inclusion flag.                                                    |
| Credentials Summary | Metadata about which credential fields are set (presence-only), surfaced to the frontend instead of actual values.                                                         |
| SSRF                | Server-Side Request Forgery. An attack where a crafted URL causes the server to make requests to unintended network targets.                                               |
| PKCE                | Proof Key for Code Exchange. A security extension to OAuth 2.0 Authorization Code flows that prevents authorization code interception attacks.                             |
| Fernet              | A symmetric encryption standard providing AES-128-CBC with an HMAC-SHA256 integrity check. Used as an example; the concept applies to any authenticated encryption scheme. |
| Key Rotation        | The process of replacing an encryption key with a new one, re-encrypting all data encrypted under the old key.                                                             |
| Circuit Breaker     | A resilience pattern that temporarily halts requests to a failing service after a threshold of consecutive failures, preventing resource exhaustion.                       |
| Cursor              | An opaque token returned by an API that represents a position in a paginated dataset. Used in cursor-based pagination.                                                     |
| Jitter              | A random component added to retry backoff delays to prevent synchronized retry storms from multiple clients.                                                               |
| Data Enrichment     | The process of augmenting existing pipeline records with additional fields sourced from an external API.                                                                   |

---

*This document is a living starting point. As project requirements, constraints, and technical context become clearer, specific sections should be expanded, revised, or scoped according to what is appropriate for that implementation.*