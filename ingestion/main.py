import os
from hashlib import sha256
from datetime import datetime, timedelta, timezone
from uuid import UUID

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.utils.text import slugify
from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from kombu.exceptions import OperationalError

from ingestion.auth import create_access_token, get_current_user, get_tenant_for_user
from ingestion.schemas import (
    CarbonReportRequest,
    IngestionPayload,
    IngestionResponse,
    LoginPayload,
    MeterCreate,
    MeterUpdate,
    RegisterPayload,
    TenantCreate,
    TenantUpdate,
)
from mrv.models import CarbonReport, EnergyReading, Meter, Tenant
from mrv.services import CarbonCalculationService
from mrv.tasks import generate_carbon_report

app = FastAPI(
    title="Predictive Green Energy Engine API",
    description="Tenant-scoped MRV, energy ingestion, reporting, and baseline forecasting APIs.",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS", "http://localhost:3000,http://localhost:5173"
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


def tenant_response(tenant: Tenant) -> dict:
    return {
        "id": str(tenant.id),
        "name": tenant.name,
        "slug": tenant.slug,
        "grid_emission_factor_kgco2_per_kwh": str(
            tenant.grid_emission_factor_kgco2_per_kwh
        ),
        "created_at": tenant.created_at.isoformat(),
    }


def meter_response(meter: Meter) -> dict:
    return {
        "id": str(meter.id),
        "tenant_id": str(meter.tenant_id),
        "external_id": meter.external_id,
        "name": meter.name,
        "meter_type": meter.meter_type,
        "active": meter.active,
    }


def reading_response(reading: EnergyReading) -> dict:
    return {
        "id": reading.pk,
        "tenant_id": str(reading.tenant_id),
        "meter_id": str(reading.meter_id),
        "timestamp": reading.timestamp.isoformat(),
        "energy_consumed_kwh": str(reading.energy_consumed_kwh),
        "energy_generated_kwh": str(reading.energy_generated_kwh),
        "quality": reading.quality,
        "ingested_at": reading.ingested_at.isoformat(),
    }


def ensure_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise HTTPException(status_code=422, detail=f"{name} must include a timezone")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/auth/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterPayload) -> dict:
    try:
        validate_email(payload.email)
    except DjangoValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.messages) from exc

    user_model = get_user_model()
    email = payload.email.strip().lower()
    if user_model.objects.filter(email__iexact=email).exists():
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    username = email if len(email) <= 150 else f"{email[:80]}-{sha256(email.encode()).hexdigest()}"
    user = user_model(username=username, email=email)
    try:
        validate_password(payload.password, user)
    except DjangoValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.messages) from exc

    tenant_name = payload.tenant_name.strip()
    if not tenant_name:
        raise HTTPException(status_code=422, detail="Tenant name cannot be blank")
    requested_slug = slugify(payload.tenant_slug or tenant_name)[:100].strip("-")
    if not requested_slug:
        raise HTTPException(status_code=422, detail="Tenant name must produce a valid slug")
    tenant_slug = requested_slug
    if payload.tenant_slug and Tenant.objects.filter(slug=tenant_slug).exists():
        raise HTTPException(status_code=409, detail="Tenant slug is already in use")
    if not payload.tenant_slug:
        suffix = 2
        while Tenant.objects.filter(slug=tenant_slug).exists():
            tenant_slug = f"{requested_slug[:95]}-{suffix}"
            suffix += 1

    try:
        with transaction.atomic():
            user.set_password(payload.password)
            user.save()
            tenant = Tenant.objects.create(
                name=tenant_name,
                slug=tenant_slug,
                grid_emission_factor_kgco2_per_kwh=payload.grid_emission_factor_kgco2_per_kwh,
            )
            tenant.members.add(user)
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409, detail="Email or tenant slug is already in use"
        ) from exc

    return {
        "access_token": create_access_token(user.pk),
        "token_type": "bearer",
        "expires_in": 3600,
        "user": {"id": user.pk, "email": user.email},
        "tenant": tenant_response(tenant),
    }


