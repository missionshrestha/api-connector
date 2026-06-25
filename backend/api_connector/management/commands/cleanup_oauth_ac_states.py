# backend/api_connector/management/commands/cleanup_oauth_ac_states.py
"""
Management command to delete expired/used OAuthACState records.

Schedule weekly via cron:
  0 3 * * 0 /path/to/venv/bin/python /path/to/manage.py cleanup_oauth_ac_states

Records deleted:
  - used=True AND created_at < (now - 24 hours)  [completed flows, safely old]
  - expires_at < (now - 24 hours)                [expired before use]

Records preserved:
  - used=False AND expires_at > now              [active authorization flows]
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Delete expired and used OAuthACState records. Safe to run at any time."

    def add_arguments(self, parser):
        parser.add_argument(
            "--retention-hours",
            type=int,
            default=24,
            help="Hours after creation/expiry before a used/expired record is deleted (default: 24)",
        )

    def handle(self, *args, **options):
        from api_connector.models import OAuthACState

        retention = timedelta(hours=options["retention_hours"])
        cutoff = timezone.now() - retention

        # Condition A: used records older than retention window
        deleted_used = OAuthACState.objects.filter(
            used=True, created_at__lt=cutoff
        ).delete()[0]

        # Condition B: expired records (regardless of used flag) older than retention window
        deleted_expired = OAuthACState.objects.filter(
            expires_at__lt=cutoff
        ).delete()[0]

        total_deleted = deleted_used + deleted_expired

        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {total_deleted} expired OAuthACState record(s) "
                f"(used+old: {deleted_used}, expired: {deleted_expired})."
            )
        )

        # Report remaining count for monitoring
        active_count = OAuthACState.objects.filter(
            used=False, expires_at__gt=timezone.now()
        ).count()
        self.stdout.write(f"Active (in-progress) OAuthACState records remaining: {active_count}")