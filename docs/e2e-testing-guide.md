# API Connector — End-to-End Testing Guide

Complete walkthrough for creating and testing connection profiles across every authentication type, endpoint configuration variant, and pagination strategy supported by the app.

---

## How to Read This Guide

Each section follows the same structure:

```
Profile Setup → Connection Test → Endpoint Creation → Pagination → Schema
```

The first section (No Auth) is the most detailed — it walks through every UI field. Later sections only describe what changes for that auth type.

**Before you start:** App must be running and the database must be fresh (empty).

---

## Table of Contents

1. [Profile Information Fields (Reference)](#1-profile-information-fields-reference)
2. [No Auth — JSONPlaceholder](#2-no-auth--jsonplaceholder)
3. [API Key (Query Parameter) — NASA](#3-api-key-query-parameter--nasa)
4. [API Key (Header) — CoinGecko](#4-api-key-header--coingecko)
5. [Bearer Token — GitHub](#5-bearer-token--github)
6. [Basic Auth — HTTPBin](#6-basic-auth--httpbin)
7. [OAuth 2.0 Client Credentials — Spotify](#7-oauth-20-client-credentials--spotify)
8. [OAuth 2.0 Authorization Code — GitHub OAuth App](#8-oauth-20-authorization-code--github-oauth-app)
9. [Endpoint Configuration Deep-Dive](#9-endpoint-configuration-deep-dive)
10. [Pagination Strategies — All Six Variants](#10-pagination-strategies--all-six-variants)
11. [Connection Test Anatomy](#11-connection-test-anatomy)

---

## 1. Profile Information Fields (Reference)

Every new profile starts with this section. Fields are the same regardless of auth type.

| Field                               | Description                                                                            | Recommended value                                                          |
| ----------------------------------- | -------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| **Profile Name**              | Free-text label shown in the profile list                                              | Descriptive, e.g.`GitHub API (PAT)`                                      |
| **Base URL**                  | Root URL — no trailing slash, no path segments                                        | `https://api.example.com`                                                |
| **Request Timeout (seconds)** | Per-request timeout. Range: 1–120                                                     | `30` for most APIs; `10` for fast APIs; `60` for slow GraphQL/search |
| **Verify SSL Certificate**    | Checked by default. Uncheck only for local dev with self-signed certs                  | Leave checked for all public APIs                                          |
| **Default Headers**           | Headers sent on every request from this profile. For non-secret, non-auth headers only | `Accept: application/json`, `Content-Type: application/json`           |

> **Default Headers vs Auth credentials:** Default headers are stored unencrypted. Never put API keys or tokens here — use the Authentication section for those.

---

## 2. No Auth — JSONPlaceholder

**API:** `https://jsonplaceholder.typicode.com`
**Why:** No signup, no key, clean JSON, multiple resource types, predictable structure.

### 2.1 Create the Profile

1. Click **+ New Profile**
2. Fill in Profile Information:
   - **Profile Name:** `JSONPlaceholder`
   - **Base URL:** `https://jsonplaceholder.typicode.com`
   - **Request Timeout:** `30`
   - **Verify SSL:** checked
   - **Default Headers:** click **Add Header**
     - Name: `Accept` → Value: `application/json`
3. Under **Authentication**:
   - **Auth Type:** `No Auth`
   - The form shows: *"No credentials required for this auth type."*
4. Click **Create Profile**

### 2.2 Run a Connection Test

From the profile detail page, click **Test Connection**.

**What the test does:**

- Makes a GET request to the base URL (`https://jsonplaceholder.typicode.com`)
- Returns status code, response time, detected format, and a sample of the response body

**Expected result:**

- Status: `200`
- Format: `json`
- Response time: typically < 300ms
- Response body sample: the root page (an HTML welcome or a JSON response)

> If the base URL returns HTML, that is normal — the test only verifies reachability and auth. You configure the actual data path in the endpoint.

### 2.3 Create Endpoint: List Users

1. From the profile, go to **Endpoints** → **+ New Endpoint**
2. Fill in **Endpoint Configuration**:
   - **Name:** `List Users`
   - **Path:** `/users`
   - **Method:** `GET`
   - **Query Parameters:** (none for this endpoint)
   - **Endpoint Headers:** (none — `Accept` is already in Default Headers)
   - **Data Root Path:** (leave blank — response is a top-level array)
3. **Pagination Configuration:** `No Pagination`
4. Click **Create Endpoint**

**Verify:** The endpoint appears in the list with path `/users`.

### 2.4 Create Endpoint: Get Single User (Path Variable)

1. **+ New Endpoint**
2. Fill in:
   - **Name:** `Get User`
   - **Path:** `/users/{userId}`
   - **Method:** `GET`
3. Once you type `/users/{userId}`, the form auto-detects `userId` and shows a **Path Variables** section.
4. In **Path Variables**, enter a static test value:
   - `userId` → `1`
5. **Data Root Path:** (blank — response is a single object)
6. **Pagination:** `No Pagination`
7. Click **Create Endpoint**

### 2.5 Create Endpoint: List Posts (with Query Params)

1. **+ New Endpoint**
2. Fill in:
   - **Name:** `List Posts by User`
   - **Path:** `/posts`
   - **Method:** `GET`
3. **Query Parameters** — click **Add** for each:
   - `userId` → `1`
4. **Data Root Path:** (blank — top-level array)
5. **Pagination:** `No Pagination`
6. Click **Create Endpoint**

**Live URL being called:** `https://jsonplaceholder.typicode.com/posts?userId=1`

### 2.6 Create Endpoint: Create a Post (POST)

1. **+ New Endpoint**
2. Fill in:
   - **Name:** `Create Post`
   - **Path:** `/posts`
   - **Method:** `POST`
3. A **Request Body (JSON)** textarea appears when you select POST. Enter:
   ```json
   {
     "title": "Test Post",
     "body": "This is a test.",
     "userId": 1
   }
   ```
4. **Pagination:** `No Pagination`
5. Click **Create Endpoint**

> JSONPlaceholder accepts POST requests and returns a fake `201` response with a generated ID. It does not actually persist data.

---

## 3. API Key (Query Parameter) — NASA

**API:** `https://api.nasa.gov`
**Key param name:** `api_key`
**Free key:** Use `DEMO_KEY` for instant testing (no signup). Rate limit: 30 req/hour.
**Full key signup:** https://api.nasa.gov (gives 1,000 req/day)

### 3.1 Create the Profile

1. **+ New Profile**
2. Profile Information:
   - **Profile Name:** `NASA APIs`
   - **Base URL:** `https://api.nasa.gov`
   - **Request Timeout:** `30`
   - **Default Headers:** `Accept: application/json`
3. **Authentication → Auth Type:** `API Key`
4. Auth fields appear:
   - **Key Name:** `api_key`
   - **Key Value:** `DEMO_KEY` *(or your actual key)*
   - **Delivery Method:** `Query Parameter`
   - **Prefix:** (leave blank — NASA does not use a prefix)
5. Click **Create Profile**

**How it works:** Every request from this profile will automatically append `?api_key=DEMO_KEY` to the URL (or `&api_key=DEMO_KEY` if other query params already exist).

### 3.2 Test Connection

Click **Test Connection**. Expected: `200`, format `json`.

> The test hits `https://api.nasa.gov?api_key=DEMO_KEY`. NASA's root returns a JSON welcome response.

### 3.3 Create Endpoint: Astronomy Picture of the Day (APOD)

1. **+ New Endpoint**
2. Fill in:
   - **Name:** `Astronomy Picture of the Day`
   - **Path:** `/planetary/apod`
   - **Method:** `GET`
   - **Query Parameters:** (none needed — `api_key` is injected automatically)
3. **Data Root Path:** (blank — single object response)
4. **Pagination:** `No Pagination`
5. Click **Create Endpoint**

**Live URL:** `https://api.nasa.gov/planetary/apod?api_key=DEMO_KEY`

### 3.4 Create Endpoint: Near Earth Objects (Paginated)

1. **+ New Endpoint**
2. Fill in:
   - **Name:** `Near Earth Objects`
   - **Path:** `/neo/rest/v1/neo/browse`
   - **Method:** `GET`
   - **Data Root Path:** `near_earth_objects`
3. **Pagination Configuration:**
   - **Strategy:** `Page / Size`
   - `page_param`: `page`
   - `page_size_param`: `size`
   - `page_size`: `20`
   - `total_pages_path`: `page.total_pages`
   - `max_pages`: `5`
   - `max_records`: `100`
4. Click **Create Endpoint**

---

## 4. API Key (Header) — CoinGecko

**API:** `https://api.coingecko.com/api/v3`
**Header name:** `x-cg-demo-api-key`
**Get a key:** https://www.coingecko.com/en/api (free demo tier, no credit card)

### 4.1 Create the Profile

1. **+ New Profile**
2. Profile Information:
   - **Profile Name:** `CoinGecko`
   - **Base URL:** `https://api.coingecko.com/api/v3`
   - **Request Timeout:** `30`
3. **Authentication → Auth Type:** `API Key`
4. Auth fields:
   - **Key Name:** `x-cg-demo-api-key`
   - **Key Value:** `<your-demo-api-key>`
   - **Delivery Method:** `Header`
   - **Prefix:** (leave blank)
5. Click **Create Profile**

**How it works:** Every request will include the HTTP header `x-cg-demo-api-key: <your-key>`.

### 4.2 Prefix Field — When to Use It

The **Prefix** field prepends a string before the key value in the header. Examples:

| API          | Header Name           | Key Value  | Prefix     | Result sent                      |
| ------------ | --------------------- | ---------- | ---------- | -------------------------------- |
| CoinGecko    | `x-cg-demo-api-key` | `abc123` | (blank)    | `x-cg-demo-api-key: abc123`    |
| Some APIs    | `Authorization`     | `abc123` | `Token`  | `Authorization: Token abc123`  |
| Abstract API | `Authorization`     | `abc123` | `Bearer` | `Authorization: Bearer abc123` |

> For true Bearer token auth, use the **Bearer Token** auth type instead — it uses `Authorization` header by default with no prefix configuration needed.

### 4.3 Test Connection

Test Connection → Expected: `200`, format `json`.

### 4.4 Create Endpoint: Coin List

1. **+ New Endpoint**
2. Fill in:
   - **Name:** `Coin List`
   - **Path:** `/coins/list`
   - **Method:** `GET`
3. **Data Root Path:** (blank — top-level array)
4. **Pagination:** `No Pagination` (CoinGecko's `/coins/list` returns the full list in one call)
5. Click **Create Endpoint**

### 4.5 Create Endpoint: Coin Markets (Paginated)

1. **+ New Endpoint**
2. Fill in:
   - **Name:** `Coin Markets`
   - **Path:** `/coins/markets`
   - **Method:** `GET`
   - **Query Parameters:**
     - `vs_currency` → `usd`
     - `order` → `market_cap_desc`
3. **Data Root Path:** (blank — top-level array)
4. **Pagination Configuration:**
   - **Strategy:** `Page / Size`
   - `page_param`: `page`
   - `page_size_param`: `per_page`
   - `page_size`: `50`
   - `max_pages`: `10`
   - `max_records`: `500`
5. Click **Create Endpoint**

---

## 5. Bearer Token — GitHub

**API:** `https://api.github.com`
**Token type:** Personal Access Token (classic or fine-grained)
**Get a token:** GitHub → Settings → Developer Settings → Personal Access Tokens

**Recommended scopes for testing:**

- `repo` (read access to repositories)
- `read:user` (user profile)
- `read:org` (organization membership)

### 5.1 Create the Profile

1. **+ New Profile**
2. Profile Information:
   - **Profile Name:** `GitHub API`
   - **Base URL:** `https://api.github.com`
   - **Request Timeout:** `30`
   - **Default Headers:**
     - `Accept: application/vnd.github+json`
     - `X-GitHub-Api-Version: 2022-11-28`
3. **Authentication → Auth Type:** `Bearer Token`
4. Auth fields:
   - **Token:** `ghp_xxxxxxxxxxxxxxxxxxxx` *(your PAT)*
   - **Header Name:** `Authorization` *(default — leave as-is)*
5. Click **Create Profile**

**How it works:** Every request includes `Authorization: Bearer ghp_xxxx`.

> The **Header Name** field lets you override `Authorization` if a non-standard API expects the token in a different header. For GitHub, always leave it as `Authorization`.

### 5.2 Test Connection

Test Connection → Expected: `200`, format `json`.

The test hits `https://api.github.com` which returns a JSON map of all available API endpoints — a perfect connectivity check.

### 5.3 Create Endpoint: Authenticated User

1. **+ New Endpoint**
2. Fill in:
   - **Name:** `Get Authenticated User`
   - **Path:** `/user`
   - **Method:** `GET`
3. **Data Root Path:** (blank — single object)
4. **Pagination:** `No Pagination`
5. Click **Create Endpoint**

### 5.4 Create Endpoint: List Repos (Paginated, Link Header)

GitHub uses RFC 5988 `Link` header pagination — the response includes a header like:

```
Link: <https://api.github.com/user/repos?page=2>; rel="next", <https://api.github.com/user/repos?page=5>; rel="last"
```

1. **+ New Endpoint**
2. Fill in:
   - **Name:** `My Repositories`
   - **Path:** `/user/repos`
   - **Method:** `GET`
   - **Query Parameters:**
     - `per_page` → `30`
     - `sort` → `updated`
3. **Data Root Path:** (blank — top-level array)
4. **Pagination Configuration:**
   - **Strategy:** `Link Header`
   - `max_pages`: `10`
   - `max_records`: `300`
   - `inter_page_delay_ms`: `100` *(be polite to GitHub's rate limiter)*
   - `max_retries`: `3`
5. Click **Create Endpoint**

> Link Header strategy needs no params — it reads the `Link` response header automatically and follows the `rel="next"` URL.

### 5.5 Create Endpoint: Search Repos (Path Variable)

1. **+ New Endpoint**
2. Fill in:
   - **Name:** `Get Repo`
   - **Path:** `/repos/{owner}/{repo}`
   - **Method:** `GET`
3. Path variables auto-detected: `owner`, `repo`
4. In **Path Variables:**
   - `owner` → `octocat`
   - `repo` → `Hello-World`
5. **Data Root Path:** (blank — single object)
6. **Pagination:** `No Pagination`
7. Click **Create Endpoint**

---

## 6. Basic Auth — HTTPBin

**API:** `https://httpbin.org`
**Purpose:** HTTPBin is purpose-built for testing HTTP features. The `/basic-auth/{user}/{pass}` endpoint accepts any username/password you embed in the URL path and returns `200` if credentials match — perfect for validating Basic Auth wiring.

### 6.1 Create the Profile

1. **+ New Profile**
2. Profile Information:
   - **Profile Name:** `HTTPBin Basic Auth`
   - **Base URL:** `https://httpbin.org`
   - **Request Timeout:** `15`
3. **Authentication → Auth Type:** `Basic Auth`
4. Auth fields:
   - **Username:** `testuser`
   - **Password:** `secret123`
5. Click **Create Profile**

**How it works:** The connector encodes `testuser:secret123` as Base64 and sends `Authorization: Basic dGVzdHVzZXI6c2VjcmV0MTIz` on every request.

### 6.2 Test Connection

Test Connection → Expected: `200`, format `json`.

HTTPBin's root (`/`) returns a JSON response confirming the server is reachable.

### 6.3 Create Endpoint: Basic Auth Verification

This endpoint proves credentials are being sent correctly.

1. **+ New Endpoint**
2. Fill in:
   - **Name:** `Verify Basic Auth`
   - **Path:** `/basic-auth/testuser/secret123`
   - **Method:** `GET`
3. **Data Root Path:** (blank — response: `{"authenticated": true, "user": "testuser"}`)
4. **Pagination:** `No Pagination`
5. Click **Create Endpoint**

**Expected response:**

```json
{ "authenticated": true, "user": "testuser" }
```

**To test failure:** Create a second profile with wrong credentials and hit the same endpoint — expect `401`.

### 6.4 Create Endpoint: Inspect Headers Being Sent

1. **+ New Endpoint**
2. Fill in:
   - **Name:** `Inspect Request Headers`
   - **Path:** `/headers`
   - **Method:** `GET`
3. **Data Root Path:** `headers`
4. **Pagination:** `No Pagination`
5. Click **Create Endpoint**

**Expected response (after data root path applied):**

```json
{
  "Accept": "application/json",
  "Authorization": "Basic dGVzdHVzZXI6c2VjcmV0MTIz",
  "Host": "httpbin.org"
}
```

This confirms the `Authorization` header is being constructed and sent correctly by the connector.

---

## 7. OAuth 2.0 Client Credentials — Spotify

**API:** `https://api.spotify.com/v1`
**Token URL:** `https://accounts.spotify.com/api/token`
**Signup:** https://developer.spotify.com/dashboard → Create App
**Scopes needed:** none (Client Credentials flow is scoped to public catalog data)

**Get credentials:**

1. Log in at https://developer.spotify.com/dashboard
2. Click **Create App** → fill in name/description → set redirect URI to `http://localhost:8080` (placeholder, not used in CC flow)
3. Note your **Client ID** and **Client Secret**

### 7.1 Create the Profile

1. **+ New Profile**
2. Profile Information:
   - **Profile Name:** `Spotify API (Client Credentials)`
   - **Base URL:** `https://api.spotify.com/v1`
   - **Request Timeout:** `30`
   - **Default Headers:** `Accept: application/json`
3. **Authentication → Auth Type:** `OAuth Client Credentials`
4. Auth fields:
   - **Client ID:** `<your-spotify-client-id>`
   - **Client Secret:** `<your-spotify-client-secret>`
   - **Token Endpoint URL:** `https://accounts.spotify.com/api/token`
   - **Scopes:** (leave blank — Spotify CC flow doesn't require scopes for public data)
5. Click **Create Profile**

**How it works:**

1. Before each request (or when the token expires), the connector POSTs to `https://accounts.spotify.com/api/token` with `grant_type=client_credentials` and your credentials.
2. The response token (`Bearer eyJxx...`) is stored encrypted and injected into subsequent API calls automatically.

### 7.2 Test Connection

Test Connection → Expected: `200`, format `json`.

> The test first fetches a token from the token endpoint, then uses it to call `https://api.spotify.com/v1`. A successful response confirms the full OAuth CC round-trip is working.

### 7.3 Create Endpoint: Search Tracks

1. **+ New Endpoint**
2. Fill in:
   - **Name:** `Search Tracks`
   - **Path:** `/search`
   - **Method:** `GET`
   - **Query Parameters:**
     - `q` → `Beatles`
     - `type` → `track`
     - `limit` → `20`
3. **Data Root Path:** `tracks.items`
4. **Pagination Configuration:**
   - **Strategy:** `Offset / Limit`
   - `offset_param`: `offset`
   - `limit_param`: `limit`
   - `page_size`: `20`
   - `max_pages`: `5`
   - `max_records`: `100`
5. Click **Create Endpoint**

**Response structure:**

```json
{
  "tracks": {
    "href": "...",
    "items": [ ... ],
    "limit": 20,
    "offset": 0,
    "total": 1000
  }
}
```

**Data Root Path** `tracks.items` extracts the array. `record_count_path` would be `tracks.total` if you want to track total available records.

### 7.4 Create Endpoint: Get Artist

1. **+ New Endpoint**
2. Fill in:
   - **Name:** `Get Artist`
   - **Path:** `/artists/{artist_id}`
   - **Method:** `GET`
3. Path variable detected: `artist_id`
4. **Path Variables:** `artist_id` → `0TnOYISbd1XYRBk9myaseg` *(Pitbull's Spotify ID — public)*
5. **Data Root Path:** (blank)
6. **Pagination:** `No Pagination`
7. Click **Create Endpoint**

---

## 8. OAuth 2.0 Authorization Code — GitHub OAuth App

This flow requires a browser redirect. The connector handles the callback automatically.

**Signup:** GitHub → Settings → Developer Settings → OAuth Apps → New OAuth App

**OAuth App settings to configure in GitHub:**

- **Application name:** `API Connector Test`
- **Homepage URL:** `http://localhost:5173`
- **Authorization callback URL:** Check your app's OAuth callback URL. Typically: `http://localhost:8000/api/oauth/callback/` *(verify in your backend URL config)*

**Note your:**

- `Client ID` (shown on the OAuth App page)
- `Client Secret` (click "Generate a new client secret")

### 8.1 Create the Profile (Step 1 — Save First)

> OAuth AC requires a two-step process: **save credentials first**, then **authorize**.

1. **+ New Profile**
2. Profile Information:
   - **Profile Name:** `GitHub OAuth App`
   - **Base URL:** `https://api.github.com`
   - **Request Timeout:** `30`
   - **Default Headers:**
     - `Accept: application/vnd.github+json`
     - `X-GitHub-Api-Version: 2022-11-28`
3. **Authentication → Auth Type:** `OAuth Authorization Code`
4. Auth fields (all inherited from OAuth CC, plus one extra):
   - **Client ID:** `<your-oauth-app-client-id>`
   - **Client Secret:** `<your-oauth-app-client-secret>`
   - **Token Endpoint URL:** `https://github.com/login/oauth/access_token`
   - **Scopes:** `repo read:user`
   - **Authorization Endpoint URL:** `https://github.com/login/oauth/authorize`
5. Notice the **Browser Authorization** section shows: *"Save the profile first, then return to authorize."*
6. Click **Create Profile**

### 8.2 Authorize (Step 2 — Browser Popup)

After saving, you are redirected to the profile edit page.

1. Scroll to **Authentication → Browser Authorization**
2. The **Authorize** button is now enabled (credentials are saved)
3. Click **Authorize**
4. A browser window/popup opens to GitHub's login + consent page
5. GitHub asks you to authorize the app for the scopes you specified
6. Click **Authorize \<your-app-name\>**
7. GitHub redirects to your callback URL; the connector exchanges the code for a token
8. The status badge updates to **Authorized**

> If the button shows "Waiting for browser…" — the popup is open. Complete the GitHub consent flow. If the popup was blocked, allow popups for localhost.

### 8.3 Test Connection

Test Connection → Expected: `200`, format `json`.

This test now uses the stored access token in `Authorization: Bearer <token>`, proving the full auth code flow succeeded.

### 8.4 Re-Authorization

When the token expires or access is revoked:

1. Edit the profile
2. Click **Re-Authorize** in the Browser Authorization section
3. Complete the GitHub consent flow again

### 8.5 Endpoints

Endpoints for GitHub OAuth App are identical to section 5 (Bearer Token / GitHub). The difference is that the OAuth AC token represents a specific user who consented, while PAT tokens represent the token owner directly.

---

## 9. Endpoint Configuration Deep-Dive

### 9.1 Path Variables

Path variables are declared using `{variableName}` syntax in the **Path** field.

```
/repos/{owner}/{repo}/issues/{issue_number}
```

The form auto-detects all `{variable}` placeholders and renders an input for each. You provide static default values — these are used as the test/preview values.

**Rules:**

- Variable names must be alphanumeric + underscores only (no hyphens)
- Each detected variable must have a non-empty value
- Values are URL-encoded automatically

### 9.2 Query Parameters

Static key-value pairs appended to the URL for every call through this endpoint.

**What goes here vs. auth:**

- Query params here: `format=json`, `lang=en`, `fields=id,name`
- Auth key (if using Query Parameter delivery): handled automatically via the profile's auth config — do not duplicate it here

**Example — DummyJSON paginated products:**

```
/products?select=title,price,category
```

- `select` → `title,price,category`

### 9.3 Endpoint Headers

Per-endpoint headers that are merged with (and can override) the profile's Default Headers.

**Use cases:**

- `Content-Type: application/x-www-form-urlencoded` for a specific POST endpoint
- `X-Request-Source: api-connector` for audit logging

### 9.4 Request Body (POST only)

Appears only when **Method** is `POST`. Must be valid JSON.

```json
{
  "query": "SELECT id, name FROM users LIMIT 100",
  "format": "json"
}
```

**Important:** Never put credentials in the request body. The app enforces this with a UI warning. Auth credentials belong in the profile's Authentication section.

### 9.5 Data Root Path

Dot-notation path to the array of records within the response.

| API response shape                                   | Data Root Path             |
| ---------------------------------------------------- | -------------------------- |
| `[ {...}, {...} ]`                                 | (blank — top-level array) |
| `{ "data": [ ... ] }`                              | `data`                   |
| `{ "results": { "items": [ ... ] } }`              | `results.items`          |
| `{ "response": { "data": { "users": [ ... ] } } }` | `response.data.users`    |

**Rules:**

- Alphanumeric + underscores + dots only
- Each segment separated by `.` must be non-empty
- Invalid: `data..items`, `.data`, `data.`

### 9.6 Record Count Path

Optional. Dot-notation path to the total record count field in the response.

| API response                              | Record Count Path       |
| ----------------------------------------- | ----------------------- |
| `{ "total": 500, "data": [...] }`       | `total`               |
| `{ "meta": { "total_count": 500 } }`    | `meta.total_count`    |
| `{ "page": { "total_elements": 500 } }` | `page.total_elements` |

Used for informational display and to detect when to stop pagination early.

---

## 10. Pagination Strategies — All Six Variants

### 10.1 No Pagination

**When to use:** Single-page responses, small datasets, detail endpoints.

**Config required:** None.

**Example API:** `https://jsonplaceholder.typicode.com/users`

---

### 10.2 Offset / Limit

Server advances by offset position. Client sends `offset=0`, then `offset=20`, then `offset=40`, etc.

**Config fields:**

| Field                   | Description                  | Example    |
| ----------------------- | ---------------------------- | ---------- |
| `offset_param`        | URL param name for offset    | `offset` |
| `limit_param`         | URL param name for page size | `limit`  |
| `page_size`           | Records per page             | `20`     |
| `max_pages`           | Hard stop on page count      | `50`     |
| `max_records`         | Hard stop on total records   | `1000`   |
| `inter_page_delay_ms` | Delay between requests (ms)  | `0`      |
| `max_retries`         | Retry count on 429/5xx       | `3`      |

**Example: PokeAPI**

- **Profile Base URL:** `https://pokeapi.co/api/v2`
- **Endpoint Path:** `/pokemon`
- **Data Root Path:** `results`
- **Record Count Path:** `count`
- Pagination:
  - `offset_param`: `offset`
  - `limit_param`: `limit`
  - `page_size`: `100`
  - `max_pages`: `10`

**Example: Spotify Search (from section 7.3)**

- `offset_param`: `offset`
- `limit_param`: `limit`
- `page_size`: `20`

---

### 10.3 Page / Size

Server advances by page number. Client sends `page=1`, then `page=2`, etc.

**Config fields:**

| Field                | Description                                                  | Example            |
| -------------------- | ------------------------------------------------------------ | ------------------ |
| `page_param`       | URL param name for page number                               | `page`           |
| `page_size_param`  | URL param name for page size                                 | `per_page`       |
| `page_size`        | Records per page                                             | `30`             |
| `total_pages_path` | Dot-notation path to total page count in response (optional) | `meta.last_page` |
| `max_pages`        | Hard stop                                                    | `20`             |
| `max_records`      | Hard stop                                                    | `500`            |

**Example: DummyJSON**

- **Profile Base URL:** `https://dummyjson.com`
- **Endpoint Path:** `/products`
- **Data Root Path:** `products`
- **Record Count Path:** `total`
- Pagination:
  - `page_param`: `skip` *(DummyJSON uses skip, not page — use Offset/Limit instead for this one)*

**Better Page/Size example: CoinGecko Markets (section 4.5)**

- `page_param`: `page`
- `page_size_param`: `per_page`
- `page_size`: `50`

**Better Page/Size example: NASA Near Earth Objects (section 3.4)**

- `page_param`: `page`
- `page_size_param`: `size`
- `page_size`: `20`
- `total_pages_path`: `page.total_pages`

---

### 10.4 Cursor

Server returns an opaque cursor string. Client sends cursor in next request. Cursor changes every page — you cannot jump to a specific page.

**Config fields:**

| Field                    | Description                             | Example              |
| ------------------------ | --------------------------------------- | -------------------- |
| `cursor_request_param` | URL param name to send cursor           | `after`            |
| `cursor_response_path` | Dot-notation path to cursor in response | `meta.next_cursor` |
| `max_pages`            | Hard stop                               | `20`               |
| `max_records`          | Hard stop                               | `500`              |

**Example: Airtable**

- **Profile Base URL:** `https://api.airtable.com/v0`
- **Auth Type:** Bearer Token → your Airtable personal access token
- **Endpoint Path:** `/{baseId}/{tableId}`
- **Path Variables:**
  - `baseId` → `appXXXXXXXXXXXXXX`
  - `tableId` → `tblXXXXXXXXXXXXXX`
- **Data Root Path:** `records`
- Pagination:
  - `cursor_request_param`: `offset`
  - `cursor_response_path`: `offset`
  - `max_pages`: `20`

> Airtable's "cursor" is named `offset` in both request and response, but it is an opaque string — not an integer position. Use Cursor strategy, not Offset/Limit.

---

### 10.5 Next URL

Server includes the full URL for the next page directly in the response body. Client follows it verbatim.

**Config fields:**

| Field                      | Description                                    | Example  |
| -------------------------- | ---------------------------------------------- | -------- |
| `next_url_response_path` | Dot-notation path to next page URL in response | `next` |
| `max_pages`              | Hard stop                                      | `20`   |
| `max_records`            | Hard stop                                      | `500`  |

**Example: PokeAPI (alternative to Offset/Limit)**

- **Response shape:**
  ```json
  {
    "count": 1302,
    "next": "https://pokeapi.co/api/v2/pokemon?offset=100&limit=100",
    "previous": null,
    "results": [ ... ]
  }
  ```
- Pagination:
  - `next_url_response_path`: `next`
  - `max_pages`: `5`

**Example: DummyJSON**

- `/products` response doesn't include next URL — use Offset/Limit instead.

**Example: Django REST Framework APIs (your own backend)**

- DRF's default pagination returns `{ "next": "http://...", "previous": "...", "results": [...] }`
- `next_url_response_path`: `next`
- `data_root_path`: `results`

---

### 10.6 Link Header

Server sends the next page URL in an HTTP response header (`Link: <url>; rel="next"`). RFC 5988 format. Response body contains no pagination info.

**Config fields:**

| Field                   | Description                                                   |
| ----------------------- | ------------------------------------------------------------- |
| `max_pages`           | Hard stop                                                     |
| `max_records`         | Hard stop                                                     |
| `inter_page_delay_ms` | Delay between requests — important for GitHub's rate limiter |

No `strategy_params` required. The connector reads the `Link` header automatically.

**Example: GitHub Repos (section 5.4)**

- `/user/repos`
- `max_pages`: `10`
- `inter_page_delay_ms`: `100`
- `max_retries`: `3`

**Example: GitLab Issues**

- **Profile Base URL:** `https://gitlab.com/api/v4`
- **Auth Type:** Bearer Token → GitLab personal access token
- **Endpoint Path:** `/projects/{project_id}/issues`
- **Path Variables:** `project_id` → your project ID (numeric)
- **Query Parameters:** `state` → `opened`
- **Data Root Path:** (blank — top-level array)
- Pagination: Link Header, `max_pages`: `20`, `inter_page_delay_ms`: `50`

---

## 11. Connection Test Anatomy

### What the Test Does

When you click **Test Connection**, the connector:

1. Resolves auth credentials (fetches OAuth token if needed, reads stored encrypted key/token)
2. Makes a GET request to the **Base URL** with all auth headers applied
3. Records: status code, response time (ms), detected content format, and up to 2KB of the response body as a sample

### Test Result Fields

| Field           | What it means                                 |
| --------------- | --------------------------------------------- |
| Status Code     | HTTP response code from the server            |
| Response Time   | End-to-end latency in milliseconds            |
| Detected Format | `json`, `xml`, `csv`, or `plain_text` |
| Response Sample | First ~2KB of the response body               |

### Interpreting Results

| Status  | Likely cause                                                          |
| ------- | --------------------------------------------------------------------- |
| `200` | Connection and auth are working                                       |
| `401` | Credentials are wrong or missing                                      |
| `403` | Credentials are valid but lack permission for the base URL            |
| `404` | Base URL path doesn't exist — check for trailing slash or wrong path |
| `429` | Rate limited — wait and retry                                        |
| `5xx` | Server-side error — likely unrelated to your config                  |
| Timeout | Server unreachable, SSL handshake failure, or timeout set too low     |

### Common Issues by Auth Type

| Auth Type             | Common failure               | Fix                                                                           |
| --------------------- | ---------------------------- | ----------------------------------------------------------------------------- |
| API Key (Query Param) | `401` — key not sent      | Check Key Name matches what the API expects exactly (case-sensitive)          |
| API Key (Header)      | `403` — key rejected      | Verify the key is still valid in the provider dashboard                       |
| Bearer Token          | `401` — token expired     | Regenerate the PAT in GitHub/GitLab settings, update the profile              |
| Basic Auth            | `401` — wrong credentials | Double-check username and password; some APIs use email as username           |
| OAuth CC              | `invalid_client`           | Client ID or Secret is wrong; check for extra spaces                          |
| OAuth CC              | `401` on API               | Token endpoint returned a token but it was rejected — check scopes           |
| OAuth AC              | Authorize button disabled    | Save the profile with all credentials filled in first, then come back to edit |
| OAuth AC              | Popup blocked                | Allow popups for your localhost origin in browser settings                    |

---

## Quick Reference: All Supported Auth Types

| Auth Type                | Identifier   | Required Fields                                  | How Credentials Are Sent                       |
| ------------------------ | ------------ | ------------------------------------------------ | ---------------------------------------------- |
| No Auth                  | `none`     | —                                               | Nothing added                                  |
| API Key                  | `api_key`  | key_name, key_value, delivery                    | As query param or header                       |
| Bearer Token             | `bearer`   | token, header_name (default: Authorization)      | `Authorization: Bearer <token>`              |
| Basic Auth               | `basic`    | username, password                               | `Authorization: Basic <base64>`              |
| OAuth Client Credentials | `oauth_cc` | client_id, client_secret, token_endpoint, scopes | Token fetched automatically, sent as Bearer    |
| OAuth Authorization Code | `oauth_ac` | All CC fields + authorization_endpoint           | Token fetched via browser flow, sent as Bearer |

## Quick Reference: All Pagination Strategies

| Strategy       | Identifier        | Required Params                            | Best For                                           |
| -------------- | ----------------- | ------------------------------------------ | -------------------------------------------------- |
| No Pagination  | `no_pagination` | —                                         | Detail endpoints, small fixed datasets             |
| Offset / Limit | `offset_limit`  | offset_param, limit_param, page_size       | Most REST APIs (PokeAPI, Spotify)                  |
| Page / Size    | `page_size`     | page_param, page_size_param, page_size     | Page-numbered APIs (CoinGecko, NASA)               |
| Cursor         | `cursor`        | cursor_request_param, cursor_response_path | Airtable, Slack, Stripe                            |
| Next URL       | `next_url`      | next_url_response_path                     | PokeAPI, DRF APIs, any API returning full next URL |
| Link Header    | `link_header`   | (none)                                     | GitHub, GitLab (RFC 5988`Link` header)           |
