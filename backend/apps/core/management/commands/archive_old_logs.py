"""
Management command: archive_old_logs

Moves old audit/event log records to archive tables to keep operational
tables lean and fast. Safe to run on a schedule (e.g., nightly via cron).

Usage:
    python manage.py archive_old_logs               # archives records > 90 days old
    python manage.py archive_old_logs --days 180    # archives records > 180 days old
    python manage.py archive_old_logs --dry-run     # shows counts without moving
"""

from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.utils import timezone
from datetime import timedelta


ARCHIVE_QUERIES = [
    {
        "name": "SearchAuditLog",
        "source": "core_searchauditlog",
        "archive": "core_searchauditlog_archive",
        "columns": "actor_username, query_type, query_value, result_count, created_at",
        "id_col": "id",
    },
    {
        "name": "AppointmentEvent",
        "source": "core_appointmentevent",
        "archive": "core_appointmentevent_archive",
        "columns": "appointment_id, action, previous_status, new_status, reason, actor_username, created_at",
        "id_col": "id",
    },
    {
        "name": "QueueEvent",
        "source": "core_queueevent",
        "archive": "core_queueevent_archive",
        "columns": "queue_item_id, action, previous_status, new_status, actor_username, payload, created_at",
        "id_col": "id",
    },
    {
        "name": "BillingAuditEvent",
        "source": "core_billingauditevent",
        "archive": "core_billingauditevent_archive",
        "columns": "ledger_id, action, actor_username, payload, created_at",
        "id_col": "id",
    },
]


class Command(BaseCommand):
    help = "Archive old audit and event log records to keep operational tables lean."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=90,
            help="Archive records older than this many days (default: 90)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Show what would be archived without actually moving records",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=1000,
            help="Number of records to move per batch (default: 1000)",
        )

    def handle(self, *args, **options):
        days = options["days"]
        dry_run = options["dry_run"]
        batch_size = options["batch_size"]

        cutoff = timezone.now() - timedelta(days=days)
        self.stdout.write(
            f"{'[DRY RUN] ' if dry_run else ''}"
            f"Archiving records older than {days} days (before {cutoff.date()})"
        )

        total_archived = 0

        for cfg in ARCHIVE_QUERIES:
            with connection.cursor() as cursor:
                # Count eligible records
                cursor.execute(
                    f"SELECT COUNT(*) FROM {cfg['source']} WHERE created_at < %s",
                    [cutoff],
                )
                count = cursor.fetchone()[0]

                if count == 0:
                    self.stdout.write(f"  {cfg['name']}: 0 records to archive")
                    continue

                self.stdout.write(f"  {cfg['name']}: {count} records to archive")

                if dry_run:
                    continue

                # Move in batches to avoid long locks
                archived = 0
                while True:
                    with transaction.atomic():
                        cursor.execute(
                            f"""
                            WITH moved AS (
                                DELETE FROM {cfg['source']}
                                WHERE {cfg['id_col']} IN (
                                    SELECT {cfg['id_col']} FROM {cfg['source']}
                                    WHERE created_at < %s
                                    ORDER BY created_at
                                    LIMIT %s
                                )
                                RETURNING {cfg['columns']}
                            )
                            INSERT INTO {cfg['archive']} ({cfg['columns']})
                            SELECT {cfg['columns']} FROM moved
                            """,
                            [cutoff, batch_size],
                        )
                        moved = cursor.rowcount
                        archived += moved
                        if moved < batch_size:
                            break

                self.stdout.write(
                    self.style.SUCCESS(f"  {cfg['name']}: archived {archived} records")
                )
                total_archived += archived

        self.stdout.write(
            self.style.SUCCESS(
                f"\n{'[DRY RUN] Would archive' if dry_run else 'Total archived'}: {total_archived} records"
            )
        )
