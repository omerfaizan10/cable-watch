"""End-to-end check of the streaming path on a real Kafka-API broker (Redpanda).

Runs the same two commands an operator would, against the broker in CABLEWATCH_BROKERS:
  1. python -m cablewatch.replay <day> --jitter-ms 90000 --late-fraction 0.001
     (disordered arrival, keyed by MMSI, into a 6-partition ais.raw topic)
  2. python -m cablewatch.pipeline stream --run kafka_<day>
Then it checks, without trusting either command's own summary:
  * every produced row was consumed (the run audit's raw_in equals the row count);
  * the alerts written to Parquet equal the alerts on the cable.alerts topic;
  * those alerts equal an in-process run over the same rows in the same arrival order
    (so the broker, partitioning and consumer change nothing);
  * the run ledger balances.
Writes data/warehouse/kafka_check.json.

Usage (Redpanda running, see README):
  CABLEWATCH_BUS=kafka python -m cablewatch.kafka_check data/processed/raw_2022-02-25_26.parquet
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pyarrow.parquet as pq

from .bus import ALERT_TOPIC, LATE_TOPIC, RAW_TOPIC
from .config import DEFAULT
from .pipeline import ROOT, WAREHOUSE, build_index, run_rows
from .replay import arrival_schedule

PARTITIONS = 6
JITTER_MS = 90_000
LATE_FRACTION = 0.001
SEED = 7


def reset_topics(brokers: str) -> None:
    from confluent_kafka.admin import AdminClient, NewTopic

    admin = AdminClient({"bootstrap.servers": brokers})
    existing = set(admin.list_topics(timeout=10).topics)
    gone = [t for t in (RAW_TOPIC, ALERT_TOPIC, LATE_TOPIC) if t in existing]
    if gone:
        for f in admin.delete_topics(gone, operation_timeout=30).values():
            f.result()
        time.sleep(2)
    new = [NewTopic(RAW_TOPIC, num_partitions=PARTITIONS, replication_factor=1),
           NewTopic(ALERT_TOPIC, num_partitions=1, replication_factor=1),
           NewTopic(LATE_TOPIC, num_partitions=1, replication_factor=1)]
    for f in admin.create_topics(new).values():
        f.result()


def topic_count(brokers: str, topic: str) -> int:
    from confluent_kafka import Consumer, TopicPartition

    c = Consumer({"bootstrap.servers": brokers, "group.id": "kafka-check-count"})
    md = c.list_topics(topic, timeout=10).topics[topic]
    n = 0
    for p in md.partitions:
        lo, hi = c.get_watermark_offsets(TopicPartition(topic, p), timeout=10)
        n += hi - lo
    c.close()
    return n


def read_alert_topic(brokers: str) -> list[tuple]:
    from confluent_kafka import Consumer

    c = Consumer({"bootstrap.servers": brokers, "group.id": f"kafka-check-{time.time_ns()}",
                  "auto.offset.reset": "earliest"})
    c.subscribe([ALERT_TOPIC])
    out, idle = [], time.monotonic()
    while time.monotonic() - idle < 5:
        m = c.poll(1.0)
        if m is None or m.error():
            continue
        idle = time.monotonic()
        a = json.loads(m.value())
        out.append((a["ts"], a["mmsi"], a["rule"], a["cable_id"]))
    c.close()
    return sorted(out)


def main() -> None:
    src = Path(sys.argv[1])
    brokers = os.environ.get("CABLEWATCH_BROKERS", "127.0.0.1:19092")
    env = {**os.environ, "CABLEWATCH_BUS": "kafka", "CABLEWATCH_BROKERS": brokers}
    day = src.stem.replace("raw_", "")
    run = f"kafka_{day}"
    py = sys.executable

    reset_topics(brokers)
    t0 = time.monotonic()
    subprocess.run([py, "-m", "cablewatch.replay", str(src), "--jitter-ms", str(JITTER_MS),
                    "--late-fraction", str(LATE_FRACTION), "--seed", str(SEED)], env=env, cwd=ROOT, check=True)
    t_produce = time.monotonic() - t0
    produced = topic_count(brokers, RAW_TOPIC)
    t1 = time.monotonic()
    subprocess.run([py, "-m", "cablewatch.pipeline", "stream", "--run", run, "--idle-timeout", "15"],
                   env=env, cwd=ROOT, check=True)
    t_consume = time.monotonic() - t1

    audit = json.loads((WAREHOUSE / f"run_{run}.json").read_text())["audit"]
    import duckdb

    pq_alerts = sorted(tuple(r) for r in duckdb.sql(
        f"SELECT ts, mmsi, rule, cable_id FROM read_parquet('{WAREHOUSE / f'alerts_{run}.parquet'}')").fetchall())
    topic_alerts = read_alert_topic(brokers)

    # Reference: the same rows in the same arrival order, straight into the processor.
    rows = pq.read_table(src).to_pylist()
    sched = arrival_schedule(rows, JITTER_MS, LATE_FRACTION, DEFAULT.allowed_lateness_ms, seed=SEED)
    ref, _ = run_rows((r for _, _, r, _ in sched), build_index(), DEFAULT)
    ref_alerts = sorted((a.ts, a.mmsi, a.rule, a.cable_id) for a in ref.alerts)

    out = {
        "broker": "Redpanda v26.1.2 (Kafka API), single node",
        "source": str(src.resolve().relative_to(ROOT)),
        "partitions": PARTITIONS,
        "rows_in_file": len(rows),
        "rows_on_topic": produced,
        "rows_consumed": audit["raw_in"],
        "injected_late": sum(1 for s in sched if s[3]),
        "late_dropped": audit["late_dropped"],
        "alerts_parquet": len(pq_alerts),
        "alerts_topic": len(topic_alerts),
        "alerts_reference": len(ref_alerts),
        "parquet_equals_topic": pq_alerts == topic_alerts,
        "stream_equals_in_process": pq_alerts == ref_alerts,
        "audit_equals_in_process": audit == ref.audit(),
        "ledger_balanced": bool(audit.get("balanced")),
        "produce_seconds": round(t_produce, 1),
        "consume_seconds": round(t_consume, 1),
        "consume_rows_per_second": round(audit["raw_in"] / t_consume) if t_consume else None,
    }
    out["passed"] = all([out["rows_on_topic"] == out["rows_in_file"], out["rows_consumed"] == out["rows_in_file"],
                         out["parquet_equals_topic"], out["stream_equals_in_process"], out["ledger_balanced"]])
    (WAREHOUSE / "kafka_check.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    if not out["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
