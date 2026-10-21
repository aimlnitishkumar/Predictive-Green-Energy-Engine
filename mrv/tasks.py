from datetime import datetime
from uuid import UUID

from celery import shared_task
from celery.signals import task_failure
from django.db.models import QuerySet

from .models import CarbonReport, EnergyReading, Tenant
from .services import CarbonCalculationService


@shared_task
def generate_carbon_report(
    tenant_id: str | UUID,
    start: datetime,
    end: datetime,
    report_id: str | UUID | None = None,
) -> dict:
    """Aggregate 15-minute readings into UTC daily summaries for a reporting range."""
    if report_id is not None:
        CarbonReport.objects.filter(pk=report_id).update(status=CarbonReport.Status.RUNNING)
    tenant = Tenant.objects.get(pk=tenant_id)
    readings: QuerySet = EnergyReading.objects.filter(
        tenant_id=tenant.id,
        timestamp__gte=start,
        timestamp__lt=end,
    ).order_by("timestamp")
    service = CarbonCalculationService(tenant.grid_emission_factor_kgco2_per_kwh)
    daily = service.calculate_by_day(readings.iterator(chunk_size=5000))
    monthly = service.calculate_by_month(readings.iterator(chunk_size=5000))

    def serialize(summary):
        return {
            "consumed_kwh": str(summary.consumed_kwh),
            "generated_kwh": str(summary.generated_kwh),
            "matched_green_kwh": str(summary.matched_green_kwh),
            "net_grid_kwh": str(summary.net_grid_kwh),
            "emissions_kgco2": str(summary.emissions_kgco2),
        }

    result = {
        "tenant_id": str(tenant.id),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "daily": {day.isoformat(): serialize(summary) for day, summary in daily.items()},
        "monthly": {month: serialize(summary) for month, summary in monthly.items()},
    }
    if report_id is not None:
        CarbonReport.objects.filter(pk=report_id).update(
            status=CarbonReport.Status.SUCCESS,
            result=result,
            error_message="",
        )
    return result


@task_failure.connect(weak=False)
def mark_carbon_report_failed(sender=None, task_id: str | None = None, **kwargs) -> None:
    if getattr(sender, "name", None) == generate_carbon_report.name and task_id:
        CarbonReport.objects.filter(pk=task_id).update(
            status=CarbonReport.Status.FAILURE,
            error_message="Report generation failed.",
        )
