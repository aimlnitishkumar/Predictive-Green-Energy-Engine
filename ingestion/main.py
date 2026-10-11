import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

from django.db import transaction
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from mrv.models import EnergyReading, Meter, Tenant
from mrv.services import CarbonCalculationService

app = FastAPI(title="MRV IoT Ingestion API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ReadingPayload(BaseModel):
    timestamp: datetime
    energy_consumed_kwh: Decimal = Field(ge=0)
    energy_generated_kwh: Decimal = Field(ge=0)
    quality: str = Field(default="measured", max_length=32)


class IngestionPayload(BaseModel):
    tenant_id: UUID
    meter_external_id: str = Field(min_length=1, max_length=255)
    readings: list[ReadingPayload] = Field(min_length=1, max_length=10_000)


class IngestionResponse(BaseModel):
    accepted: int
    tenant_id: UUID
    meter_external_id: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/dashboard/overview")
def dashboard_overview(tenant_id: UUID | None = Query(default=None)) -> dict:
    """Return the latest 24 hours of tenant-scoped metrics for the command center."""
    tenant = Tenant.objects.filter(pk=tenant_id).first() if tenant_id else Tenant.objects.first()
    if tenant is None:
        raise HTTPException(status_code=404, detail="No tenant data available")

    start = datetime.now(timezone.utc) - timedelta(hours=24)
    readings = list(
        EnergyReading.objects.filter(tenant_id=tenant.id, timestamp__gte=start)
        .order_by("timestamp")
    )
    if not readings:
        raise HTTPException(status_code=404, detail="No readings available for tenant")

    service = CarbonCalculationService(tenant.grid_emission_factor_kgco2_per_kwh)
    summary = service.calculate(readings)
    points = []
    for reading in readings:
        match = service.match_interval(
            reading.timestamp,
            Decimal(reading.energy_consumed_kwh),
            Decimal(reading.energy_generated_kwh),
        )
        points.append(
            {
                "time": reading.timestamp.astimezone(timezone.utc).strftime("%H:%M"),
                "consumed": float(match.consumed_kwh),
                "renewable": float(match.generated_kwh),
                "emissions": float(match.emissions_kgco2),
            }
        )
    return {
        "tenant": tenant.name,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "totals": {
            "consumed_kwh": float(summary.consumed_kwh),
            "renewable_kwh": float(summary.generated_kwh),
            "matched_kwh": float(summary.matched_green_kwh),
            "emissions_kgco2": float(summary.emissions_kgco2),
        },
        "points": points,
    }


@app.post("/v1/energy/readings", response_model=IngestionResponse, status_code=status.HTTP_202_ACCEPTED)
def ingest_readings(payload: IngestionPayload) -> IngestionResponse:
    """Bulk upsert one meter's 15-minute readings in a single database transaction."""
    meter = Meter.objects.filter(
        tenant_id=payload.tenant_id,
        external_id=payload.meter_external_id,
        active=True,
    ).first()
    if meter is None:
        raise HTTPException(status_code=404, detail="Active meter not found for tenant")

    readings = [
        EnergyReading(
            tenant_id=payload.tenant_id,
            meter_id=meter.id,
            timestamp=reading.timestamp,
            energy_consumed_kwh=reading.energy_consumed_kwh,
            energy_generated_kwh=reading.energy_generated_kwh,
            quality=reading.quality,
        )
        for reading in payload.readings
    ]
    try:
        with transaction.atomic():
            EnergyReading.objects.bulk_create(
                readings,
                update_conflicts=True,
                update_fields=["energy_consumed_kwh", "energy_generated_kwh", "quality"],
                unique_fields=["tenant", "meter", "timestamp"],
                batch_size=1_000,
            )
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Could not persist readings") from exc

    return IngestionResponse(
        accepted=len(readings),
        tenant_id=payload.tenant_id,
        meter_external_id=payload.meter_external_id,
    )
