from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("mrv", "0002_rename_mrv_energy_tenant_i_8f1e8f_idx_mrv_energyr_tenant__e60e70_idx_and_more"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "CREATE EXTENSION IF NOT EXISTS timescaledb; "
                "ALTER TABLE mrv_energyreading "
                "ADD CONSTRAINT mrv_energyreading_pkey PRIMARY KEY (id, timestamp);"
            ),
            reverse_sql="ALTER TABLE mrv_energyreading DROP CONSTRAINT mrv_energyreading_pkey;",
        ),
    ]
