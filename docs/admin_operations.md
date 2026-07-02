# Admin Operations

These endpoints help recover inspections that are stuck because the worker was stopped or RabbitMQ was unavailable.

## List Pending Inspections

```cmd
curl "http://localhost:8000/api/admin/inspections/pending"
```

The response contains newest `PENDING` inspections first.

## Mark An Inspection Failed

```cmd
curl -X POST "http://localhost:8000/api/admin/inspections/123/mark-failed"
```

Replace `123` with the inspection id. This does not delete uploaded or annotated images. It updates the inspection to:

```text
status = FAILED
result = FAIL
error_message = Marked failed by admin action because job was stuck or could not complete.
```

## Retry An Inspection

```cmd
curl -X POST "http://localhost:8000/api/admin/inspections/123/retry"
```

Retry keeps the same uploaded `image_name`, resets the row to `PENDING`, clears `error_message`, updates `updated_at`, and publishes a new RabbitMQ job. If RabbitMQ is unavailable, the endpoint returns `503` and marks the row `FAILED` with the publish error so it does not remain stuck.

## Helper Script

Print curl commands:

```cmd
backend\.venv\Scripts\python.exe scripts\test_admin_inspection_actions.py --inspection-id 123
```

Optionally call the endpoints:

```cmd
backend\.venv\Scripts\python.exe scripts\test_admin_inspection_actions.py --call pending
backend\.venv\Scripts\python.exe scripts\test_admin_inspection_actions.py --call mark-failed --inspection-id 123
backend\.venv\Scripts\python.exe scripts\test_admin_inspection_actions.py --call retry --inspection-id 123
```

## Verify In PostgreSQL Or DBeaver

Use the `inspections` table. Helpful checks:

```sql
SELECT id, image_name, status, result, error_message, updated_at
FROM inspections
WHERE status = 'PENDING'
ORDER BY id DESC;
```

```sql
SELECT id, image_name, status, result, error_message, updated_at
FROM inspections
WHERE id = 123;
```

In DBeaver, connect with:

```text
host: localhost
port: 5432
database: shelf_audit
user: shelf_user
password: shelf_password
```
