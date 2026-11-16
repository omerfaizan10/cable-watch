"""Message bus adapters with one small interface.

* KafkaBus: Redpanda (or any Kafka-API broker) through confluent-kafka. Messages are keyed
  by MMSI, so all fixes of a vessel land in one partition and keep their relative order.
* LocalBus: an embedded append-only log (one JSONL file per topic). It exists because this
  machine has no Docker, so a Redpanda container cannot run here. Same produce/consume
  semantics minus partitions and consumer groups.

Pick with CABLEWATCH_BUS=kafka|local (default local) and CABLEWATCH_BROKERS.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterator, Protocol

TOPIC_DIR = Path(__file__).resolve().parent.parent / "data" / "topics"

RAW_TOPIC = "ais.raw"
ALERT_TOPIC = "cable.alerts"
LATE_TOPIC = "ais.late"
DQ_TOPIC = "ais.dq_rejects"


class Bus(Protocol):
    def produce(self, topic: str, key: str, value: dict) -> None: ...
    def flush(self) -> None: ...
    def consume(self, topic: str, group: str, idle_timeout_s: float = 5.0) -> Iterator[dict]: ...


class LocalBus:
    def __init__(self, root: Path = TOPIC_DIR):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._fh: dict[str, object] = {}

    def path(self, topic: str) -> Path:
        return self.root / f"{topic}.jsonl"

    def reset(self, topic: str) -> None:
        if topic in self._fh:
            self._fh.pop(topic).close()
        self.path(topic).unlink(missing_ok=True)

    def produce(self, topic: str, key: str, value: dict) -> None:
        fh = self._fh.get(topic)
        if fh is None:
            fh = self._fh[topic] = open(self.path(topic), "a", encoding="utf-8")
        fh.write(json.dumps({"key": key, "value": value}, separators=(",", ":")) + "\n")

    def flush(self) -> None:
        for fh in self._fh.values():
            fh.flush()

    def consume(self, topic: str, group: str = "", idle_timeout_s: float = 0.0) -> Iterator[dict]:
        self.flush()
        p = self.path(topic)
        if not p.exists():
            return
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                yield json.loads(line)["value"]

    def close(self) -> None:
        for fh in self._fh.values():
            fh.close()
        self._fh.clear()


class KafkaBus:
    def __init__(self, brokers: str):
        from confluent_kafka import Producer

        self.brokers = brokers
        self.producer = Producer({"bootstrap.servers": brokers, "linger.ms": 20, "compression.type": "lz4"})

    def produce(self, topic: str, key: str, value: dict) -> None:
        while True:
            try:
                self.producer.produce(topic, key=key, value=json.dumps(value, separators=(",", ":")))
                break
            except BufferError:
                self.producer.poll(0.5)
        self.producer.poll(0)

    def flush(self) -> None:
        self.producer.flush()

    def consume(self, topic: str, group: str, idle_timeout_s: float = 5.0) -> Iterator[dict]:
        """Read until the topic has been idle for idle_timeout_s (0 means run forever)."""
        import time

        from confluent_kafka import Consumer

        c = Consumer({"bootstrap.servers": self.brokers, "group.id": group, "auto.offset.reset": "earliest"})
        c.subscribe([topic])
        last = time.monotonic()
        try:
            while True:
                msg = c.poll(1.0)
                if msg is None:
                    if idle_timeout_s and time.monotonic() - last > idle_timeout_s:
                        return
                    continue
                if msg.error():
                    continue
                last = time.monotonic()
                yield json.loads(msg.value())
        finally:
            c.close()

    def close(self) -> None:
        self.flush()


def get_bus() -> LocalBus | KafkaBus:
    kind = os.environ.get("CABLEWATCH_BUS", "local")
    if kind == "kafka":
        return KafkaBus(os.environ.get("CABLEWATCH_BROKERS", "127.0.0.1:19092"))
    return LocalBus()
