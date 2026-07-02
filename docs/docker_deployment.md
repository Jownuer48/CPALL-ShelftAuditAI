# Docker Deployment

This Compose setup runs the full ShelfAuditAI runtime:

- PostgreSQL
- RabbitMQ
- FastAPI backend
- AI worker
- Streamlit dashboard

Docker deployment always uses PostgreSQL. SQLite remains available only as a local fallback when `DATABASE_URL` is not set.

## Start

From the project root:

```cmd
docker compose up -d --build
```

Check service status:

```cmd
docker compose ps
```

## Logs

```cmd
docker compose logs backend
docker compose logs worker
docker compose logs dashboard
```

Follow logs live:

```cmd
docker compose logs -f backend
docker compose logs -f worker
docker compose logs -f dashboard
```

## Stop

```cmd
docker compose down
```

This stops containers but keeps named volumes, including PostgreSQL data and runtime image folders.

## URLs

Backend API:

```text
http://localhost:8000
```

Swagger:

```text
http://localhost:8000/docs
```

Dashboard:

```text
http://localhost:8501
```

RabbitMQ management:

```text
http://localhost:15672
```

Default RabbitMQ login is `guest` / `guest`.

## Health Checks

```text
http://localhost:8000/health
http://localhost:8000/health/db
http://localhost:8000/health/rabbitmq
http://localhost:8000/health/models
```

You can also run:

```cmd
docker compose exec backend python /app/scripts/check_services.py --base-url http://localhost:8000
```

If checking from the host machine, use:

```cmd
backend\.venv\Scripts\python.exe scripts\check_services.py --base-url http://localhost:8000
```

## PostgreSQL

Compose service:

```text
service: postgres
container: shelf-postgres
database: shelf_audit
user: shelf_user
password: shelf_password
port: 5432
```

Connection string inside Docker:

```text
postgresql+psycopg2://shelf_user:shelf_password@postgres:5432/shelf_audit
```

Connect with a local database tool such as DBeaver:

```text
host: localhost
port: 5432
database: shelf_audit
user: shelf_user
password: shelf_password
```

## Shared Runtime Images

The backend, worker, and dashboard share these Docker named volumes:

```text
shelf_uploads   -> /app/backend/uploads
shelf_annotated -> /app/backend/annotated
```

The backend saves uploaded images, the worker writes annotated images, and the dashboard reads both.

## Required Models

The Docker image includes the model files already present in the project folder:

```text
backend/yolo_models/experiments/sku110k_product.pt
backend/yolo_models/shelf_yolo.pt
```

Do not exclude these files from the Docker build context. `/health/models` reports missing or empty model files.

## Common Issues

Model missing:

- `/health/models` returns `error`.
- Confirm model files exist in `backend/yolo_models`.
- Rebuild after copying model files: `docker compose up -d --build`.

RabbitMQ not ready yet:

- Worker logs may show temporary RabbitMQ connection errors.
- Wait a few seconds, then check `docker compose logs worker`.
- Verify `/health/rabbitmq`.

Wrong `DATABASE_URL`:

- `/health/db` returns `error`.
- In Docker, services must use host `postgres`, not `localhost`.
- Confirm the backend container environment points to `postgresql+psycopg2://shelf_user:shelf_password@postgres:5432/shelf_audit`.

Port already used:

- Docker may fail to bind `8000`, `8501`, `5432`, `5672`, or `15672`.
- Stop the other service using the port or change the host-side port in `docker-compose.yml`.

Docker Desktop not running:

- `docker compose up` fails before services start.
- Open Docker Desktop and wait until it is fully running.
