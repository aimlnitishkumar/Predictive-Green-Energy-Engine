import uuid

from django.conf import settings
from django.db import models


class Tenant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="tenants")
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=100, unique=True)
    grid_emission_factor_kgco2_per_kwh = models.DecimalField(
        max_digits=12,
        decimal_places=8,
        default=0,
        help_text="Location-based grid factor used for Scope 2 calculations.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]


class CarbonReport(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        RUNNING = "RUNNING", "Running"
        SUCCESS = "SUCCESS", "Success"
        FAILURE = "FAILURE", "Failure"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="reports")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="carbon_reports"
    )
    start = models.DateTimeField()
    end = models.DateTimeField()
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    result = models.JSONField(null=True, blank=True)
    error_message = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Meter(models.Model):
    class MeterType(models.TextChoices):
        CONSUMPTION = "consumption", "Consumption"
        GENERATION = "generation", "Generation"
        BIDIRECTIONAL = "bidirectional", "Bidirectional"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="meters")
    external_id = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    meter_type = models.CharField(max_length=20, choices=MeterType.choices)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "external_id"], name="unique_meter_external_id_per_tenant"
            )
        ]


class EnergyReading(models.Model):
    """15-minute energy interval. The migration converts this table to a hypertable."""

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="energy_readings")
    meter = models.ForeignKey(Meter, on_delete=models.CASCADE, related_name="energy_readings")
    timestamp = models.DateTimeField()
    energy_consumed_kwh = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    energy_generated_kwh = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    quality = models.CharField(max_length=32, default="measured")
    ingested_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "meter", "timestamp"], name="unique_reading_per_meter_interval"
            ),
            models.CheckConstraint(
                condition=models.Q(energy_consumed_kwh__gte=0)
                & models.Q(energy_generated_kwh__gte=0),
                name="reading_energy_values_non_negative",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "timestamp"]),
            models.Index(fields=["meter", "timestamp"]),
        ]
