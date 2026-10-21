import unittest
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from pydantic import ValidationError

from ingestion.schemas import IngestionPayload
from mrv.services import CarbonCalculationService


class IngestionSchemaTests(unittest.TestCase):
    def test_reading_requires_timezone(self):
        with self.assertRaises(ValidationError):
            IngestionPayload.model_validate(
                {
                    "tenant_id": "8e739056-c3c4-4bba-85a1-a9f0ad59d61b",
                    "meter_external_id": "plant-01",
                    "readings": [
                        {
                            "timestamp": "2026-10-21T12:00:00",
                            "energy_consumed_kwh": 1,
                            "energy_generated_kwh": 0,
                        }
                    ],
                }
            )

    def test_reading_batch_rejects_duplicate_instants(self):
        with self.assertRaises(ValidationError):
            IngestionPayload.model_validate(
                {
                    "tenant_id": "8e739056-c3c4-4bba-85a1-a9f0ad59d61b",
                    "meter_external_id": "plant-01",
                    "readings": [
                        {
                            "timestamp": "2026-10-21T12:00:00+00:00",
                            "energy_consumed_kwh": 1,
                            "energy_generated_kwh": 0,
                        },
                        {
                            "timestamp": "2026-10-21T14:00:00+02:00",
                            "energy_consumed_kwh": 2,
                            "energy_generated_kwh": 0,
                        },
                    ],
                }
            )


class ForecastTests(unittest.TestCase):
    def test_matching_combines_meter_readings_for_each_interval(self):
        timestamp = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
        readings = [
            SimpleNamespace(
                timestamp=timestamp,
                energy_consumed_kwh=Decimal("10"),
                energy_generated_kwh=Decimal("0"),
            ),
            SimpleNamespace(
                timestamp=timestamp,
                energy_consumed_kwh=Decimal("0"),
                energy_generated_kwh=Decimal("6"),
            ),
        ]
        service = CarbonCalculationService(Decimal("0.4"))

        summary = service.calculate(readings)
        daily = service.calculate_by_day(readings)[timestamp.date()]
        monthly = service.calculate_by_month(readings)["2026-10"]

        for result in (summary, daily, monthly):
            self.assertEqual(result.consumed_kwh, Decimal("10"))
            self.assertEqual(result.generated_kwh, Decimal("6"))
            self.assertEqual(result.matched_green_kwh, Decimal("6"))
            self.assertEqual(result.net_grid_kwh, Decimal("4"))
            self.assertEqual(result.emissions_kgco2, Decimal("1.6"))

    def test_forecast_aggregates_meters_before_calculating_history_mean(self):
        timestamp = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
        readings = [
            SimpleNamespace(
                timestamp=timestamp,
                energy_consumed_kwh=Decimal("2"),
                energy_generated_kwh=Decimal("1"),
            ),
            SimpleNamespace(
                timestamp=timestamp,
                energy_consumed_kwh=Decimal("4"),
                energy_generated_kwh=Decimal("1"),
            ),
        ]
        service = CarbonCalculationService(Decimal("0.5"))

        forecast = service.forecast_seasonal_mean(readings, timestamp, intervals=1)

        self.assertEqual(forecast["coverage_percent"], 100)
        self.assertEqual(forecast["points"][0]["consumed_kwh"], "6")
        self.assertEqual(forecast["points"][0]["generated_kwh"], "2")
        self.assertEqual(forecast["points"][0]["emissions_kgco2"], "2.0")
        self.assertEqual(forecast["points"][0]["sample_count"], 1)

    def test_forecast_marks_unobserved_weekday_slots_unavailable(self):
        history_timestamp = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
        forecast_timestamp = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
        reading = SimpleNamespace(
            timestamp=history_timestamp,
            energy_consumed_kwh=Decimal("1"),
            energy_generated_kwh=Decimal("0"),
        )
        service = CarbonCalculationService(Decimal("0.4"))

        forecast = service.forecast_seasonal_mean([reading], forecast_timestamp, intervals=1)

        self.assertEqual(forecast["coverage_percent"], 0)
        self.assertIsNone(forecast["points"][0]["consumed_kwh"])


if __name__ == "__main__":
    unittest.main()
