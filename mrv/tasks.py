from datetime import datetime
from uuid import UUID

from celery import shared_task
from django.db.models import QuerySet

from .models import EnergyReading, Tenant
from .services import CarbonCalculationService


@shared_task
def generate_carbon_report(tenant_id: str | UUID, start: datetime, end: datetime) -> dict:
    """Aggregate 15-minute readings into UTC daily summaries for a reporting range."""
    tenant = Tenant.objects.get(pk=tenant_id)
    readings: QuerySet = EnergyReading.objects.filter(
        tenant_id=tenant.id,
        timestamp__gte=start,
        timestamp__lt=end,
    ).order_by("timestamp")
    service = CarbonCalculationService(tenant.grid_emission_factor_kgco2_per_kwh)
    readings = list(readings.iterator(chunk_size=5000))
    daily = service.calculate_by_day(readings)
    monthly = service.calculate_by_month(readings)

    def serialize(summary):
        return {
            "consumed_kwh": str(summary.consumed_kwh),
            "generated_kwh": str(summary.generated_kwh),
            "matched_green_kwh": str(summary.matched_green_kwh),
            "net_grid_kwh": str(summary.net_grid_kwh),
            "emissions_kgco2": str(summary.emissions_kgco2),
        }

    return {
        "tenant_id": str(tenant.id),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "daily": {day.isoformat(): serialize(summary) for day, summary in daily.items()},
        "monthly": {month: serialize(summary) for month, summary in monthly.items()},
    }
