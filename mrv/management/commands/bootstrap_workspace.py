from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from mrv.models import Meter, Tenant


class Command(BaseCommand):
    help = "Create or update a workspace and its first meter."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-name", required=True)
        parser.add_argument("--tenant-slug", required=True)
        parser.add_argument("--meter-id", required=True, help="External meter identifier.")
        parser.add_argument("--meter-name", required=True)
        parser.add_argument(
            "--meter-type",
            choices=Meter.MeterType.values,
            default=Meter.MeterType.BIDIRECTIONAL,
        )
        parser.add_argument(
            "--grid-emission-factor",
            required=True,
            type=Decimal,
            help="Grid emission factor in kg CO2e per kWh.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["grid_emission_factor"] < 0:
            raise CommandError("Grid emission factor cannot be negative.")

        tenant, tenant_created = Tenant.objects.update_or_create(
            slug=options["tenant_slug"],
            defaults={
                "name": options["tenant_name"],
                "grid_emission_factor_kgco2_per_kwh": options["grid_emission_factor"],
            },
        )
        meter, meter_created = Meter.objects.update_or_create(
            tenant=tenant,
            external_id=options["meter_id"],
            defaults={
                "name": options["meter_name"],
                "meter_type": options["meter_type"],
                "active": True,
            },
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Workspace {'created' if tenant_created else 'updated'}: "
                f"{tenant.name} ({tenant.id})"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Meter {'created' if meter_created else 'updated'}: "
                f"{meter.name} ({meter.external_id})"
            )
        )
