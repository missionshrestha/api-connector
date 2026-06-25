# backend/api_connector/management/commands/rotate_encryption_key.py
"""
Management command for rotating the Fernet ENCRYPTION_KEY.

⚠️  CRITICAL: Wraps ALL re-encryption in a single transaction.atomic().
    If the process is interrupted halfway, the transaction is rolled back.
    The old key still works after a rollback — no data corruption.

Usage:
    python manage.py rotate_encryption_key \\
        --old-key=<current ENCRYPTION_KEY value> \\
        --new-key=<a fresh Fernet key — see the generation snippet in docs/operations.md>

NEVER run this without a database backup.
NEVER run this on a production database without following docs/operations.md.

ADR-005: this command performs no direct Fernet work. All encryption operations
go through EncryptionService (api_connector/services/encryption.py).
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = (
        "Rotate the Fernet ENCRYPTION_KEY by re-encrypting all stored credentials "
        "and OAuth tokens. Wraps ALL operations in a single transaction. "
        "NEVER run without a database backup. See docs/operations.md."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--old-key",
            required=True,
            help="The current ENCRYPTION_KEY value (Fernet key string)",
        )
        parser.add_argument(
            "--new-key",
            required=True,
            help="The new ENCRYPTION_KEY value (Fernet key string)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Verify decryption succeeds without writing any changes",
        )

    def handle(self, *args, **options):
        old_key = options["old_key"]
        new_key = options["new_key"]
        dry_run = options["dry_run"]

        from api_connector.services.encryption import encryption_service

        # Validate both keys before touching any data
        try:
            encryption_service.validate_key(old_key)
            encryption_service.validate_key(new_key)
        except Exception as exc:
            raise CommandError(f"Invalid key format: {exc}") from exc

        if old_key == new_key:
            raise CommandError(
                "Old key and new key are identical — no rotation needed."
            )

        self.stdout.write(
            self.style.WARNING(
                "\n⚠️  ENCRYPTION KEY ROTATION\n"
                "  This operation re-encrypts ALL stored credentials and OAuth tokens.\n"
                "  Ensure you have a database backup before proceeding.\n"
                "  The operation is wrapped in a single transaction — any failure rolls back.\n"
            )
        )

        if dry_run:
            self.stdout.write(
                self.style.NOTICE("  DRY RUN mode — no data will be written.\n")
            )

        from api_connector.models import AuthConfig, OAuthToken

        auth_config_count = AuthConfig.objects.count()
        oauth_token_count = OAuthToken.objects.count()

        self.stdout.write(
            f"  Records to rotate:\n"
            f"    AuthConfig (encrypted_credentials): {auth_config_count}\n"
            f"    OAuthToken (encrypted_token + optional refresh): {oauth_token_count}\n"
        )

        if dry_run:
            self._dry_run_verify(old_key, auth_config_count, oauth_token_count)
            return

        confirm = input("\n  Type 'ROTATE' to confirm: ").strip()
        if confirm != "ROTATE":
            self.stdout.write(
                self.style.ERROR("Aborted — you must type exactly 'ROTATE' to proceed.")
            )
            return

        self._execute_rotation(old_key, new_key)

    def _dry_run_verify(self, old_key, auth_count, token_count):
        from api_connector.models import AuthConfig, OAuthToken
        from api_connector.services.encryption import encryption_service

        errors = 0

        self.stdout.write(
            f"\n  Verifying {auth_count} AuthConfig records with old key..."
        )
        for ac in AuthConfig.objects.all():
            blob = ac.encrypted_credentials.get("blob", "")
            if blob and not encryption_service.is_decryptable(blob, old_key):
                self.stdout.write(
                    self.style.ERROR(f"    ✗ AuthConfig pk={ac.pk}: decryption failed")
                )
                errors += 1

        self.stdout.write(
            f"  Verifying {token_count} OAuthToken records with old key..."
        )
        for ot in OAuthToken.objects.all():
            ok = encryption_service.is_decryptable(ot.encrypted_token, old_key)
            if ot.encrypted_refresh_token:
                ok = ok and encryption_service.is_decryptable(
                    ot.encrypted_refresh_token, old_key
                )
            if not ok:
                self.stdout.write(
                    self.style.ERROR(f"    ✗ OAuthToken pk={ot.pk}: decryption failed")
                )
                errors += 1

        if errors == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n  ✓ Dry run PASSED — {auth_count + token_count} records verified, 0 errors"
                )
            )
            self.stdout.write("  Ready to rotate — re-run without --dry-run to apply.")
        else:
            self.stdout.write(
                self.style.ERROR(
                    f"\n  ✗ Dry run FAILED — {errors} records could not be decrypted with the old key."
                )
            )
            self.stdout.write("  Do NOT rotate — investigate the failures first.")

    def _execute_rotation(self, old_key, new_key):
        from api_connector.models import AuthConfig, OAuthToken
        from api_connector.services.encryption import InvalidToken, encryption_service

        self.stdout.write("\n  Starting rotation (inside single transaction)...")
        rotated_ac = 0
        rotated_ot = 0
        errors = []

        try:
            with transaction.atomic():
                # ── Rotate AuthConfig.encrypted_credentials ────────────────────
                self.stdout.write("  Rotating AuthConfig records...")
                for ac in AuthConfig.objects.select_for_update().all():
                    blob = ac.encrypted_credentials.get("blob", "")
                    if not blob:
                        continue
                    try:
                        new_blob = encryption_service.reencrypt(blob, old_key, new_key)
                        ac.encrypted_credentials = {"blob": new_blob}
                        ac.save(update_fields=["encrypted_credentials", "updated_at"])
                        rotated_ac += 1
                    except InvalidToken as exc:
                        errors.append(f"AuthConfig pk={ac.pk}: {exc}")

                if errors:
                    raise Exception(
                        f"Rotation aborted: {len(errors)} AuthConfig record(s) could not be decrypted. "
                        f"Transaction rolled back. Old key still valid. First error: {errors[0]}"
                    )

                # ── Rotate OAuthToken records ──────────────────────────────────
                self.stdout.write("  Rotating OAuthToken records...")
                for ot in OAuthToken.objects.select_for_update().all():
                    try:
                        new_token = encryption_service.reencrypt(
                            ot.encrypted_token, old_key, new_key
                        )
                        new_refresh = None
                        if ot.encrypted_refresh_token:
                            new_refresh = encryption_service.reencrypt(
                                ot.encrypted_refresh_token, old_key, new_key
                            )
                        ot.encrypted_token = new_token
                        ot.encrypted_refresh_token = new_refresh
                        ot.save(
                            update_fields=[
                                "encrypted_token",
                                "encrypted_refresh_token",
                                "updated_at",
                            ]
                        )
                        rotated_ot += 1
                    except InvalidToken as exc:
                        errors.append(f"OAuthToken pk={ot.pk}: {exc}")

                if errors:
                    raise Exception(
                        f"Rotation aborted: {len(errors)} OAuthToken record(s) failed. "
                        f"Transaction rolled back. Old key still valid. First error: {errors[0]}"
                    )

        except Exception as exc:
            self.stdout.write(
                self.style.ERROR(
                    f"\n  ✗ ROTATION FAILED — TRANSACTION ROLLED BACK\n  {exc}"
                )
            )
            self.stdout.write(
                self.style.WARNING("  Old key is still active. No data was changed.")
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"\n  ✓ ROTATION COMPLETE\n"
                f"    AuthConfig records rotated: {rotated_ac}\n"
                f"    OAuthToken records rotated: {rotated_ot}\n"
                f"\n  Next steps:\n"
                f"    1. Update ENCRYPTION_KEY in all deployment environments\n"
                f"    2. Restart all Django worker processes (Fernet instance is cached)\n"
                f"    3. Verify decryption works: python manage.py shell\n"
                f"       >>> from api_connector.services.encryption import encryption_service\n"
                f"       >>> from api_connector.models import AuthConfig\n"
                f"       >>> print(encryption_service.decrypt_to_dict(AuthConfig.objects.first().encrypted_credentials))\n"
            )
        )
