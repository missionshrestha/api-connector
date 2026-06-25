# Phase 8 Benchmark Results

## Environment

| Component | Version / Spec |
|---|---|
| Machine | [FILL IN: e.g., MacBook Pro M3, 16GB RAM] |
| Python | 3.11.x |
| Django | 4.2.x |
| PostgreSQL | 15.x |
| Node.js | 22.x |
| Test API | [FILL IN: e.g., jsonplaceholder.typicode.com or internal dev API] |

## Results

| Operation | NFR Target (ms) | Measured Median (ms) | p95 (ms) | Status | Notes |
|---|---|---|---|---|---|
| profile_list | 500 | [FILL IN] | [FILL IN] | [✓ PASS / ✗ FAIL] | 50 profiles, 5 iterations |
| schema_explorer | 500 | [FILL IN] | [FILL IN] | [✓ PASS / ✗ FAIL] | 250 SchemaField rows, 5 iterations |
| connection_test | 5000 | [FILL IN] | [FILL IN] | [✓ PASS / ✗ FAIL] | DNS + network + auth + HTTP; target API latency included |
| schema_inference | 15000 | [FILL IN] | [FILL IN] | [✓ PASS / ✗ FAIL] | Up to 300 records (3 pages); includes pagination |
| data_preview | 10000 | [FILL IN] | [FILL IN] | [✓ PASS / ✗ FAIL] | 25 rows, aliased columns |

## Methodology

Run via: `python manage.py benchmark [--operation <name>] [--iterations 5]`

- `profile_list` and `schema_explorer`: DB-only operations; timed using Django test client; 5 iterations, median reported
- `connection_test`, `schema_inference`, `data_preview`: Network-dependent; single run against `[TEST_API_BASE_URL]`
- All timings include Django request processing + DB queries + (for network ops) external API round-trip

## Identified Bottlenecks and Resolutions

### profile_list — icontains Search Limitation
The `?search=` filter uses `name__icontains` which generates `LIKE '%term%'` (leading wildcard). PostgreSQL's B-tree index on the `name` column **cannot** optimize leading-wildcard queries. For production deployments expecting heavy search usage, consider a PostgreSQL trigram index (`pg_trgm` extension). This is acceptable for MVP scope.

### N+1 Queries — All Present
The following ORM optimizations were verified in place:
- `ConnectionProfileViewSet.get_queryset()`: `select_related('auth_config').prefetch_related('oauth_tokens')`
- `EndpointViewSet.get_queryset()`: `select_related('pagination_config')`
- `SchemaField` queries: `filter(endpoint=endpoint, include=True)` covered by `(endpoint_id, include)` composite index

### Network-Dependent Operations
NFR targets for `connection_test`, `schema_inference`, and `data_preview` assume the target API responds within its configured `request_timeout`. Results above reflect actual external API latency and are environment-specific.

## Limitations

1. **Leading-wildcard search**: `profile_list?search=` with a prefix uses the name index; with a leading wildcard it does not. Document to users that the search is most efficient for suffix-free patterns.
2. **Environment variance**: Network-dependent benchmarks vary with API latency. Run from the same network as the target API for representative results.
3. **Django test client**: Bypasses HTTP stack (no TCP, no SSL negotiation). Profile list and schema explorer timings reflect pure Django + DB time, which is a slight underestimate vs. real HTTP.

## Baseline for Future Comparison

Re-run `python manage.py benchmark` after any changes to:
- `ConnectionProfileViewSet.get_queryset()` or its serializers
- `SchemaField` query patterns in `SchemaInferenceEngine` or `DataPreviewService`
- Migration additions that change table structure or indexes

Report regressions > 20% of the baseline values above.
