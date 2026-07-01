# PostgreSQL Setup

This project can use PostgreSQL for server deployment while keeping SQLite as a local fallback.

## Start PostgreSQL

From the project root:

```cmd
docker compose up -d postgres
```

The Compose service uses:

```text
database: shelf_audit
user: shelf_user
password: shelf_password
host: localhost
port: 5432
```

`start_all.cmd` starts PostgreSQL before the backend, worker, and dashboard.

## Set DATABASE_URL

For PostgreSQL:

```cmd
set DATABASE_URL=postgresql+psycopg2://shelf_user:shelf_password@localhost:5432/shelf_audit
```

If `DATABASE_URL` is not set, the backend falls back to:

```text
sqlite:///backend/shelf_audit.db
```

## Migrate SQLite Records

Install backend dependencies first so the PostgreSQL driver is available:

```cmd
backend\.venv\Scripts\pip.exe install -r backend\requirements.txt
```

Check the active runtime:

```cmd
backend\.venv\Scripts\python.exe scripts\check_runtime_env.py
```

Then run:

```cmd
backend\.venv\Scripts\python.exe scripts\migrate_sqlite_to_postgres.py
```

The script reads from `backend/shelf_audit.db`, inserts missing rows into PostgreSQL by `id`, skips existing rows, and never deletes SQLite records.

To use a custom target:

```cmd
backend\.venv\Scripts\python.exe scripts\migrate_sqlite_to_postgres.py --database-url postgresql+psycopg2://shelf_user:shelf_password@localhost:5432/shelf_audit
```

## Verify With psql

If `psql` is installed locally:

```cmd
psql postgresql://shelf_user:shelf_password@localhost:5432/shelf_audit -c "SELECT COUNT(*) FROM inspections;"
psql postgresql://shelf_user:shelf_password@localhost:5432/shelf_audit -c "SELECT id, branch_code, status, result, created_at FROM inspections ORDER BY id DESC LIMIT 10;"
```

Or from inside the container:

```cmd
docker exec -it shelf-postgres psql -U shelf_user -d shelf_audit
```
