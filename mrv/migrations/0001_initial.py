import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Tenant",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
                ("slug", models.SlugField(max_length=100, unique=True)),
                ("grid_emission_factor_kgco2_per_kwh", models.DecimalField(decimal_places=8, default=0, max_digits=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Meter",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("external_id", models.CharField(max_length=255)),
                ("name", models.CharField(max_length=255)),
                ("meter_type", models.CharField(choices=[("consumption", "Consumption"), ("generation", "Generation"), ("bidirectional", "Bidirectional")], max_length=20)),
                ("active", models.BooleanField(default=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="meters", to="mrv.tenant")),
            ],
        ),
        migrations.CreateModel(
            name="EnergyReading",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("timestamp", models.DateTimeField()),
                ("energy_consumed_kwh", models.DecimalField(decimal_places=6, default=0, max_digits=18)),
                ("energy_generated_kwh", models.DecimalField(decimal_places=6, default=0, max_digits=18)),
                ("quality", models.CharField(default="measured", max_length=32)),
                ("ingested_at", models.DateTimeField(auto_now_add=True)),
                ("meter", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="energy_readings", to="mrv.meter")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="energy_readings", to="mrv.tenant")),
            ],
        ),
        migrations.AddConstraint(
            model_name="meter",
            constraint=models.UniqueConstraint(fields=("tenant", "external_id"), name="unique_meter_external_id_per_tenant"),
        ),
        migrations.AddConstraint(
            model_name="energyreading",
            constraint=models.UniqueConstraint(fields=("tenant", "meter", "timestamp"), name="unique_reading_per_meter_interval"),
        ),
        migrations.AddConstraint(
            model_name="energyreading",
            constraint=models.CheckConstraint(condition=models.Q(("energy_consumed_kwh__gte", 0), ("energy_generated_kwh__gte", 0)), name="reading_energy_values_non_negative"),
        ),
        migrations.AddIndex(model_name="energyreading", index=models.Index(fields=["tenant", "timestamp"], name="mrv_energy_tenant_i_8f1e8f_idx")),
        migrations.AddIndex(model_name="energyreading", index=models.Index(fields=["meter", "timestamp"], name="mrv_energy_meter_i_3f4f7d_idx")),
        migrations.RunSQL(
            # Timescale requires every unique index on a hypertable to include its time column.
            sql="ALTER TABLE mrv_energyreading DROP CONSTRAINT mrv_energyreading_pkey; SELECT create_hypertable('mrv_energyreading', 'timestamp', if_not_exists => TRUE, migrate_data => TRUE);",
            reverse_sql="SELECT 1;",
        ),
    ]