@app.post("/v1/auth/login")
def login(payload: LoginPayload) -> dict:
    email = payload.email.strip().lower()
    user_model = get_user_model()
    user_record = user_model.objects.filter(email__iexact=email, is_active=True).first()
    user = (
        authenticate(username=user_record.username, password=payload.password)
        if user_record
        else None
    )
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {
        "access_token": create_access_token(user.pk),
        "token_type": "bearer",
        "expires_in": 3600,
        "user": {"id": user.pk, "email": user.email},
    }


@app.get("/v1/auth/me")
def current_user_profile(user=Depends(get_current_user)) -> dict:
    return {
        "id": user.pk,
        "email": user.email,
        "tenants": [
            tenant_response(tenant) for tenant in Tenant.objects.filter(members=user)
        ],
    }


@app.get("/v1/tenants")
def list_tenants(user=Depends(get_current_user)) -> list[dict]:
    return [
        tenant_response(tenant)
        for tenant in Tenant.objects.filter(members=user).order_by("name")
    ]


@app.post("/v1/tenants", status_code=status.HTTP_201_CREATED)
def create_tenant(payload: TenantCreate, user=Depends(get_current_user)) -> dict:
    tenant_name = payload.name.strip()
    tenant_slug = slugify(payload.slug)[:100].strip("-")
    if not tenant_name or not tenant_slug:
        raise HTTPException(status_code=422, detail="Tenant name and slug cannot be blank")
    try:
        with transaction.atomic():
            tenant = Tenant.objects.create(
                name=tenant_name,
                slug=tenant_slug,
                grid_emission_factor_kgco2_per_kwh=payload.grid_emission_factor_kgco2_per_kwh,
            )
            tenant.members.add(user)
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Tenant slug is already in use") from exc
    return tenant_response(tenant)


@app.get("/v1/tenants/{tenant_id}")
def retrieve_tenant(tenant_id: UUID, user=Depends(get_current_user)) -> dict:
    return tenant_response(get_tenant_for_user(user, tenant_id))


@app.patch("/v1/tenants/{tenant_id}")
def update_tenant(
    tenant_id: UUID,
    payload: TenantUpdate,
    user=Depends(get_current_user),
) -> dict:
    tenant = get_tenant_for_user(user, tenant_id)
    updates = payload.model_dump(exclude_unset=True)
    if not updates or any(value is None for value in updates.values()):
        raise HTTPException(status_code=422, detail="At least one non-null field is required")
    if "slug" in updates and updates["slug"] is not None:
        updates["slug"] = slugify(updates["slug"])[:100].strip("-")
        if not updates["slug"]:
            raise HTTPException(status_code=422, detail="A valid tenant slug is required")
    if "name" in updates and not updates["name"].strip():
        raise HTTPException(status_code=422, detail="Tenant name cannot be blank")
    for field, value in updates.items():
        setattr(tenant, field, value.strip() if field == "name" and value is not None else value)
    try:
        tenant.save(update_fields=list(updates))
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Tenant slug is already in use") from exc
    return tenant_response(tenant)


@app.get("/v1/tenants/{tenant_id}/meters")
def list_meters(tenant_id: UUID, user=Depends(get_current_user)) -> list[dict]:
    tenant = get_tenant_for_user(user, tenant_id)
    return [
        meter_response(meter)
        for meter in Meter.objects.filter(tenant=tenant).order_by("name", "external_id")
    ]


@app.post("/v1/tenants/{tenant_id}/meters", status_code=status.HTTP_201_CREATED)
def create_meter(
    tenant_id: UUID,
    payload: MeterCreate,
    user=Depends(get_current_user),
) -> dict:
    tenant = get_tenant_for_user(user, tenant_id)
    external_id = payload.external_id.strip()
    name = payload.name.strip()
    if not external_id or not name:
        raise HTTPException(status_code=422, detail="Meter ID and name cannot be blank")
    try:
        meter = Meter.objects.create(
            tenant=tenant,
            external_id=external_id,
            name=name,
            meter_type=payload.meter_type,
        )
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409, detail="Meter external ID already exists for this tenant"
        ) from exc
    return meter_response(meter)


