# backend/api_connector/management/commands/benchmark.py
"""
Benchmark management command for NFR validation.

Usage:
  python manage.py benchmark
  python manage.py benchmark --operation profile_list
  python manage.py benchmark --operation schema_explorer --endpoint-id 5
  python manage.py benchmark --profile-id 1 --endpoint-id 5

SAFETY: Refuses to run with DEBUG=False (production guard).
        Benchmark records are created in the active database — use dev DB only.
        Use --destructive-cleanup to delete created benchmark records after timing.
"""
import time
import statistics

from django.core.management.base import BaseCommand, CommandError
from django.test import Client
from django.conf import settings


class Command(BaseCommand):
    help = (
        "Benchmark API operations against NFR targets. "
        "Run against the dev database ONLY (refuses to run when DEBUG=False)."
    )

    NFR_TARGETS_MS = {
        "profile_list": 500,
        "schema_explorer": 500,
        "connection_test": 5000,
        "schema_inference": 15000,
        "data_preview": 10000,
    }

    def add_arguments(self, parser):
        parser.add_argument(
            "--operation",
            choices=list(self.NFR_TARGETS_MS.keys()) + ["all"],
            default="all",
            help="Which operation to benchmark (default: all)",
        )
        parser.add_argument(
            "--profile-id",
            type=int,
            help="ConnectionProfile PK for network-dependent operations",
        )
        parser.add_argument(
            "--endpoint-id",
            type=int,
            help="Endpoint PK for endpoint-scoped operations",
        )
        parser.add_argument(
            "--iterations",
            type=int,
            default=5,
            help="Number of timing iterations for DB-only operations (default: 5)",
        )
        parser.add_argument(
            "--destructive-cleanup",
            action="store_true",
            help="Delete benchmark-created records after timing",
        )

    def handle(self, *args, **options):
        # Production guard
        if not settings.DEBUG:
            raise CommandError(
                "Benchmark refuses to run with DEBUG=False. "
                "This command creates test data and should only run against the dev database. "
                "Set DEBUG=True in your environment if you are certain this is a dev database."
            )

        # Django's test Client sends requests with host "testserver", which is not
        # in the dev ALLOWED_HOSTS. The test runner normally appends it via
        # setup_test_environment(); this command runs outside that, so do it here.
        if "testserver" not in settings.ALLOWED_HOSTS:
            settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, "testserver"]

        operation = options["operation"]
        operations_to_run = (
            list(self.NFR_TARGETS_MS.keys())
            if operation == "all"
            else [operation]
        )

        results = {}
        created_profile_pk = None
        created_field_pks = []

        self.stdout.write("\n" + "═" * 60)
        self.stdout.write("  Phase 8 NFR Benchmark")
        self.stdout.write("═" * 60 + "\n")

        for op in operations_to_run:
            nfr_ms = self.NFR_TARGETS_MS[op]
            try:
                if op == "profile_list":
                    timing_ms, notes = self._benchmark_profile_list(
                        options["iterations"],
                        options["destructive_cleanup"],
                    )
                    # Store PK to clean up later if needed
                elif op == "schema_explorer":
                    endpoint_id = options.get("endpoint_id")
                    timing_ms, notes = self._benchmark_schema_explorer(
                        endpoint_id, options["iterations"]
                    )
                elif op == "connection_test":
                    profile_id = options.get("profile_id")
                    if not profile_id:
                        results[op] = {"status": "SKIP", "reason": "Requires --profile-id"}
                        continue
                    timing_ms, notes = self._benchmark_connection_test(profile_id)
                elif op == "schema_inference":
                    profile_id = options.get("profile_id")
                    endpoint_id = options.get("endpoint_id")
                    if not profile_id or not endpoint_id:
                        results[op] = {"status": "SKIP", "reason": "Requires --profile-id and --endpoint-id"}
                        continue
                    timing_ms, notes = self._benchmark_schema_inference(profile_id, endpoint_id)
                elif op == "data_preview":
                    profile_id = options.get("profile_id")
                    endpoint_id = options.get("endpoint_id")
                    if not profile_id or not endpoint_id:
                        results[op] = {"status": "SKIP", "reason": "Requires --profile-id and --endpoint-id"}
                        continue
                    timing_ms, notes = self._benchmark_data_preview(profile_id, endpoint_id)
                else:
                    continue

                passed = timing_ms <= nfr_ms
                results[op] = {
                    "time_ms": timing_ms,
                    "nfr_ms": nfr_ms,
                    "passed": passed,
                    "notes": notes,
                }
            except Exception as exc:
                results[op] = {"status": "ERROR", "error": str(exc)}

        self._print_results_table(results)
        failed = [op for op, r in results.items() if r.get("passed") is False]
        if failed:
            self.stdout.write(self.style.ERROR(f"\n✗ {len(failed)} NFR(s) MISSED: {', '.join(failed)}"))
            raise SystemExit(1)
        else:
            self.stdout.write(self.style.SUCCESS("\n✓ All benchmarked NFRs PASSED\n"))

    def _benchmark_profile_list(self, iterations: int, cleanup: bool):
        """
        Create 50 ConnectionProfile + AuthConfig pairs, time GET /api/connector/profiles/.
        """
        from tests.factories import ConnectionProfileFactory, AuthConfigFactory
        from api_connector.services.encryption import encryption_service

        self.stdout.write("  Setting up 50 profiles for list benchmark...")

        created_pks = []
        for _ in range(50):
            profile = ConnectionProfileFactory()
            AuthConfigFactory(
                connection_profile=profile,
                encrypted_credentials=encryption_service.encrypt_dict({}),
            )
            created_pks.append(profile.pk)

        client = Client()
        timings = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            response = client.get("/api/connector/profiles/")
            elapsed_ms = (time.perf_counter() - t0) * 1000
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            timings.append(elapsed_ms)

        median_ms = statistics.median(timings)
        notes = f"Median of {iterations} runs; 50 profiles; ILIKE search not tested (leading-wildcard cannot use B-tree index)"

        if cleanup:
            from api_connector.models import ConnectionProfile
            ConnectionProfile.objects.filter(pk__in=created_pks).delete()
            self.stdout.write(f"  Cleaned up {len(created_pks)} benchmark profiles.")

        return int(median_ms), notes

    def _benchmark_schema_explorer(self, endpoint_id: int | None, iterations: int):
        """
        Create 250 SchemaField records (or use existing endpoint), time GET .../schema/fields/.
        """
        from api_connector.models import Endpoint, SchemaField

        if endpoint_id:
            endpoint = Endpoint.objects.get(pk=endpoint_id)
            cleanup_fields = False
        else:
            from tests.factories import ConnectionProfileFactory, EndpointFactory, AuthConfigFactory
            from api_connector.services.encryption import encryption_service
            profile = ConnectionProfileFactory()
            AuthConfigFactory(connection_profile=profile, encrypted_credentials=encryption_service.encrypt_dict({}))
            endpoint = EndpointFactory(connection_profile=profile, path="/benchmark")
            cleanup_fields = True

        self.stdout.write(f"  Creating 250 SchemaFields for endpoint {endpoint.pk}...")
        created_pks = []
        for i in range(250):
            sf = SchemaField.objects.create(
                endpoint=endpoint,
                key_path=f"field_{i:03d}",
                inferred_type="string",
            )
            created_pks.append(sf.pk)

        profile_pk = endpoint.connection_profile_id
        client = Client()
        timings = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            response = client.get(
                f"/api/connector/profiles/{profile_pk}/endpoints/{endpoint.pk}/schema/fields/"
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000
            assert response.status_code == 200
            timings.append(elapsed_ms)

        median_ms = statistics.median(timings)
        notes = f"250 SchemaField rows; median of {iterations} runs; index on (endpoint_id, include) active"

        if cleanup_fields:
            SchemaField.objects.filter(pk__in=created_pks).delete()

        return int(median_ms), notes

    def _benchmark_connection_test(self, profile_id: int):
        """Time POST .../profiles/<pk>/test/ against a real API."""
        client = Client()
        t0 = time.perf_counter()
        response = client.post(
            f"/api/connector/profiles/{profile_id}/test/",
            content_type="application/json",
            data="{}",
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        notes = f"Profile {profile_id}; response HTTP {response.status_code}; includes DNS + network + auth + HTTP request"
        return int(elapsed_ms), notes

    def _benchmark_schema_inference(self, profile_id: int, endpoint_id: int):
        """Time POST .../schema/infer/ against a real API."""
        from api_connector.models import Endpoint
        endpoint = Endpoint.objects.get(pk=endpoint_id)
        client = Client()
        t0 = time.perf_counter()
        response = client.post(
            f"/api/connector/profiles/{profile_id}/endpoints/{endpoint_id}/schema/infer/",
            content_type="application/json",
            data="{}",
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        notes = f"Profile {profile_id}, Endpoint {endpoint_id}; samples up to 300 records (3 pages)"
        return int(elapsed_ms), notes

    def _benchmark_data_preview(self, profile_id: int, endpoint_id: int):
        """Time POST .../preview/ with row_limit=25."""
        client = Client()
        import json
        t0 = time.perf_counter()
        response = client.post(
            f"/api/connector/profiles/{profile_id}/endpoints/{endpoint_id}/preview/",
            content_type="application/json",
            data=json.dumps({"row_limit": 25}),
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        notes = f"Profile {profile_id}, Endpoint {endpoint_id}; row_limit=25; HTTP {response.status_code}"
        return int(elapsed_ms), notes

    def _print_results_table(self, results: dict):
        self.stdout.write(f"\n{'Operation':<22} | {'Time (ms)':>10} | {'NFR (ms)':>10} | {'Status':<8} | Notes")
        self.stdout.write("-" * 90)
        for op, r in results.items():
            if r.get("status") == "SKIP":
                self.stdout.write(f"{op:<22} | {'—':>10} | {self.NFR_TARGETS_MS[op]:>10} | {'SKIP':<8} | {r['reason']}")
            elif r.get("status") == "ERROR":
                self.stdout.write(
                    self.style.ERROR(
                        f"{op:<22} | {'ERROR':>10} | {self.NFR_TARGETS_MS[op]:>10} | {'ERROR':<8} | {r['error'][:40]}"
                    )
                )
            else:
                status_str = "✓ PASS" if r["passed"] else "✗ FAIL"
                style = self.style.SUCCESS if r["passed"] else self.style.ERROR
                self.stdout.write(
                    style(
                        f"{op:<22} | {r['time_ms']:>10} | {r['nfr_ms']:>10} | {status_str:<8} | {r.get('notes', '')[:40]}"
                    )
                )