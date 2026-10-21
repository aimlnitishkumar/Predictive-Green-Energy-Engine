from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterPayload(APIModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)
    tenant_name: str = Field(min_length=1, max_length=255)
    tenant_slug: str | None = Field(default=None, min_length=1, max_length=100)
    grid_emission_factor_kgco2_per_kwh: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        le=Decimal("9999.99999999"),
        max_digits=12,
        decimal_places=8,
    )


class LoginPayload(APIModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class TenantCreate(APIModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=100)
    grid_emission_factor_kgco2_per_kwh: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        le=Decimal("9999.99999999"),
        max_digits=12,
        decimal_places=8,
    )


class TenantUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=100)
    grid_emission_factor_kgco2_per_kwh: Decimal | None = Field(
        default=None,
        ge=0,
        le=Decimal("9999.99999999"),
        max_digits=12,
        decimal_places=8,
    )


class MeterCreate(APIModel):
    external_id: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    meter_type: Literal["consumption", "generation", "bidirectional"]


class MeterUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    meter_type: Literal["consumption", "generation", "bidirectional"] | None = None
    active: bool | None = None


class ReadingPayload(APIModel):
    timestamp: datetime
    energy_consumed_kwh: Decimal = Field(ge=0, max_digits=18, decimal_places=6)
    energy_generated_kwh: Decimal = Field(ge=0, max_digits=18, decimal_places=6)
    quality: str = Field(default="measured", min_length=1, max_length=32)

    @field_validator("timestamp")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")
        return value


class IngestionPayload(APIModel):
    tenant_id: UUID
    meter_external_id: str = Field(min_length=1, max_length=255)
    readings: list[ReadingPayload] = Field(min_length=1, max_length=10_000)

    @model_validator(mode="after")
    def require_unique_timestamps(self) -> IngestionPayload:
        timestamps = [reading.timestamp.astimezone(timezone.utc) for reading in self.readings]
        if len(set(timestamps)) != len(timestamps):
            raise ValueError("readings must not contain duplicate timestamps")
        return self


class IngestionResponse(APIModel):
    accepted: int
    tenant_id: UUID
    meter_external_id: str


class CarbonReportRequest(APIModel):
    tenant_id: UUID
    start: datetime
    end: datetime

    @field_validator("start", "end")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("report timestamps must include a timezone")
        return value

    @model_validator(mode="after")
    def require_ordered_range(self) -> CarbonReportRequest:
        if self.end <= self.start:
            raise ValueError("end must be later than start")
        return self