@app.patch("/v1/tenants/{tenant_id}/meters/{meter_id}")
def update_meter(
    tenant_id: UUID,
    meter_id: UUID,
    payload: MeterUpdate,
    user=Depends(get_current_user),
) -> dict:
    tenant = get_tenant_for_user(user, tenant_id)
    meter = Meter.objects.filter(pk=meter_id, tenant=tenant).first()
    if meter is None:
        raise HTTPException(status_code=404, detail="Meter not found")
    updates = payload.model_dump(exclude_unset=True)
    if not updates or any(value is None for value in updates.values()):
        raise HTTPException(status_code=422, detail="At least one non-null field is required")
    for field, value in updates.items():
        if field == "name":
            value = value.strip()
            if not value:
                raise HTTPException(status_code=422, detail="Meter name cannot be blank")
        setattr(meter, field, value)
    meter.save(update_fields=list(updates))
    return meter_response(meter)


@app.delete(
    "/v1/tenants/{tenant_id}/meters/{meter_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def deactivate_meter(
    tenant_id: UUID,
    meter_id: UUID,
    user=Depends(get_current_user),
) -> Response:
    tenant = get_tenant_for_user(user, tenant_id)
    updated = Meter.objects.filter(pk=meter_id, tenant=tenant).update(active=False)
    if not updated:
        raise HTTPException(status_code=404, detail="Meter not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/v1/energy/readings")
def list_readings(
    tenant_id: UUID,
    meter_external_id: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    user=Depends(get_current_user),
) -> dict:
    tenant = get_tenant_for_user(user, tenant_id)
    if start is not None:
        ensure_aware(start, "start")
    if end is not None:
        ensure_aware(end, "end")
    if start is not None and end is not None and end <= start:
        raise HTTPException(status_code=422, detail="end must be later than start")

    readings = EnergyReading.objects.filter(tenant=tenant)
    if meter_external_id:
        readings = readings.filter(meter__external_id=meter_external_id)
    if start is not None:
        readings = readings.filter(timestamp__gte=start)
    if end is not None:
        readings = readings.filter(timestamp__lt=end)
    readings = readings.order_by("-timestamp", "meter_id")
    total = readings.count()
    items = list(readings[offset : offset + limit])
    return {
        "tenant_id": str(tenant.id),
        "count": total,
        "limit": limit,
        "offset": offset,
        "results": [reading_response(reading) for reading in items],
    }


