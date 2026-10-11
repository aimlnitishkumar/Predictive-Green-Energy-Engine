from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable


ZERO = Decimal("0")


@dataclass(frozen=True)
class IntervalMatch:
    timestamp: datetime
    consumed_kwh: Decimal
    generated_kwh: Decimal
    matched_green_kwh: Decimal
    net_grid_kwh: Decimal
    emissions_kgco2: Decimal


@dataclass(frozen=True)
class FootprintSummary:
    consumed_kwh: Decimal
    generated_kwh: Decimal
    matched_green_kwh: Decimal
    net_grid_kwh: Decimal
    emissions_kgco2: Decimal


class CarbonCalculationService:
    """Applies temporal matching at the finest available 15-minute interval."""

    def __init__(self, grid_emission_factor_kgco2_per_kwh: Decimal):
        if grid_emission_factor_kgco2_per_kwh < ZERO:
            raise ValueError("Grid emission factor cannot be negative")
        self.grid_emission_factor = grid_emission_factor_kgco2_per_kwh

    def match_interval(
        self,
        timestamp: datetime,
        consumed_kwh: Decimal,
        generated_kwh: Decimal,
    ) -> IntervalMatch:
        if consumed_kwh < ZERO or generated_kwh < ZERO:
            raise ValueError("Energy values cannot be negative")
        matched_green = min(consumed_kwh, generated_kwh)
        net_grid = consumed_kwh - matched_green
        return IntervalMatch(
            timestamp=timestamp,
            consumed_kwh=consumed_kwh,
            generated_kwh=generated_kwh,
            matched_green_kwh=matched_green,
            net_grid_kwh=net_grid,
            emissions_kgco2=net_grid * self.grid_emission_factor,
        )

    def calculate(self, readings: Iterable[object]) -> FootprintSummary:
        total = FootprintSummary(ZERO, ZERO, ZERO, ZERO, ZERO)
        for reading in readings:
            match = self.match_interval(
                timestamp=reading.timestamp,
                consumed_kwh=Decimal(reading.energy_consumed_kwh),
                generated_kwh=Decimal(reading.energy_generated_kwh),
            )
            total = FootprintSummary(
                consumed_kwh=total.consumed_kwh + match.consumed_kwh,
                generated_kwh=total.generated_kwh + match.generated_kwh,
                matched_green_kwh=total.matched_green_kwh + match.matched_green_kwh,
                net_grid_kwh=total.net_grid_kwh + match.net_grid_kwh,
                emissions_kgco2=total.emissions_kgco2 + match.emissions_kgco2,
            )
        return total

    def calculate_by_day(self, readings: Iterable[object]) -> dict:
        grouped = {}
        for reading in readings:
            day = reading.timestamp.astimezone(timezone.utc).date()
            grouped.setdefault(day, []).append(reading)
        return {day: self.calculate(day_readings) for day, day_readings in grouped.items()}

    def calculate_by_month(self, readings: Iterable[object]) -> dict:
        grouped = {}
        for reading in readings:
            timestamp = reading.timestamp.astimezone(timezone.utc)
            month = timestamp.strftime("%Y-%m")
            grouped.setdefault(month, []).append(reading)
        return {month: self.calculate(month_readings) for month, month_readings in grouped.items()}
