from dataclasses import dataclass
from collections import defaultdict
from datetime import datetime, timedelta, timezone
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
        return self.calculate_intervals(self.aggregate_intervals(readings))

    @staticmethod
    def aggregate_intervals(
        readings: Iterable[object],
    ) -> dict[datetime, tuple[Decimal, Decimal]]:
        intervals = {}
        for reading in readings:
            timestamp = reading.timestamp.astimezone(timezone.utc)
            consumed, generated = intervals.get(timestamp, (ZERO, ZERO))
            intervals[timestamp] = (
                consumed + Decimal(reading.energy_consumed_kwh),
                generated + Decimal(reading.energy_generated_kwh),
            )
        return intervals

    def calculate_intervals(
        self,
        intervals: dict[datetime, tuple[Decimal, Decimal]],
    ) -> FootprintSummary:
        total = FootprintSummary(ZERO, ZERO, ZERO, ZERO, ZERO)
        for timestamp, (consumed, generated) in intervals.items():
            match = self.match_interval(timestamp, consumed, generated)
            total = self._add_match(total, match)
        return total

    def calculate_by_day(self, readings: Iterable[object]) -> dict:
        grouped = {}
        intervals = self.aggregate_intervals(readings)
        for timestamp, (consumed, generated) in intervals.items():
            day = timestamp.date()
            match = self.match_interval(timestamp, consumed, generated)
            grouped[day] = self._add_match(
                grouped.get(day, FootprintSummary(ZERO, ZERO, ZERO, ZERO, ZERO)),
                match,
            )
        return grouped

    def calculate_by_month(self, readings: Iterable[object]) -> dict:
        grouped = {}
        intervals = self.aggregate_intervals(readings)
        for timestamp, (consumed, generated) in intervals.items():
            month = timestamp.strftime("%Y-%m")
            match = self.match_interval(timestamp, consumed, generated)
            grouped[month] = self._add_match(
                grouped.get(month, FootprintSummary(ZERO, ZERO, ZERO, ZERO, ZERO)),
                match,
            )
        return grouped

    @staticmethod
    def _add_match(total: FootprintSummary, match: IntervalMatch) -> FootprintSummary:
        return FootprintSummary(
            consumed_kwh=total.consumed_kwh + match.consumed_kwh,
            generated_kwh=total.generated_kwh + match.generated_kwh,
            matched_green_kwh=total.matched_green_kwh + match.matched_green_kwh,
            net_grid_kwh=total.net_grid_kwh + match.net_grid_kwh,
            emissions_kgco2=total.emissions_kgco2 + match.emissions_kgco2,
        )

    def forecast_seasonal_mean(
        self,
        readings: Iterable[object],
        forecast_start: datetime,
        intervals: int,
    ) -> dict:
        """Forecast 15-minute values from matching weekday/time historical means."""
        history = defaultdict(lambda: [ZERO, ZERO, 0])
        for timestamp, (consumed, generated) in self.aggregate_intervals(readings).items():
            key = (timestamp.weekday(), timestamp.hour * 4 + timestamp.minute // 15)
            history[key][0] += consumed
            history[key][1] += generated
            history[key][2] += 1

        points = []
        covered = 0
        for index in range(intervals):
            timestamp = forecast_start + timedelta(minutes=15 * index)
            timestamp = timestamp.astimezone(timezone.utc)
            key = (timestamp.weekday(), timestamp.hour * 4 + timestamp.minute // 15)
            consumed_total, generated_total, sample_count = history[key]
            if sample_count:
                consumed = consumed_total / sample_count
                generated = generated_total / sample_count
                match = self.match_interval(timestamp, consumed, generated)
                points.append(
                    {
                        "timestamp": timestamp.isoformat(),
                        "consumed_kwh": str(match.consumed_kwh),
                        "generated_kwh": str(match.generated_kwh),
                        "matched_green_kwh": str(match.matched_green_kwh),
                        "net_grid_kwh": str(match.net_grid_kwh),
                        "emissions_kgco2": str(match.emissions_kgco2),
                        "sample_count": sample_count,
                    }
                )
                covered += 1
            else:
                points.append(
                    {
                        "timestamp": timestamp.isoformat(),
                        "consumed_kwh": None,
                        "generated_kwh": None,
                        "matched_green_kwh": None,
                        "net_grid_kwh": None,
                        "emissions_kgco2": None,
                        "sample_count": 0,
                    }
                )

        return {
            "method": "historical_weekday_time_mean",
            "history_days": 28,
            "coverage_percent": (covered * 100 / intervals) if intervals else 0,
            "points": points,
        }