@app.post(
    "/v1/energy/readings",
    response_model=IngestionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def ingest_readings(
    payload: IngestionPayload,
    user=Depends(get_current_user),
) -> IngestionResponse:
    tenant = get_tenant_for_user(user, payload.tenant_id)
    meter = Meter.objects.filter(
        tenant=tenant,
        external_id=payload.meter_external_id,
        active=True,
    ).first()
    if meter is None:
        raise HTTPException(status_code=404, detail="Active meter not found for tenant")

    readings = [
        EnergyReading(
            tenant=tenant,
            meter=meter,
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
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Could not persist readings") from exc

    return IngestionResponse(
        accepted=len(readings),
        tenant_id=tenant.id,
        meter_external_id=meter.external_id,
    )


@app.get("/v1/dashboard/overview")
def dashboard_overview(
    tenant_id: UUID | None = None,
    hours: int = Query(default=24, ge=1, le=168),
    user=Depends(get_current_user),
) -> dict:
    tenant = (
        get_tenant_for_user(user, tenant_id)
        if tenant_id
        else Tenant.objects.filter(members=user).order_by("name").first()
    )
    if tenant is None:
        raise HTTPException(status_code=404, detail="No tenant available for this account")

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=hours)
    readings = EnergyReading.objects.filter(
        tenant=tenant,
        timestamp__gte=start,
        timestamp__lt=now,
    ).order_by("timestamp", "meter_id")
    if not readings.exists():
        raise HTTPException(status_code=404, detail="No readings available for tenant")

    service = CarbonCalculationService(tenant.grid_emission_factor_kgco2_per_kwh)
    intervals = service.aggregate_intervals(readings.iterator(chunk_size=5_000))
    summary = service.calculate_intervals(intervals)
    points = []
    for timestamp, (consumed, generated) in sorted(intervals.items()):
        match = service.match_interval(timestamp, consumed, generated)
        points.append(
            {
                "time": timestamp.strftime("%H:%M"),
                "timestamp": timestamp.isoformat(),
                "consumed": float(match.consumed_kwh),
                "renewable": float(match.generated_kwh),
                "emissions": float(match.emissions_kgco2),
            }
        )
    return {
        "tenant": tenant.name,
        "tenant_id": str(tenant.id),
        "updated_at": now.isoformat(),
        "totals": {
            "consumed_kwh": float(summary.consumed_kwh),
            "renewable_kwh": float(summary.generated_kwh),
            "matched_kwh": float(summary.matched_green_kwh),
            "emissions_kgco2": float(summary.emissions_kgco2),
        },
        "points": points,
    }


@app.post("/v1/reports/carbon", status_code=status.HTTP_202_ACCEPTED)
def request_carbon_report(
    payload: CarbonReportRequest,
    user=Depends(get_current_user),
) -> dict:
    tenant = get_tenant_for_user(user, payload.tenant_id)
    if payload.end - payload.start > timedelta(days=366):
        raise HTTPException(status_code=422, detail="Report range cannot exceed 366 days")

    report = CarbonReport.objects.create(
        tenant=tenant,
        requested_by=user,
        start=payload.start,
        end=payload.end,
    )
    try:
        generate_carbon_report.apply_async(
            args=(str(tenant.id), payload.start, payload.end, str(report.id)),
            task_id=str(report.id),
        )
    except OperationalError as exc:
        report.delete()
        raise HTTPException(status_code=503, detail="Report queue is unavailable") from exc
    report.refresh_from_db(fields=["status"])
    return {
        "id": str(report.id),
        "tenant_id": str(tenant.id),
        "status": report.status,
        "start": payload.start.isoformat(),
        "end": payload.end.isoformat(),
    }


@app.get("/v1/reports")
def list_reports(
    tenant_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    user=Depends(get_current_user),
) -> list[dict]:
    tenant = get_tenant_for_user(user, tenant_id)
    reports = CarbonReport.objects.filter(tenant=tenant)[:limit]

    return [
        {
            "id": str(report.id),
            "tenant_id": str(report.tenant_id),
            "start": report.start.isoformat(),
            "end": report.end.isoformat(),
            "created_at": report.created_at.isoformat(),
            "status": report.status,
        }
        for report in reports
    ]


@app.get("/v1/reports/{report_id}")
def retrieve_report(report_id: UUID, user=Depends(get_current_user)) -> dict:
    report = (
        CarbonReport.objects.filter(pk=report_id, tenant__members=user)
        .select_related("tenant")
        .first()
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")

    response = {
        "id": str(report.id),
        "tenant_id": str(report.tenant_id),
        "start": report.start.isoformat(),
        "end": report.end.isoformat(),
        "created_at": report.created_at.isoformat(),
        "status": report.status,
    }
    if report.result is not None:
        response["result"] = report.result
    if report.error_message:
        response["error"] = report.error_message
    return response


@app.get("/v1/forecasts/energy")
def forecast_energy(
    tenant_id: UUID,
    hours: int = Query(default=24, ge=1, le=168),
    user=Depends(get_current_user),
) -> dict:
    tenant = get_tenant_for_user(user, tenant_id)
    now = datetime.now(timezone.utc)
    history_start = now - timedelta(days=28)
    history = EnergyReading.objects.filter(
        tenant=tenant,
        timestamp__gte=history_start,
        timestamp__lt=now,
    ).order_by("timestamp", "meter_id")
    if not history.exists():
        raise HTTPException(
            status_code=404,
            detail="Historical readings are required to generate a forecast",
        )

    next_interval = datetime.fromtimestamp(
        ((int(now.timestamp()) + 899) // 900) * 900,
        tz=timezone.utc,
    )
    service = CarbonCalculationService(tenant.grid_emission_factor_kgco2_per_kwh)
    forecast = service.forecast_seasonal_mean(
        history.iterator(chunk_size=5_000),
        next_interval,
        intervals=hours * 4,
    )
    return {
        "tenant_id": str(tenant.id),
        "generated_at": now.isoformat(),
        "horizon_hours": hours,
        "method": forecast["method"],
        "history_days": forecast["history_days"],
        "coverage_percent": forecast["coverage_percent"],
        "points": forecast["points"],
        "notice": (
            "Historical weekday/time averages are a baseline, not an ML prediction. "
            "Intervals without comparable history are returned with null values."
        ),
    }
