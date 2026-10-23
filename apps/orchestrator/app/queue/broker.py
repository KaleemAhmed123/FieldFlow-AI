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
from time import perf_counter

import aio_pika
import logfire
from aio_pika.abc import AbstractIncomingMessage

from app import telemetry
from app.logging import get_logger

log = get_logger("broker")

EXCHANGE = "fieldflow"
DLX = "fieldflow.dlx"
QUEUE = "events"
DLQ = "events.dlq"

# Retry tier before the DLQ (AI-REL-01 / P0-5). A handler failure is retried with backoff instead of
# dead-lettering now: the message is parked in a fixed-TTL retry queue that dead-letters back
# to the main exchange when the delay elapses. Three tiers → 3 retries at 5s / 30s / 120s, then DLQ.
# Fixed-TTL-per-tier (not per-message TTL) avoids the head-of-line-blocking bug where a long delay
# stalls a shorter one queued behind it.
RETRY_EXCHANGE = "fieldflow.retry"
MAX_RETRIES = 3
RETRY_TIERS = (  # (routing key, queue name, delay ms) — one per attempt
    ("retry.5s", "events.retry.5s", 5_000),
    ("retry.30s", "events.retry.30s", 30_000),
    ("retry.120s", "events.retry.120s", 120_000),
)

Handler = Callable[[str, dict], Awaitable[None]]


def next_retry_key(attempts: int) -> str | None:
    """The retry routing key for the next attempt, given how many retries already happened — or None
    when the 3 retries are spent (the message then dead-letters to events.dlq)."""
    return RETRY_TIERS[attempts][0] if attempts < MAX_RETRIES else None


def _trace_header() -> dict:
    """The current OTel trace context as a message header, so the consumer can continue the SAME
    trace (one tree from the SF webhook through the whole case). Empty when no active span."""
    tp = logfire.get_context().get("traceparent")
    return {"traceparent": tp} if tp else {}


class Broker:
    def __init__(self, url: str) -> None:
        self._url = url
        self._conn: aio_pika.abc.AbstractRobustConnection | None = None
        self._channel: aio_pika.abc.AbstractChannel | None = None
        self._exchange: aio_pika.abc.AbstractExchange | None = None
        self._queue: aio_pika.abc.AbstractQueue | None = None
        self._retry_exchange: aio_pika.abc.AbstractExchange | None = None

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

        # Retry flow (P0-5): a retry exchange + one fixed-TTL queue per backoff tier, each
        # dead-lettering back to the MAIN exchange so an expired retry is re-consumed from `events`.
        retry_x = await self._channel.declare_exchange(
            RETRY_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
        )
        for key, qname, ttl in RETRY_TIERS:
            rq = await self._channel.declare_queue(qname, durable=True, arguments={
                "x-dead-letter-exchange": EXCHANGE,
                "x-dead-letter-routing-key": "appointment.at_risk",
                "x-message-ttl": ttl,
            })
            await rq.bind(retry_x, routing_key=key)
        self._retry_exchange = retry_x
        log.info("broker.connected", exchange=EXCHANGE, queue=QUEUE, dlq=DLQ, retries=MAX_RETRIES)

    async def publish(self, routing_key: str, body: dict) -> None:
        assert self._exchange is not None
        await self._exchange.publish(
            aio_pika.Message(
                body=json.dumps(body).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                content_type="application/json",
                headers=_trace_header(),  # carry the webhook's trace into the consumer
            ),
            routing_key=routing_key,
        )

    async def start_consuming(self, handler: Handler) -> None:
        assert self._queue is not None

        async def on_message(message: AbstractIncomingMessage) -> None:
            headers = dict(message.headers or {})
            tp = headers.get("traceparent")
            carrier = {"traceparent": tp} if tp else {}
            try:
                body = json.loads(message.body)
                start = perf_counter()
                # attach_context first → the `process event` span (and the whole case under it)
                # continues the webhook's trace. carrier empty (sim path) → a fresh root trace.
                with logfire.attach_context(carrier), logfire.span(
                    "process event", routing_key=message.routing_key or ""
                ):
                    await handler(message.routing_key or "", body)
                telemetry.event_latency.record(perf_counter() - start)  # per-attempt latency
                await message.ack()
            except Exception as exc:  # noqa: BLE001 — retry with backoff, then DLQ (don't crash)
                attempts = int(headers.get("x-retry-count", 0) or 0)
                key = next_retry_key(attempts)
                if key is not None and self._retry_exchange is not None:
                    # Park it in the matching backoff queue; it dead-letters back to `events` after
                    # the TTL. Ack here so it leaves the main queue (it now lives in the retry one).
                    await self._retry_exchange.publish(
                        aio_pika.Message(
                            body=message.body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                            content_type="application/json",
                            headers={"x-retry-count": attempts + 1, **carrier},  # keep the trace
                        ),
                        routing_key=key,
                    )
                    await message.ack()
                    log.warning("broker.retry_scheduled", attempt=attempts + 1, delay=key,
                                error=str(exc))
                else:
                    telemetry.events_failed.add(1)  # retries spent → dead-lettered (alert signal)
                    log.error("broker.handler_failed", error=str(exc), tb=traceback.format_exc())
                    await message.nack(requeue=False)  # retries spent → events.dlq

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
