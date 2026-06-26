import json
import os
from typing import Dict

import pika

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "guest")
SHELF_QUEUE_NAME = os.getenv("SHELF_QUEUE_NAME", "shelf_audit_queue")


def get_connection() -> pika.BlockingConnection:
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
    parameters = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        credentials=credentials,
        heartbeat=60,
        blocked_connection_timeout=30,
    )
    return pika.BlockingConnection(parameters)


def publish_job(message: Dict) -> None:
    body = json.dumps(message, ensure_ascii=False).encode("utf-8")

    connection = get_connection()
    try:
        channel = connection.channel()
        channel.queue_declare(queue=SHELF_QUEUE_NAME, durable=True)
        channel.basic_publish(
            exchange="",
            routing_key=SHELF_QUEUE_NAME,
            body=body,
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json",
            ),
        )
    finally:
        connection.close()
