# Phase 3: Archive tables for high-volume event/audit logs
# Creates dedicated archive tables so operational tables stay lean.
# A management command (archive_old_logs) moves records older than N days.

from django.db import migrations


CREATE_ARCHIVE_TABLES = """
CREATE TABLE IF NOT EXISTS core_searchauditlog_archive (
    id          BIGSERIAL PRIMARY KEY,
    actor_username VARCHAR(150) NOT NULL,
    query_type  VARCHAR(50)  NOT NULL,
    query_value VARCHAR(255) NOT NULL,
    result_count INTEGER      NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ  NOT NULL,
    archived_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_searchauditlog_arch_created
    ON core_searchauditlog_archive (created_at);

CREATE TABLE IF NOT EXISTS core_appointmentevent_archive (
    id               BIGSERIAL PRIMARY KEY,
    appointment_id   BIGINT NOT NULL,
    action           VARCHAR(20) NOT NULL,
    previous_status  VARCHAR(20) NOT NULL DEFAULT '',
    new_status       VARCHAR(20) NOT NULL,
    reason           VARCHAR(255) NOT NULL DEFAULT '',
    actor_username   VARCHAR(150) NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL,
    archived_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_appointmentevent_arch_appt
    ON core_appointmentevent_archive (appointment_id);
CREATE INDEX IF NOT EXISTS idx_appointmentevent_arch_created
    ON core_appointmentevent_archive (created_at);

CREATE TABLE IF NOT EXISTS core_queueevent_archive (
    id               BIGSERIAL PRIMARY KEY,
    queue_item_id    BIGINT NOT NULL,
    action           VARCHAR(20) NOT NULL,
    previous_status  VARCHAR(20) NOT NULL,
    new_status       VARCHAR(20) NOT NULL,
    actor_username   VARCHAR(150) NOT NULL,
    payload          JSONB NOT NULL DEFAULT '{}',
    created_at       TIMESTAMPTZ NOT NULL,
    archived_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_queueevent_arch_created
    ON core_queueevent_archive (created_at);

CREATE TABLE IF NOT EXISTS core_billingauditevent_archive (
    id               BIGSERIAL PRIMARY KEY,
    ledger_id        BIGINT NOT NULL,
    action           VARCHAR(50) NOT NULL,
    actor_username   VARCHAR(150) NOT NULL,
    payload          JSONB NOT NULL DEFAULT '{}',
    created_at       TIMESTAMPTZ NOT NULL,
    archived_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_billingaudit_arch_ledger
    ON core_billingauditevent_archive (ledger_id);
CREATE INDEX IF NOT EXISTS idx_billingaudit_arch_created
    ON core_billingauditevent_archive (created_at);
"""

DROP_ARCHIVE_TABLES = """
DROP TABLE IF EXISTS core_searchauditlog_archive;
DROP TABLE IF EXISTS core_appointmentevent_archive;
DROP TABLE IF EXISTS core_queueevent_archive;
DROP TABLE IF EXISTS core_billingauditevent_archive;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0044_phase2_denormalization_backfill"),
    ]

    operations = [
        migrations.RunSQL(
            sql=CREATE_ARCHIVE_TABLES,
            reverse_sql=DROP_ARCHIVE_TABLES,
        ),
    ]
