"""Add DB-level append-only triggers for Evidence and HumanLayerEvent on Postgres.

This migration installs trigger functions that prevent UPDATE and DELETE
on the critical append-only tables. It is a no-op on non-Postgres databases.
"""
from django.db import migrations


def install_triggers(apps, schema_editor):
    conn = schema_editor.connection
    vendor = conn.vendor
    if vendor != 'postgresql':
        # Skip for non-Postgres (e.g., SQLite in dev)
        return
    with conn.cursor() as cur:
        # Function to block updates/deletes by raising an exception
        cur.execute("""
        CREATE OR REPLACE FUNCTION policy_block_updates() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Attempt to modify append-only table %', TG_TABLE_NAME;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """)
        # Create triggers for Evidence
        cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'evidence_block_ud') THEN
                CREATE TRIGGER evidence_block_ud BEFORE UPDATE OR DELETE ON policy_evidence
                FOR EACH ROW EXECUTE FUNCTION policy_block_updates();
            END IF;
        END$$;
        """)
        # Create triggers for HumanLayerEvent
        cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'humanlayerevent_block_ud') THEN
                CREATE TRIGGER humanlayerevent_block_ud BEFORE UPDATE OR DELETE ON policy_humanlayerevent
                FOR EACH ROW EXECUTE FUNCTION policy_block_updates();
            END IF;
        END$$;
        """)


def remove_triggers(apps, schema_editor):
    conn = schema_editor.connection
    vendor = conn.vendor
    if vendor != 'postgresql':
        return
    with conn.cursor() as cur:
        cur.execute("DROP TRIGGER IF EXISTS evidence_block_ud ON policy_evidence;")
        cur.execute("DROP TRIGGER IF EXISTS humanlayerevent_block_ud ON policy_humanlayerevent;")
        cur.execute("DROP FUNCTION IF EXISTS policy_block_updates();")


class Migration(migrations.Migration):

    dependencies = [
        ('policy', '0005_alter_policyhistory_options_and_more'),
    ]

    operations = [
        migrations.RunPython(install_triggers, remove_triggers),
    ]
