# MRV CleanTech Platform

## Project structure

```text
.
├── config/                 # Django settings, WSGI, Celery application
├── frontend/               # React + TypeScript command center dashboard
├── ingestion/              # FastAPI IoT ingestion service
├── mrv/                    # Tenant, meter, time-series models and domain services
│   ├── migrations/         # PostgreSQL and TimescaleDB schema
│   ├── models.py
│   ├── services.py
│   └── tasks.py
├── docker/
│   ├── Dockerfile.django
│   └── Dockerfile.fastapi
├── docker-compose.yml
├── manage.py
└── requirements.txt
```

## Run

```bash
docker compose up --build
```

Django is available on `http://localhost:8000`; the MRV command center is available on `http://localhost:3000`; ingestion is available on `http://localhost:8001`.

The dashboard uses live API data when a tenant has readings. With an empty database it renders a clearly labeled demo workspace so the interface can be evaluated immediately.

For frontend-only development:

```bash
cd frontend
npm install
npm run dev
```

The FastAPI Swagger contract is available at `http://localhost:8001/docs`.

### Prepare a workspace for ingestion

A new database has no tenants or meters. Create a workspace and its first meter
after the services are up:

```bash
docker compose exec web python manage.py bootstrap_workspace --tenant-name "Northstar Metals" --tenant-slug northstar-metals --meter-id plant-01 --meter-name "Plant 01" --grid-emission-factor 0.4
```

Use the grid emission factor applicable to your location. The command prints
the tenant UUID required by `POST /v1/energy/readings`. Send readings for the
meter ID supplied above; the dashboard switches from demo data to live data
once readings from the last 24 hours are available.

The Compose services wait for PostgreSQL, Redis, migrations, and the ingestion
health check before starting their dependents. To use a non-default API URL in
the browser, set `VITE_API_URL` in `.env` and rebuild the frontend image.


Explaination


In simple terms, this project is an energy and carbon monitoring platform for facilities/metered assets. It collects interval energy data, calculates how much was renewable vs grid-supplied, and shows the result in a dashboard.

The main idea:
- Meters produce energy readings
- FastAPI accepts those readings
- Django stores them in a time-series database
- Carbon logic matches renewable generation against consumption
- React dashboard displays totals and charts

You can see the overall architecture in `README.md`, and the core app wiring in `docker-compose.yml`.

How the system is organized

1. Django backend
- Located in `config/settings.py`
- This is the main application layer
- It configures:
  - PostgreSQL database
  - Redis for Celery
  - Django app setup
  - timezone and settings

2. Domain models
- In `mrv/models.py`
- It defines:
  - Tenant: a customer/organization
  - Meter: a physical energy meter
  - EnergyReading: a 15-minute interval reading with consumed/generated energy values

This model is specifically built for time-series analytics, which is why the project uses TimescaleDB/PostgreSQL.

3. FastAPI ingestion service
- In `ingestion/main.py`
- This service accepts energy reading batches from devices or systems
- It validates each payload and stores it into Django models
- It exposes endpoints like:
  - /health
  - /v1/dashboard/overview
  - /v1/energy/readings

4. React frontend
- In `frontend/src/App.tsx`
- This is the command-center dashboard
- It fetches live data from the ingestion API
- If no live data exists, it falls back to a demo dataset so the UI still works

5. Celery worker
- In `mrv/tasks.py`
- This runs background jobs to generate carbon summary reports for periods like days or months

What happens when data is ingested

The main ingestion endpoint is:

- POST /v1/energy/readings

What it does:
- receives tenant_id, meter_external_id, and a batch of readings
- looks for an active meter belonging to that tenant
- validates each reading
- saves each interval as an EnergyReading row

Important part: it uses bulk_create with update_conflicts, so if the same meter/timestamp already exists, it updates that record instead of creating duplicates. This is ideal for time-series meter data.

How the carbon calculation works

The actual logic is in `mrv/services.py`.

For each interval:
- consumed_kwh = energy consumed
- generated_kwh = renewable generation
- matched_green_kwh = min(consumed_kwh, generated_kwh)
- net_grid_kwh = consumed_kwh - matched_green_kwh
- emissions_kgco2 = net_grid_kwh * grid_emission_factor

This means:
- if the site consumed 100 kWh and generated 60 kWh, only 60 kWh can be “matched” as renewable
- the remaining 40 kWh is assumed to come from the grid
- emissions are calculated based on that grid usage

This is called temporal matching: matching renewable generation to consumption within the same interval.

How the dashboard gets data

The dashboard calls:

- GET /v1/dashboard/overview

That endpoint:
- finds a tenant
- fetches the last 24 hours of readings
- calculates totals and time-series points
- returns:
  - total consumed kWh
  - renewable matched kWh
  - emissions
  - per-hour chart points

Then the frontend renders:
- KPI cards
- charts
- “Live monitoring” status
- renewable matching percentage

If there is no live tenant data, it switches to a demo dataset. That is why the app still looks fully functional immediately after startup.

How the whole platform starts

Using Docker Compose:
- db: TimescaleDB/PostgreSQL
- redis: message broker
- web: Django backend
- ingestion: FastAPI ingestion service
- frontend: React dashboard
- worker: Celery job runner

This means the app is a distributed but connected system:
- the frontend talks to ingestion
- ingestion writes into the same database
- Django and Celery handle backend processing and reports

In one sentence:
This project is a full-stack MRV platform that measures energy usage, matches renewable generation to consumption, computes carbon emissions, and visualizes the result in a live dashboard.

If you want, I can also explain:
- the exact request/response flow for one reading
- the database schema in more detail
- how the frontend chart is built from the backend JSON
- how to run this project locally step by step