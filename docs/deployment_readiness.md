# Deployment Readiness Checks

The FastAPI backend exposes health endpoints for internal server deployment checks.

In local development, examples use:

```text
http://localhost:8000
```

In production, replace `localhost:8000` with the company server IP address or domain name.

## Endpoints

### Overall

```cmd
curl http://localhost:8000/health
```

Returns the combined status for the backend, database, RabbitMQ, and required model files.

Example:

```json
{
  "status": "ok",
  "timestamp": "2026-07-02T10:30:00+00:00",
  "analysis_mode": "sku110k_planogram",
  "database": {
    "status": "ok",
    "mode": "postgres",
    "message": "Database connectivity ok."
  },
  "rabbitmq": {
    "status": "ok",
    "host": "localhost",
    "port": 5672,
    "queue": "shelf_audit_queue",
    "message": "RabbitMQ connectivity ok."
  },
  "models": {
    "status": "ok",
    "missing": [],
    "models": [
      {
        "name": "sku110k_product",
        "path": "backend/yolo_models/experiments/sku110k_product.pt",
        "exists": true,
        "size_bytes": 123456,
        "status": "ok"
      },
      {
        "name": "shelf_yolo",
        "path": "backend/yolo_models/shelf_yolo.pt",
        "exists": true,
        "size_bytes": 123456,
        "status": "ok"
      }
    ]
  }
}
```

### Database

```cmd
curl http://localhost:8000/health/db
```

Checks database connectivity with a lightweight query. It supports PostgreSQL through `DATABASE_URL` and SQLite fallback. It reports only the database mode (`postgres` or `sqlite`) and never exposes passwords or the full database URL.

### RabbitMQ

```cmd
curl http://localhost:8000/health/rabbitmq
```

Checks RabbitMQ connectivity and the configured queue using the backend RabbitMQ settings. It does not publish an analysis job.

### Models

```cmd
curl http://localhost:8000/health/models
```

Checks required model files exist and are larger than zero bytes:

```text
backend/yolo_models/experiments/sku110k_product.pt
backend/yolo_models/shelf_yolo.pt
```

Missing or empty model files are listed in the `missing` field.

## Service Check Script

From the project root:

```cmd
backend\.venv\Scripts\python.exe scripts\check_services.py
```

For a deployed server:

```cmd
backend\.venv\Scripts\python.exe scripts\check_services.py --base-url http://SERVER-IP-OR-DOMAIN:8000
```

The script prints a readable summary and exits non-zero if the overall health status is `error` or if the backend cannot be reached.

## Network And Server Team Usage

The server team can use these endpoints from:

- A browser for quick manual checks.
- `curl` from the server or another machine on the same network.
- A load balancer, uptime monitor, or deployment script.

For production monitoring, use `/health` as the primary readiness check and use the component endpoints to diagnose failures.

## Common Failure Causes

`/health/db` returns `error`:

- PostgreSQL container/service is not running.
- `DATABASE_URL` is missing or points to the wrong host/port/database.
- `psycopg2-binary` is not installed in `backend\.venv`.
- Database user/password is incorrect.

`/health/rabbitmq` returns `error`:

- RabbitMQ container/service is not running.
- `RABBITMQ_HOST` or `RABBITMQ_PORT` is wrong.
- Firewall or network routing blocks the port.
- RabbitMQ credentials are wrong.

`/health/models` returns `error`:

- `sku110k_product.pt` is missing or empty.
- `shelf_yolo.pt` is missing or empty.
- Model files were not copied to the server.

`/health` returns `error`:

- One or more component checks failed. Read `database`, `rabbitmq`, and `models` fields for the exact cause.
