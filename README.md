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
