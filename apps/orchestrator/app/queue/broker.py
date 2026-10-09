"""RabbitMQ wiring with a dead-letter queue from day one.

Topology:  exchange `fieldflow` (topic) --> queue `events`  (x-dead-letter-exchange = fieldflow.dlx)
           exchange `fieldflow.dlx`      --> queue `events.dlq`
A handler that raises → the message is nacked without requeue → it lands in events.dlq.
That is NFR-3 (Salesforce-down / retry / DLQ) wired in miniature.
"""

from __future__ import annotations

import json
import traceback
from collections.abc import Awaitable, Callable

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from app.logging import get_logger

log = get_logger("broker")

EXCHANGE = "fieldflow"
DLX = "fieldflow.dlx"
QUEUE = "events"
DLQ = "events.dlq"

Handler = Callable[[str, dict], Awaitable[None]]


class Broker:
    def __init__(self, url: str) -> None:
        self._url = url
        self._conn: aio_pika.abc.AbstractRobustConnection | None = None
        self._channel: aio_pika.abc.AbstractChannel | None = None
        self._exchange: aio_pika.abc.AbstractExchange | None = None
        self._queue: aio_pika.abc.AbstractQueue | None = None

    @property
    def is_open(self) -> bool:
        """True when the robust connection exists and isn't closed (read-only; for /health/deps)."""
        return self._conn is not None and not self._conn.is_closed

    async def connect(self) -> None:
        self._conn = await aio_pika.connect_robust(self._url)
        self._channel = await self._conn.channel()
        await self._channel.set_qos(prefetch_count=10)

        self._exchange = await self._channel.declare_exchange(
            EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
        )
        dlx = await self._channel.declare_exchange(DLX, aio_pika.ExchangeType.TOPIC, durable=True)
        dlq = await self._channel.declare_queue(DLQ, durable=True)
        await dlq.bind(dlx, routing_key="#")

        self._queue = await self._channel.declare_queue(
            QUEUE, durable=True, arguments={"x-dead-letter-exchange": DLX}
        )
        await self._queue.bind(self._exchange, routing_key="appointment.*")
        log.info("broker.connected", exchange=EXCHANGE, queue=QUEUE, dlq=DLQ)

    async def publish(self, routing_key: str, body: dict) -> None:
        assert self._exchange is not None
        await self._exchange.publish(
            aio_pika.Message(
                body=json.dumps(body).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                content_type="application/json",
            ),
            routing_key=routing_key,
        )

    async def start_consuming(self, handler: Handler) -> None:
        assert self._queue is not None

        async def on_message(message: AbstractIncomingMessage) -> None:
            try:
                body = json.loads(message.body)
                await handler(message.routing_key or "", body)
                await message.ack()
            except Exception as exc:  # noqa: BLE001 — route failures to the DLQ, don't crash
                log.error("broker.handler_failed", error=str(exc),
                          tb=traceback.format_exc())
                await message.nack(requeue=False)  # → events.dlq

        await self._queue.consume(on_message)

    async def dlq_stats(self) -> dict:
        """How many messages are parked in the dead-letter queue (read-only, passive declare)."""
        assert self._channel is not None
        q = await self._channel.declare_queue(DLQ, durable=True, passive=True)
        return {"queue": DLQ, "depth": q.declaration_result.message_count}

    async def peek_dlq(self, limit: int = 20) -> list[dict]:
        """Read up to `limit` parked messages WITHOUT consuming them: get each, then requeue it.
        A peek, not a drain — the messages stay in the DLQ for the replay."""
        assert self._queue is not None and self._channel is not None
        dlq = await self._channel.get_queue(DLQ)
        out: list[dict] = []
        for _ in range(limit):
            msg = await dlq.get(no_ack=False, fail=False)
            if msg is None:
                break
            try:
                out.append({"routingKey": msg.routing_key, "body": json.loads(msg.body)})
            except Exception:  # noqa: BLE001 — a malformed parked message still shows raw
                raw = msg.body.decode("utf-8", "replace")
                out.append({"routingKey": msg.routing_key, "body": raw})
            await msg.nack(requeue=True)  # put it back — this is a peek
        return out

    async def replay_dlq(self, limit: int = 20) -> int:
        """Re-publish parked messages to the main exchange (keeping their routing key) and ack them
        off the DLQ. Use after the dependency is healthy again. Returns how many were replayed."""
        assert self._channel is not None and self._exchange is not None
        dlq = await self._channel.get_queue(DLQ)
        replayed = 0
        for _ in range(limit):
            msg = await dlq.get(no_ack=False, fail=False)
            if msg is None:
                break
            await self._exchange.publish(
                aio_pika.Message(body=msg.body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                                 content_type="application/json"),
                routing_key=msg.routing_key or "appointment.at_risk",
            )
            await msg.ack()
            replayed += 1
        log.info("broker.dlq_replayed", count=replayed)
        return replayed

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
