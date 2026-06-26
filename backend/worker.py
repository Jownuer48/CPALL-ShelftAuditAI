import json
import time
import traceback

import pika

from ai_analyzer import analyze_image
from database import init_db, update_inspection_result, update_inspection_status
from queue_client import SHELF_QUEUE_NAME, get_connection

RECONNECT_DELAY_SECONDS = 5


def process_job(message: dict) -> None:
    if message.get("type") == "health_check":
        print("[WORKER] Health check received")
        return

    inspection_id = message.get("inspection_id")
    image_path = message.get("image_path")

    if not inspection_id or not image_path:
        print(f"[WORKER] Ignoring invalid job: {message}")
        return

    print(f"[WORKER] Processing inspection_id={inspection_id}")
    update_inspection_status(int(inspection_id), "PROCESSING")

    result = analyze_image(str(image_path))
    update_inspection_result(
        inspection_id=int(inspection_id),
        detected_model=result.get("detected_model"),
        model_score=result.get("model_score"),
        result=result.get("result", "FAILED"),
        missing_count=int(result.get("missing_count", 0)),
        missing_items=result.get("missing_items", []),
        annotated_image_name=result.get("annotated_image_name"),
    )
    print(f"[WORKER] DONE inspection_id={inspection_id}")


def main() -> None:
    init_db()

    while True:
        connection = None

        try:
            connection = get_connection()
            channel = connection.channel()
            channel.queue_declare(queue=SHELF_QUEUE_NAME, durable=True)
            channel.basic_qos(prefetch_count=1)

            def callback(ch, method, properties, body):
                inspection_id = None
                try:
                    message = json.loads(body.decode("utf-8"))
                    inspection_id = message.get("inspection_id")
                    process_job(message)
                except Exception as exc:
                    print(f"[WORKER] ERROR {exc}")
                    traceback.print_exc()
                    if inspection_id:
                        update_inspection_status(int(inspection_id), "FAILED", str(exc))
                finally:
                    ch.basic_ack(delivery_tag=method.delivery_tag)

            channel.basic_consume(queue=SHELF_QUEUE_NAME, on_message_callback=callback)
            print("[WORKER] Waiting for jobs...")
            channel.start_consuming()

        except pika.exceptions.AMQPConnectionError as exc:
            print(f"[WORKER] RabbitMQ not ready: {exc}")
            time.sleep(RECONNECT_DELAY_SECONDS)
        except KeyboardInterrupt:
            print("[WORKER] Stopping...")
            if connection and connection.is_open:
                connection.close()
            break
        except Exception as exc:
            print(f"[WORKER] ERROR {exc}")
            traceback.print_exc()
            time.sleep(RECONNECT_DELAY_SECONDS)
        finally:
            if connection and connection.is_open:
                connection.close()


if __name__ == "__main__":
    main()
